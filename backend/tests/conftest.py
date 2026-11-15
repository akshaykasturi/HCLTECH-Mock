"""Set before the app is imported:
- tests never call a real LLM, even if backend/.env has keys;
- tests use their own temporary SQLite database, never backend/app.db;
- tests use the offline hash embedder (never download a model) and a temporary vector cache."""
import os
import shutil
import tempfile
from pathlib import Path

os.environ["LLM_PROVIDER"] = "extractive"
os.environ["EMBEDDER"] = "hash"

_TEST_DB_DIR = Path(tempfile.mkdtemp(prefix="ticket-assistant-test-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TEST_DB_DIR / 'test.db').as_posix()}"
os.environ["INDEX_DIR"] = str(_TEST_DB_DIR / "index")


def pytest_sessionfinish(session, exitstatus):
    from app.db.session import get_engine

    if get_engine.cache_info().currsize:
        get_engine().dispose()  # release the file so Windows lets us delete it
    shutil.rmtree(_TEST_DB_DIR, ignore_errors=True)
