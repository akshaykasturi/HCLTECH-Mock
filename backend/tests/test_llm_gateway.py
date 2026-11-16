"""LLM gateway tests. No network: the provider functions are replaced by fakes.

Each fake returns its answers in order and records the prompts it was sent.
"""
import json

import pytest
from pydantic import BaseModel

from app.uc4.llm import cache, config, gateway, providers
from app.uc4.llm.providers import ProviderError
from app.uc4.report_models import Citation, Step

FAKE_GEMINI_KEY = "AIzaFAKE-gemini-key-123456"
FAKE_OTHER_KEY = "gsk_FAKE_other_key_987654"

GOOD_STEP = json.dumps({"action": "Look at orders-db latency", "why": "it rose", "cites": ["metric:a"]})


class Fake:
    """Stands in for a provider function: returns (or raises) its answers in order."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls: list[tuple[str, str]] = []  # (system, user)

    def __call__(self, system, user, *args):
        self.calls.append((system, user))
        answer = self.answers.pop(0) if self.answers else ProviderError("no more answers")
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture(autouse=True)
def llm_env(monkeypatch, tmp_path):
    """Fake keys, both providers configured, cache off, no real .env, fresh breakers."""
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "no.env")
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path / "cache")
    for name, value in {"GEMINI_API_KEY": FAKE_GEMINI_KEY, "GEMINI_MODEL": "g-test",
                        "LLM_BASE_URL": "http://127.0.0.1:11434/v1", "LLM_API_KEY": FAKE_OTHER_KEY,
                        "LLM_MODEL": "m-test", "LLM_PROVIDERS": "gemini,openai_compat",
                        "LLM_CACHE": "0"}.items():
        monkeypatch.setenv(name, value)
    gateway.reset_breakers()
    yield
    gateway.reset_breakers()


def use(monkeypatch, gemini=None, other=None):
    gemini = gemini or Fake()
    other = other or Fake()
    monkeypatch.setattr(providers, "gemini", gemini)
    monkeypatch.setattr(providers, "openai_compat", other)
    return gemini, other


def test_valid_json_first_try(monkeypatch):
    gemini, other = use(monkeypatch, Fake(GOOD_STEP))
    result = gateway.generate(Step, "Write a step.", "evidence...")
    assert isinstance(result.output, Step) and result.output.cites == ["metric:a"]
    assert result.provider == "gemini" and result.errors == [] and not result.cached
    assert len(gemini.calls) == 1 and other.calls == []


def test_system_prompt_ends_with_safety_rule(monkeypatch):
    gemini, _ = use(monkeypatch, Fake(GOOD_STEP))
    gateway.generate(Step, "Write a step.", "evidence...")
    assert gemini.calls[0][0].endswith(gateway.SAFETY_RULE)


def test_invalid_then_repaired(monkeypatch):
    gemini, other = use(monkeypatch, Fake("not json", GOOD_STEP))
    result = gateway.generate(Step, "s", "u")
    assert result.provider == "gemini" and result.output is not None
    assert len(gemini.calls) == 2 and other.calls == []
    assert "rejected" in gemini.calls[1][1]  # the error was sent back
    assert len(result.errors) == 1


def test_fenced_json_is_accepted(monkeypatch):
    use(monkeypatch, Fake(f"```json\n{GOOD_STEP}\n```"))
    assert gateway.generate(Step, "s", "u").output is not None


def test_invalid_twice_moves_to_next_provider(monkeypatch):
    gemini, other = use(monkeypatch, Fake("{}", '{"action": 1}'), Fake(GOOD_STEP))
    result = gateway.generate(Step, "s", "u")
    assert result.provider == "openai_compat" and result.output is not None
    assert len(gemini.calls) == 2 and len(other.calls) == 1
    assert len(result.errors) == 2


def test_all_fail_uses_fallback(monkeypatch):
    use(monkeypatch, Fake(ProviderError("HTTP 500")), Fake("{}", "{}"))
    template = Step(action="template step", why="code built it")
    result = gateway.generate(Step, "s", "u", fallback=lambda: template)
    assert result.provider == "template" and result.output is template
    assert len(result.errors) == 3


def test_no_fallback_gives_none_without_raising(monkeypatch):
    use(monkeypatch, Fake(RuntimeError("boom")), Fake(ValueError("bad")))
    result = gateway.generate(Step, "s", "u")
    assert result.output is None and result.provider == "none" and result.errors


def test_fallback_that_raises_does_not_raise(monkeypatch):
    use(monkeypatch, Fake(ProviderError("x")), Fake(ProviderError("y")))

    def broken():
        raise RuntimeError("template broke")

    result = gateway.generate(Step, "s", "u", fallback=broken)
    assert result.output is None and any("fallback error" in e for e in result.errors)


def test_unknown_evidence_id_triggers_repair(monkeypatch):
    bad = json.dumps({"action": "a", "why": "w", "cites": ["metric:made-up"]})
    gemini, _ = use(monkeypatch, Fake(bad, GOOD_STEP))
    result = gateway.generate(Step, "s", "u", allowed_ids=["metric:a"])
    assert result.provider == "gemini" and result.output.cites == ["metric:a"]
    assert len(gemini.calls) == 2 and "metric:made-up" in gemini.calls[1][1]


def test_unknown_evidence_id_in_nested_citation(monkeypatch):
    class Holder(BaseModel):
        supporting: list[Citation]

    bad = json.dumps({"supporting": [{"evidence_id": "log:nope", "quote": "q"}]})
    good = json.dumps({"supporting": [{"evidence_id": "log:1", "quote": "q"}]})
    use(monkeypatch, Fake(bad, bad), Fake(good))
    result = gateway.generate(Holder, "s", "u", allowed_ids=["log:1"])
    assert result.provider == "openai_compat"


def test_breaker_skips_provider_after_three_failures(monkeypatch):
    gemini, other = use(monkeypatch, Fake(*[ProviderError("HTTP 503")] * 3),
                        Fake(GOOD_STEP, GOOD_STEP, GOOD_STEP, GOOD_STEP))
    for _ in range(3):
        assert gateway.generate(Step, "s", "u").provider == "openai_compat"
    assert len(gemini.calls) == 3
    result = gateway.generate(Step, "s", "u")
    assert len(gemini.calls) == 3  # not called a 4th time
    assert result.provider == "openai_compat"
    assert any("circuit breaker" in e for e in result.errors)


def test_breaker_reopens_after_rest(monkeypatch):
    gemini, _ = use(monkeypatch, Fake(*[ProviderError("x")] * 3, GOOD_STEP), Fake(*[GOOD_STEP] * 3))
    for _ in range(3):
        gateway.generate(Step, "s", "u")
    gateway._breakers["gemini"].open_until = 0.0  # pretend 300 s have passed
    assert gateway.generate(Step, "s", "u").provider == "gemini"


def test_cache_hit_returns_cached(monkeypatch):
    monkeypatch.setenv("LLM_CACHE", "1")
    gemini, _ = use(monkeypatch, Fake(GOOD_STEP))
    first = gateway.generate(Step, "s", "u")
    second = gateway.generate(Step, "s", "u")
    assert not first.cached and second.cached
    assert second.output == first.output and second.provider == "gemini"
    assert len(gemini.calls) == 1


def test_cache_off_writes_nothing(monkeypatch, tmp_path):
    use(monkeypatch, Fake(GOOD_STEP))
    gateway.generate(Step, "s", "u")
    assert not (tmp_path / "cache").exists()


def test_fake_key_never_in_errors(monkeypatch):
    use(monkeypatch, Fake(ProviderError(f"denied for key {FAKE_GEMINI_KEY}")),
        Fake(RuntimeError(f"Bearer {FAKE_OTHER_KEY} rejected")))
    result = gateway.generate(Step, "s", "u")
    joined = " ".join(result.errors)
    assert FAKE_GEMINI_KEY not in joined and FAKE_OTHER_KEY not in joined
    assert "<KEY>" in joined


def test_provider_without_key_is_skipped(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    gemini, other = use(monkeypatch, Fake(GOOD_STEP), Fake(GOOD_STEP))
    assert gateway.generate(Step, "s", "u").provider == "openai_compat"
    assert gemini.calls == []


def test_openai_compat_needs_no_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDERS", "openai_compat")
    monkeypatch.setenv("LLM_API_KEY", "")
    use(monkeypatch, other=Fake(GOOD_STEP))
    assert gateway.generate(Step, "s", "u").provider == "openai_compat"


def test_env_file_parser_does_not_override_environment(monkeypatch, tmp_path):
    env_file = tmp_path / "test.env"
    env_file.write_text('# comment\nLLM_MODEL="from-file"\nLLM_TIMEOUT_S=5\n', encoding="utf-8")
    monkeypatch.setattr(config, "ENV_FILE", env_file)
    monkeypatch.delenv("LLM_TIMEOUT_S", raising=False)
    cfg = config.get_config()
    assert cfg.timeout_s == 5.0  # from the file
    assert cfg.model == "m-test"  # real environment wins


def test_gemini_key_goes_in_header_not_url(monkeypatch):
    seen = {}

    def fake_post(url, headers, body, timeout):
        seen.update(url=url, headers=headers, body=body)
        return {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}

    monkeypatch.setattr(providers, "_post_json", fake_post)
    providers.gemini("sys", "user", "g-test", FAKE_GEMINI_KEY, 5)
    assert FAKE_GEMINI_KEY not in seen["url"]
    assert seen["headers"]["x-goog-api-key"] == FAKE_GEMINI_KEY
    assert seen["body"]["generationConfig"] == {"responseMimeType": "application/json", "temperature": 0}


def test_model_lists_use_header_and_return_names_only(monkeypatch):
    seen = []

    def fake_get(url, headers, body, timeout):
        seen.append((url, headers, body))
        if "googleapis" in url:
            return {"models": [{"name": "models/g-b", "supportedGenerationMethods": ["generateContent"]},
                               {"name": "models/embed", "supportedGenerationMethods": ["embedContent"]},
                               {"name": "models/g-a", "supportedGenerationMethods": ["generateContent"]}]}
        return {"data": [{"id": "m-2"}, {"id": "m-1"}]}

    monkeypatch.setattr(providers, "_post_json", fake_get)
    assert providers.gemini_models(FAKE_GEMINI_KEY, 5) == ["g-a", "g-b"]
    assert providers.openai_compat_models("http://127.0.0.1:11434/v1/", FAKE_OTHER_KEY, 5) == ["m-1", "m-2"]
    assert all(body is None for _, _, body in seen)  # GET requests
    assert all(FAKE_GEMINI_KEY not in url and FAKE_OTHER_KEY not in url for url, _, _ in seen)
    assert seen[1][0] == "http://127.0.0.1:11434/v1/models"


def test_gemini_model_prefix_is_removed(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "models/g-test")
    assert config.get_config().gemini_model == "g-test"  # else the URL would say models/models/...
