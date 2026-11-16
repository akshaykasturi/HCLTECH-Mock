"""No evidence, for any case, contains a token, a full API key or an email."""
import json
import re

import pytest

from app.uc4.evidence import collect_evidence, scrub
from app.uc4.store import load_cases

JWT = re.compile(r"eyJ[A-Za-z0-9_-]{5,}")
FULL_KEY = re.compile(r"nvp_(live|test)_[A-Za-z0-9]{4,}")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


@pytest.fixture(scope="module")
def all_evidence() -> dict:
    return {cid: collect_evidence(case) for cid, case in load_cases().items()}


def test_covers_all_90_cases(all_evidence) -> None:
    assert len(all_evidence) == 90


def test_no_secret_in_any_evidence_text_or_data(all_evidence) -> None:
    for case_id, items in all_evidence.items():
        for item in items:
            for blob in (item.text, json.dumps(item.data, default=str)):
                for name, pattern in (("JWT", JWT), ("full key", FULL_KEY), ("email", EMAIL)):
                    # report only where it is, never the matched value
                    assert not pattern.search(blob), f"{name} in {case_id} {item.id}"


def test_key_prefix_alone_is_kept(all_evidence) -> None:
    prefixes = {item.data.get("key_prefix") for items in all_evidence.values()
                for item in items if item.kind == "request"}
    assert "nvp_live" in prefixes


def test_scrub_masks_free_text() -> None:
    # Made-up values, built from pieces so secret scanners don't flag this file.
    fake_jwt = "eyJ" + "abcdef.ghijkl.mnopqr"
    fake_key = "nvp_live_" + "ABCdef123"
    text = f"token {fake_jwt} key {fake_key} mail a.b@example.com ip 203.0.113.9"
    out = scrub(text)
    assert not JWT.search(out) and not FULL_KEY.search(out) and not EMAIL.search(out)
    assert "203.0.113.9" not in out
