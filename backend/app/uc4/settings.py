"""Read app/uc4/settings.yaml once."""
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

BACKEND_DIR = Path(__file__).resolve().parents[2]
SETTINGS_FILE = Path(__file__).with_name("settings.yaml")


@lru_cache(maxsize=1)
def get_settings() -> dict[str, Any]:
    """Return the parsed settings.yaml (loaded on first call, then cached)."""
    with open(SETTINGS_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def data_path(name: str) -> Path:
    """Absolute path of a data file named in settings.yaml (cases, logs, metrics, changes)."""
    return BACKEND_DIR / get_settings()["data"][name]
