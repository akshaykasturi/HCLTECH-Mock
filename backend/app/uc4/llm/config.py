"""LLM settings, from environment variables, with backend/.env as a fallback.

Real environment variables win over the .env file. The .env file is read into a dict
(never copied into os.environ) and nothing here ever prints a value.
"""
import os
from dataclasses import dataclass
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parents[3] / ".env"  # backend/.env (tests point this elsewhere)

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


def read_env_file(path: Path) -> dict[str, str]:
    """Tiny .env parser: KEY=VALUE lines; blank lines and # comments skipped; quotes removed."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[name] = value
    return values


@dataclass(frozen=True)
class LLMConfig:
    gemini_key: str
    gemini_model: str
    base_url: str  # OpenAI-compatible server: Groq, Ollama (http://127.0.0.1:11434/v1)...
    api_key: str  # empty is fine for Ollama
    model: str
    providers: list[str]  # order to try them in
    timeout_s: float
    cache: bool

    def secrets(self) -> list[str]:
        """The key values, so error messages can be scrubbed of them."""
        return [k for k in (self.gemini_key, self.api_key) if k]


def get_config() -> LLMConfig:
    """Read the settings now (not at import), so a changed environment is picked up."""
    file_values = read_env_file(ENV_FILE)

    def get(name: str, default: str = "") -> str:
        value = os.environ.get(name)
        if value is None or value == "":
            value = file_values.get(name, default)
        return value.strip()

    try:
        timeout = float(get("LLM_TIMEOUT_S", "12"))
    except ValueError:
        timeout = 12.0
    return LLMConfig(
        gemini_key=get("GEMINI_API_KEY"),
        # Google lists models as "models/<name>"; our URL already adds "models/", so drop it here
        gemini_model=get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).removeprefix("models/"),
        base_url=get("LLM_BASE_URL").rstrip("/"),
        api_key=get("LLM_API_KEY"),
        model=get("LLM_MODEL"),
        providers=[p.strip() for p in get("LLM_PROVIDERS", "gemini,openai_compat").split(",") if p.strip()],
        timeout_s=timeout,
        cache=get("LLM_CACHE", "1") != "0",
    )
