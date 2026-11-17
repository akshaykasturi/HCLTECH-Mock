"""A tiny disk cache for LLM answers: one JSON file per request in backend/.cache/llm/.

Same provider + model + prompts + schema -> same file, so a repeated request costs nothing
and gives the same answer (useful for demos and evaluation). The folder is git-ignored.
"""
import hashlib
import json
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parents[3] / ".cache" / "llm"


def make_key(provider: str, model: str, system: str, user: str, schema_name: str) -> str:
    """sha256 of everything that changes the answer. \\x00 separates the parts."""
    joined = "\x00".join([provider, model, system, user, schema_name])
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def get(key: str) -> str | None:
    """The cached answer text, or None if there is none (or the file is unreadable)."""
    path = CACHE_DIR / f"{key}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))["value"]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def put(key: str, value: str) -> None:
    """Save an answer. A failed write is ignored: the cache is only a speed-up."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        (CACHE_DIR / f"{key}.json").write_text(json.dumps({"value": value}), encoding="utf-8")
    except OSError:
        pass
