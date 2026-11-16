"""No evidence, for any case, contains a token, a full API key or an email."""
import json
import re

import pytest

from app.uc4.evidence import collect_evidence, mask_ip, scrub
from app.uc4.store import get_case, load_cases

JWT = re.compile(r"eyJ[A-Za-z0-9_-]{5,}")
FULL_KEY = re.compile(r"nvp_(live|test)_[A-Za-z0-9]{4,}")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
FULL_IP = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")


@pytest.fixture(scope="module")
def all_evidence() -> dict:
    return {cid: collect_evidence(case) for cid, case in load_cases().items()}


def test_covers_all_90_cases(all_evidence) -> None:
    assert len(all_evidence) == 90


def test_no_secret_in_any_evidence_text_or_data(all_evidence) -> None:
    for case_id, items in all_evidence.items():
        for item in items:
            for blob in (item.text, json.dumps(item.data, default=str)):
                for name, pattern in (("JWT", JWT), ("full key", FULL_KEY), ("email", EMAIL),
                                      ("full IP", FULL_IP)):
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


def test_error_messages_with_emails_are_masked(all_evidence) -> None:
    # 38 raw error messages echo a customer email; they must reach evidence masked.
    masked = [item for items in all_evidence.values() for item in items
              if item.kind == "request" and "<email>" in (item.data["error_message"] or "")]
    assert masked


def test_mask_ip_hides_the_last_part() -> None:
    assert mask_ip("203.0.113.42") == "203.0.113.x"
    assert mask_ip(None) is None
    assert mask_ip("not-an-ip") == "<ip>"


def test_ip_not_allowlisted_cases_show_the_masked_ip() -> None:
    # Labels pick the cases only; collect_evidence never reads them.
    cases = [c for c in load_cases().values() if c.expected_cause == "ip_not_allowlisted"]
    assert cases
    for case in cases:
        request = next(i for i in collect_evidence(case) if i.kind == "request")
        assert request.data["client_ip_allowlisted"] is False
        assert request.data["client_ip_masked"].endswith(".x")
        assert "NOT allowlisted" in request.text


def test_focal_request_records_masked_ip() -> None:
    request = next(i for i in collect_evidence(get_case("UC4-0050")) if i.kind == "request")
    assert request.data["client_ip_masked"].endswith(".x")
