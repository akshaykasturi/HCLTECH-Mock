"""Builds the LLM chain from settings: Gemini first, Groq if Gemini fails, else no LLM (extractive)."""
import threading
import time
from typing import Callable

from app.config import Settings
from app.llm.base import LLMClient, LLMError


class ChainLLM:
    """Tries each provider in order.

    One ChainLLM is shared by all requests, so it stores nothing about a single request: `run()`
    returns the provider that answered and the errors seen *for that call*.

    Circuit breaker: a provider that raises LLMError is skipped for `cooldown_s` seconds, so a down
    provider does not cost every request a full timeout. After the cooldown it is tried again;
    a success clears its failure. This memory (`_down_until`) is shared on purpose: it describes the
    provider, not a request. `clock` is injectable so tests can move time without sleeping."""

    name = "chain"  # fixed; the provider that answered a call comes back from run()

    def __init__(self, providers: list[LLMClient], cooldown_s: float = 300.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.providers = providers
        self.cooldown_s = cooldown_s
        self.clock = clock
        self._down_until: dict[int, float] = {}  # provider index -> clock time when it may be retried
        self._lock = threading.Lock()            # guards _down_until across request threads

    def run(self, system: str, user: str, schema: dict) -> tuple[dict, str, list[str]]:
        """Returns (result, provider_name, errors) for this call only.
        Raises LLMError carrying `errors` when every provider failed or was cooling down."""
        errors: list[str] = []
        for i, p in enumerate(self.providers):
            with self._lock:
                cooling = self.clock() < self._down_until.get(i, float("-inf"))
            if cooling:
                errors.append(f"{p.name} skipped: cooling down")
                continue
            try:
                result = p.generate_json(system, user, schema)
            except LLMError as e:
                errors.append(str(e))
                with self._lock:
                    self._down_until[i] = self.clock() + self.cooldown_s
                continue
            with self._lock:
                self._down_until.pop(i, None)
            return result, p.name, errors
        raise LLMError(" | ".join(errors), errors=errors)

    def generate_json(self, system: str, user: str, schema: dict) -> dict:
        """LLMClient interface. Use run() when you need to know who answered."""
        return self.run(system, user, schema)[0]


def run_llm(llm: LLMClient, system: str, user: str, schema: dict) -> tuple[dict, str, list[str]]:
    """(result, provider_name, errors) for any client: a chain reports per call, a single provider is itself."""
    if isinstance(llm, ChainLLM):
        return llm.run(system, user, schema)
    return llm.generate_json(system, user, schema), llm.name, []


def build_llm(settings: Settings) -> LLMClient | None:
    """LLM_PROVIDER: auto (default) = every provider that has a key, in order gemini -> groq;
    gemini / groq = only that one; extractive = no LLM at all."""
    choice = settings.llm_provider
    if choice == "extractive":
        return None
    providers: list[LLMClient] = []
    if choice in ("auto", "gemini") and settings.gemini_api_key:
        from app.llm.gemini import GeminiLLM
        providers.append(GeminiLLM(settings.gemini_api_key, settings.gemini_model, settings.llm_timeout_s,
                                   thinking_level=settings.gemini_thinking_level))
    if choice in ("auto", "groq") and settings.groq_api_key:
        from app.llm.groq import GroqLLM
        providers.append(GroqLLM(settings.groq_api_key, settings.groq_model, settings.llm_timeout_s))
    return ChainLLM(providers, cooldown_s=settings.llm_cooldown_s) if providers else None
