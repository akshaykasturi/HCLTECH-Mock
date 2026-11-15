"""Settings from environment variables (and backend/.env when present), plus policy.yaml.
Nothing secret is hard-coded. Real keys live only in .env (git-ignored) or the host's env settings."""
import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")  # does not override variables already set (tests rely on this)

GEMINI_THINKING_LEVELS = ("", "minimal", "low", "medium", "high")
EMBEDDERS = ("fastembed", "hash")


class Settings:
    def __init__(self) -> None:
        self.data_dir = Path(os.getenv("DATA_DIR", BACKEND_DIR / "data"))
        # auto = Gemini then Groq for whichever keys exist; extractive = no LLM; or gemini / groq only
        self.llm_provider = os.getenv("LLM_PROVIDER", "auto")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
        # how much Gemini "thinks" before answering; lower = faster. Empty = don't send it (model default)
        self.gemini_thinking_level = os.getenv("GEMINI_THINKING_LEVEL", "low").strip().lower()
        if self.gemini_thinking_level not in GEMINI_THINKING_LEVELS:
            raise ValueError(f"GEMINI_THINKING_LEVEL must be one of minimal, low, medium, high or empty, "
                             f"got {self.gemini_thinking_level!r}")
        self.groq_api_key = os.getenv("GROQ_API_KEY", "")
        # gpt-oss-120b: gpt-oss-20b kept failing Groq's strict schema check (json_validate_failed) in Nov 2026
        self.groq_model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
        self.llm_timeout_s = float(os.getenv("LLM_TIMEOUT_S", "12"))
        # after a provider fails, skip it for this many seconds before trying it again
        self.llm_cooldown_s = float(os.getenv("LLM_COOLDOWN_S", "300"))
        self.cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")]
        # empty = local SQLite file backend/app.db (see app/db/session.py)
        self.database_url = os.getenv("DATABASE_URL", "")
        # seconds to wait for a Postgres connection before giving up (per address), so an
        # unreachable database fails fast instead of hanging startup and requests
        self.db_connect_timeout_s = int(os.getenv("DB_CONNECT_TIMEOUT_S", "10"))
        # semantic search: fastembed = real model (downloaded once); hash = offline vectors for tests only
        self.embedder = os.getenv("EMBEDDER", "fastembed").strip().lower()
        if self.embedder not in EMBEDDERS:
            raise ValueError(f"EMBEDDER must be one of {', '.join(EMBEDDERS)}, got {self.embedder!r}")
        self.embed_model = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
        self.embed_cache_dir = Path(os.getenv("EMBED_CACHE_DIR", BACKEND_DIR / ".cache" / "fastembed"))
        # cached document vectors; rebuilt automatically when the corpus or the model changes
        self.index_dir = Path(os.getenv("INDEX_DIR", self.data_dir / "index"))


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_policy() -> dict:
    return yaml.safe_load((Path(__file__).parent / "policy.yaml").read_text(encoding="utf-8"))
