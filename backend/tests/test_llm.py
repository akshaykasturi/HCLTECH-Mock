"""LLM layer tests. No network: Groq uses a mock HTTP transport, Gemini a fake SDK client."""
import json
from types import SimpleNamespace

import httpx
import pytest

from app.config import Settings
from app.contracts import Match
from app.llm.base import LLMError
from app.llm.fake import FakeLLM
from app.llm.gemini import GeminiLLM
from app.llm.groq import GroqLLM, strict
from app.llm.router import ChainLLM, build_llm
from app.pipeline.generate import SCHEMA, generate

GOOD = {"steps": ["Unlock the account"], "citations": [
    {"source_id": "INC1", "excerpt": "Unlocked the account.", "reason": "same fix"}]}
MATCH = Match(source_id="INC1", source_type="ticket", title="t", text="Unlocked the account.", score=1.0)


def test_chain_falls_back_to_second_provider_and_reports_who_answered():
    chain = ChainLLM([FakeLLM(fail=True), FakeLLM(response=GOOD)])
    chain.providers[1].name = "groq:test"
    result, provider, errors = chain.run("s", "u", SCHEMA)
    assert result == GOOD and provider == "groq:test" and len(errors) == 1
    assert chain.generate_json("s", "u", SCHEMA) == GOOD     # LLMClient interface still works


def test_chain_raises_when_all_fail():
    with pytest.raises(LLMError) as exc:
        ChainLLM([FakeLLM(fail=True), FakeLLM(fail=True)]).run("s", "u", SCHEMA)
    assert exc.value.errors == ["fake failure", "fake failure"]  # errors travel on the exception


class FakeClock:
    """Manually advanced clock for the circuit breaker: no sleeping in tests."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make_breaker_chain():
    clock = FakeClock()
    first, second = FakeLLM(fail=True), FakeLLM(response=GOOD)
    first.name, second.name = "gemini:test", "groq:test"
    return ChainLLM([first, second], cooldown_s=300, clock=clock), first, clock


def test_failed_provider_is_skipped_on_next_call():
    chain, first, clock = make_breaker_chain()
    chain.run("s", "u", SCHEMA)                               # first fails -> starts cooling down
    clock.now += 299
    result, provider, errors = chain.run("s", "u", SCHEMA)
    assert result == GOOD
    assert len(first.calls) == 1                              # not called again during cooldown
    assert errors == ["gemini:test skipped: cooling down"] and provider == "groq:test"


def test_failed_provider_is_retried_after_cooldown():
    chain, first, clock = make_breaker_chain()
    chain.run("s", "u", SCHEMA)
    clock.now += 300
    _, _, errors = chain.run("s", "u", SCHEMA)
    assert len(first.calls) == 2                              # tried again once the cooldown is over
    assert errors == ["fake failure"]                         # failed again -> cooling down again
    clock.now += 1
    chain.run("s", "u", SCHEMA)
    assert len(first.calls) == 2


def test_success_resets_failure():
    chain, first, clock = make_breaker_chain()
    chain.run("s", "u", SCHEMA)
    clock.now += 300
    first.fail, first.response = False, GOOD                  # provider has recovered
    assert chain.run("s", "u", SCHEMA)[:2] == (GOOD, "gemini:test")
    first.fail = True                                         # one new failure...
    chain.run("s", "u", SCHEMA)
    first.fail = False
    clock.now += 300                                          # ...gives one fresh cooldown, no stale state
    assert chain.run("s", "u", SCHEMA)[:2] == (GOOD, "gemini:test")
    assert len(first.calls) == 4


def test_all_providers_cooling_down_raises_so_generate_falls_back():
    clock = FakeClock()
    chain = ChainLLM([FakeLLM(fail=True)], cooldown_s=300, clock=clock)
    with pytest.raises(LLMError):
        chain.generate_json("s", "u", SCHEMA)
    with pytest.raises(LLMError, match="skipped: cooling down"):
        chain.generate_json("s", "u", SCHEMA)
    assert len(chain.providers[0].calls) == 1


def test_groq_sends_strict_schema_and_parses_reply():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(GOOD)}}]})

    client = GroqLLM("k", "openai/gpt-oss-120b", transport=httpx.MockTransport(handler))
    assert client.generate_json("sys", "user", SCHEMA) == GOOD
    fmt = seen["body"]["response_format"]["json_schema"]
    assert fmt["strict"] and fmt["schema"]["additionalProperties"] is False
    assert seen["auth"] == "Bearer k"


def test_groq_http_error_becomes_llm_error():
    client = GroqLLM("k", "m", transport=httpx.MockTransport(lambda r: httpx.Response(429, json={})))
    with pytest.raises(LLMError):
        client.generate_json("s", "u", SCHEMA)


def groq_error(status: int, code: str, message: str, **extra) -> httpx.Response:
    return httpx.Response(status, json={"error": {"code": code, "message": message, "type": "invalid_request_error",
                                                   **extra}})


def test_groq_error_text_has_code_and_message_but_no_key_or_failed_output():
    def handler(request: httpx.Request) -> httpx.Response:
        return groq_error(400, "model_not_found", "The model `x` does not exist",
                          failed_generation='{"steps": ["secret ticket text"]}')

    client = GroqLLM("gsk_supersecretkey123456", "x", transport=httpx.MockTransport(handler))
    with pytest.raises(LLMError) as exc:
        client.generate_json("s", "u", SCHEMA)
    text = str(exc.value)
    assert "HTTP 400 model_not_found: The model `x` does not exist" in text
    assert "gsk_supersecretkey123456" not in text and "Bearer" not in text
    assert "secret ticket text" not in text                      # failed_generation is never copied


def test_groq_retries_json_validate_failed_once_then_succeeds():
    replies = [groq_error(400, "json_validate_failed", "Generated JSON does not match the expected schema."),
               httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(GOOD)}}]})]
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return replies[len(calls) - 1]

    client = GroqLLM("k", "m", transport=httpx.MockTransport(handler))
    assert client.generate_json("s", "u", SCHEMA) == GOOD
    assert len(calls) == 2 and calls[0] == calls[1]               # the same request, sent once more


def test_groq_gives_up_after_one_json_validate_retry():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return groq_error(400, "json_validate_failed", "Generated JSON does not match the expected schema.")

    client = GroqLLM("k", "m", transport=httpx.MockTransport(handler))
    with pytest.raises(LLMError, match="HTTP 400 json_validate_failed"):
        client.generate_json("s", "u", SCHEMA)
    assert len(calls) == 2


def test_groq_other_errors_are_not_retried():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return groq_error(429, "rate_limit_exceeded", "Rate limit reached for model")

    client = GroqLLM("k", "m", transport=httpx.MockTransport(handler))
    with pytest.raises(LLMError, match="HTTP 429 rate_limit_exceeded: Rate limit reached"):
        client.generate_json("s", "u", SCHEMA)
    assert len(calls) == 1


def test_groq_non_json_error_body_is_reported_safely():
    client = GroqLLM("k", "m", transport=httpx.MockTransport(lambda r: httpx.Response(502, text="Bad gateway")))
    with pytest.raises(LLMError, match="HTTP 502 unknown: Bad gateway"):
        client.generate_json("s", "u", SCHEMA)


def test_strict_schema_marks_nested_fields_required():
    s = strict(SCHEMA)
    item = s["properties"]["citations"]["items"]
    assert item["additionalProperties"] is False and set(item["required"]) == {"source_id", "excerpt", "reason"}


def test_gemini_parses_json_and_wraps_errors():
    ok_client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kw: SimpleNamespace(text=json.dumps(GOOD))))
    assert GeminiLLM("k", "m", client=ok_client).generate_json("s", "u", SCHEMA) == GOOD

    def boom(**kw):
        raise RuntimeError("429 quota")
    bad_client = SimpleNamespace(models=SimpleNamespace(generate_content=boom))
    with pytest.raises(LLMError):
        GeminiLLM("k", "m", client=bad_client).generate_json("s", "u", SCHEMA)


def capturing_client(seen: dict):
    def generate_content(**kw):
        seen.update(kw)
        return SimpleNamespace(text=json.dumps(GOOD))
    return SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))


def test_gemini_sends_thinking_level():
    from google.genai import types

    seen = {}
    GeminiLLM("k", "m", client=capturing_client(seen), thinking_level="low").generate_json("s", "u", SCHEMA)
    assert seen["config"].thinking_config.thinking_level == types.ThinkingLevel.LOW


def test_gemini_omits_thinking_config_when_level_empty():
    seen = {}
    GeminiLLM("k", "m", client=capturing_client(seen), thinking_level="").generate_json("s", "u", SCHEMA)
    assert seen["config"].thinking_config is None


def test_thinking_level_setting_defaults_to_low_and_is_validated(monkeypatch):
    monkeypatch.delenv("GEMINI_THINKING_LEVEL", raising=False)
    assert Settings().gemini_thinking_level == "low"
    monkeypatch.setenv("GEMINI_THINKING_LEVEL", " High ")
    assert Settings().gemini_thinking_level == "high"
    monkeypatch.setenv("GEMINI_THINKING_LEVEL", "")
    assert Settings().gemini_thinking_level == ""
    monkeypatch.setenv("GEMINI_THINKING_LEVEL", "turbo")
    with pytest.raises(ValueError, match="GEMINI_THINKING_LEVEL"):
        Settings()


def test_build_llm_passes_thinking_level_to_gemini(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("GEMINI_THINKING_LEVEL", "minimal")
    assert build_llm(Settings()).providers[0].thinking_level == "minimal"


def test_build_llm_uses_only_providers_with_keys(monkeypatch):
    for k in ("GEMINI_API_KEY", "GROQ_API_KEY", "GROQ_MODEL"):  # GROQ_MODEL too: test the default, not .env
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    assert build_llm(Settings()) is None                       # no keys -> extractive
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setenv("LLM_COOLDOWN_S", "42")
    chain = build_llm(Settings())
    assert [p.name for p in chain.providers] == ["groq:openai/gpt-oss-120b"]
    assert chain.cooldown_s == 42                              # cooldown comes from config
    monkeypatch.setenv("LLM_PROVIDER", "extractive")
    assert build_llm(Settings()) is None


def test_llm_with_empty_steps_falls_back_to_extractive():
    rec, reason, _ = generate("t", [MATCH], FakeLLM(response={"steps": [" "], "citations": []}))
    assert rec.generator == "extractive" and reason == "LLM_NO_STEPS"


def test_malformed_llm_output_falls_back_to_extractive():
    rec, reason, _ = generate("t", [MATCH], FakeLLM(response={"steps": ["x"], "citations": [{"source_id": "INC1"}]}))
    assert rec.generator == "extractive" and reason.startswith("LLM_FAILED")


# ---------- no shared per-request state ----------
class KeyedLLM:
    """Fails when the prompt contains `fail_on`, so each call's outcome depends only on its own input.
    An optional barrier holds every caller here until all have arrived, forcing the calls to overlap."""

    def __init__(self, name: str, fail_on: str | None = None, barrier=None) -> None:
        self.name, self.fail_on, self.barrier = name, fail_on, barrier

    def generate_json(self, system: str, user: str, schema: dict) -> dict:
        if self.barrier is not None:
            self.barrier.wait()
        if self.fail_on and self.fail_on in user:
            raise LLMError(f"{self.name} failed on {self.fail_on}")
        return GOOD


def test_second_call_cannot_change_first_calls_values():
    chain = ChainLLM([KeyedLLM("gemini:test", fail_on="ALPHA"), KeyedLLM("groq:test")],
                     cooldown_s=0, clock=FakeClock())
    first = chain.run("s", "ticket ALPHA", SCHEMA)
    snapshot = (first[1], list(first[2]))
    second = chain.run("s", "ticket BRAVO", SCHEMA)
    assert (first[1], first[2]) == snapshot == ("groq:test", ["gemini:test failed on ALPHA"])
    assert second[1:] == ("gemini:test", [])
    assert not hasattr(chain, "errors")                      # nothing per-request lives on the chain


def test_concurrent_analyses_keep_their_own_generator_and_errors():
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from app.contracts import TicketIn
    from app.pipeline.orchestrator import analyse

    barrier = threading.Barrier(2, timeout=10)  # both requests are inside the first provider at once
    # cooldown 0 + frozen clock: one call's failure never makes the other skip a provider
    chain = ChainLLM([KeyedLLM("gemini:test", fail_on="ALPHA", barrier=barrier), KeyedLLM("groq:test")],
                     cooldown_s=0, clock=FakeClock())
    desc = "GlobalProtect shows certificate error from home. Worked last week. Reference {}."
    tickets = [TicketIn(title="VPN not connecting", description=desc.format(ref)) for ref in ("ALPHA", "BRAVO")]

    with ThreadPoolExecutor(max_workers=2) as pool:
        failed_first, ok_first = pool.map(lambda t: analyse(t, chain), tickets)

    def generate_event(result):
        return next(e.detail for e in result.trace if e.step == "generate")

    assert failed_first.recommendation.generator == "groq:test"
    assert generate_event(failed_first)["llm_errors"] == ["gemini:test failed on ALPHA"]
    assert ok_first.recommendation.generator == "gemini:test"
    assert generate_event(ok_first)["llm_errors"] == []
