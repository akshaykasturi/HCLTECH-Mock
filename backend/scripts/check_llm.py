"""Check each configured LLM provider with a tiny request: prints provider, ok/fail, latency.

Usage (from backend):  .\\.venv\\Scripts\\python.exe scripts\\check_llm.py
Add --models to list the model names each provider offers your key (names only).
Never prints keys or full responses. The cache is turned off so every provider is really called.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import BaseModel  # noqa: E402

from app.uc4.llm import gateway, providers  # noqa: E402
from app.uc4.llm.config import get_config  # noqa: E402


class Ping(BaseModel):
    ok: bool


def list_models() -> int:
    """--models: print the model names each configured provider offers this key (names only)."""
    cfg = get_config()
    names = [n for n in cfg.providers if gateway._is_configured(n, cfg)]
    if not names:
        print("No LLM provider configured. See backend/.env.example.")
        return 1
    for name in names:
        configured = gateway._model_of(name, cfg)
        try:
            if name == "gemini":
                models = providers.gemini_models(cfg.gemini_key, cfg.timeout_s)
            else:
                models = providers.openai_compat_models(cfg.base_url, cfg.api_key, cfg.timeout_s)
        except Exception as exc:
            print(f"{name}: could not list models ({gateway._safe(str(exc), cfg)})")
            continue
        found = "yes" if configured in models else "NO"
        print(f"{name}: {len(models)} models; configured model {configured!r} in the list: {found}")
        for model in models:
            print(f"  {model}")
    return 0


def skipped_providers(cfg) -> list[tuple[str, list[str]]]:
    """Providers that will be skipped, with the NAMES of the empty variables (never values)."""
    needs = {"gemini": [("GEMINI_API_KEY", cfg.gemini_key), ("GEMINI_MODEL", cfg.gemini_model)],
             "openai_compat": [("LLM_BASE_URL", cfg.base_url), ("LLM_MODEL", cfg.model)]}
    skipped = []
    for name in ("gemini", "openai_compat"):
        if name not in cfg.providers:
            skipped.append((name, ["not listed in LLM_PROVIDERS"]))
            continue
        missing = [var for var, value in needs[name] if not value]
        if missing:
            skipped.append((name, missing))
    return skipped


def main() -> int:
    if "--models" in sys.argv[1:]:
        return list_models()
    os.environ["LLM_CACHE"] = "0"
    cfg = get_config()
    print(f"LLM_PROVIDERS order: {', '.join(cfg.providers) or '(empty)'}")
    for name, missing in skipped_providers(cfg):
        print(f"{name:<14} SKIP  not configured, empty: {', '.join(missing)}")  # names only
    names = [n for n in cfg.providers if gateway._is_configured(n, cfg)]
    if not names:
        print("No LLM provider configured. See backend/.env.example.")
        return 1
    failed = 0
    for name in names:
        gateway.reset_breakers()
        result = gateway.generate(Ping, "You are a health check.", 'Reply with {"ok": true}.', only=[name])
        ok = result.output is not None and result.provider == name
        failed += not ok
        line = f"{name:<14} {'ok' if ok else 'FAIL':<5} {result.latency_ms} ms"
        if not ok and result.errors:
            line += f"  ({result.errors[-1]})"  # already short and scrubbed of keys
        print(line)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
