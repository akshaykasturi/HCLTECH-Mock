"""Secret masking (app/uc4/redact.py): unit cases, no mutation, and the full request log.

Fake secrets are built from pieces so secret scanners don't flag this file, and no test
message ever contains a secret value (only kinds and counts).
"""
import copy
import json
from collections import Counter
from pathlib import Path

from app.uc4.redact import find_leaks, hash_idempotency_key, mask_record, mask_text

FAKE_JWT = "eyJ" + "hbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiJmYWtlIn0" + "." + "c2lnbmF0dXJlX2Zha2U"
FAKE_LIVE = "nvp_live_" + "AbC123dEf456"
FAKE_TEST = "nvp_test_" + "ZyX987wVu654"
FAKE_MAIL = "jane.doe" + "@" + "example.com"

LOG = Path(__file__).resolve().parents[1] / "data" / "raw" / "uc4" / "logs" / "requests.jsonl"


# --- mask_text, one kind at a time ------------------------------------------------------

def test_bearer_token_in_header_text() -> None:
    out, counts = mask_text(f"Bearer {FAKE_JWT}")
    assert out == "Bearer <TOKEN>"
    assert counts == {"bearer_token": 1}


def test_token_inside_error_message() -> None:
    out, counts = mask_text(f"rejected: Authorization was 'Bearer {FAKE_JWT}' (expired)")
    assert out == "rejected: Authorization was 'Bearer <TOKEN>' (expired)"
    assert counts == {"bearer_token": 1}


def test_bare_jwt_without_bearer() -> None:
    out, counts = mask_text(f"token={FAKE_JWT};")
    assert out == "token=<TOKEN>;"
    assert counts == {"bearer_token": 1}


def test_api_keys_keep_their_prefix() -> None:
    out, counts = mask_text(f"live {FAKE_LIVE} test {FAKE_TEST}")
    assert out == "live nvp_live_<KEY> test nvp_test_<KEY>"
    assert counts == {"api_key_live": 1, "api_key_test": 1}


def test_email_inside_error_message() -> None:
    out, counts = mask_text(f"field 'customer' is invalid (received customer_email={FAKE_MAIL})")
    assert out == "field 'customer' is invalid (received customer_email=<EMAIL>)"
    assert counts == {"email": 1}


def test_ip_keeps_the_slash_24() -> None:
    out, counts = mask_text("source ip 203.0.113.24 is not allowlisted.")
    assert out == "source ip 203.0.113.x is not allowlisted."
    assert counts == {"ip": 1}


def test_text_without_secrets_is_unchanged() -> None:
    text = ("Bearer token expired after 3600 s; upstream timeout (p95=850, timeout=1000); "
            "version 1.2.3.4.5, scope 'payments:write', key_prefix nvp_live, 999.1.2.3")
    out, counts = mask_text(text)
    assert out == text
    assert counts == {}
    assert find_leaks(text) == []


# --- mask_record -------------------------------------------------------------------------

def _fake_record() -> dict:
    return {
        "correlation_id": "c-0001",
        "client_ip": "198.51.100.7",
        "status": 401,
        "latency_ms": 42,
        "request_headers": {
            "Authorization": f"Bearer {FAKE_JWT}",
            "X-Api-Key": FAKE_TEST,
            "Idempotency-Key": "idem_" + "abcdef0123456789",
            "User-Agent": "acme-sdk/1.4 (python)",
        },
        "error": {"code": "invalid_request", "message": f"bad customer_email={FAKE_MAIL}"},
        "auth": {"method": "bearer", "key_prefix": "nvp_test", "token_age_s": 7300,
                 "scopes": ["payments:read"]},
    }


def test_record_is_masked_structurally() -> None:
    masked, counts = mask_record(_fake_record())
    h = masked["request_headers"]
    assert h["Authorization"] == "Bearer <TOKEN>"
    assert h["X-Api-Key"] == "nvp_test_<KEY>"
    assert h["Idempotency-Key"] == hash_idempotency_key("idem_" + "abcdef0123456789")
    assert h["User-Agent"] == "acme-sdk/1.4 (python)"
    assert masked["client_ip"] == "198.51.100.x"
    assert masked["error"]["message"] == "bad customer_email=<EMAIL>"
    assert counts == {"bearer_token": 1, "api_key_test": 1, "idempotency_key": 1,
                      "ip": 1, "email": 1}
    assert find_leaks(json.dumps(masked)) == []


def test_non_secret_fields_are_kept() -> None:
    original = _fake_record()
    masked, _ = mask_record(original)
    for key in ("correlation_id", "status", "latency_ms", "auth"):
        assert masked[key] == original[key], key


def test_input_record_is_not_mutated() -> None:
    record = _fake_record()
    snapshot = copy.deepcopy(record)
    mask_record(record)
    unchanged = record == snapshot  # compared outside assert so a failure prints no values
    assert unchanged, "mask_record changed its input"


def test_unknown_api_key_format_is_fully_hidden() -> None:
    masked, counts = mask_record({"headers": {"x-api-key": "sk" + "-whatever-1234"}})
    assert masked["headers"]["x-api-key"] == "<KEY>"
    assert counts == {"api_key_other": 1}


# --- Idempotency-Key hashing -------------------------------------------------------------

def test_same_idempotency_key_same_hash() -> None:
    a = hash_idempotency_key("idem_" + "retry-me-123")
    assert a == hash_idempotency_key("idem_" + "retry-me-123")
    assert a.startswith("idem_") and len(a) == len("idem_") + 8
    assert "retry-me-123" not in a


def test_different_idempotency_keys_differ() -> None:
    assert hash_idempotency_key("idem_" + "one") != hash_idempotency_key("idem_" + "two")


# --- find_leaks --------------------------------------------------------------------------

def test_find_leaks_names_kinds_only() -> None:
    text = f"{FAKE_JWT} {FAKE_LIVE} {FAKE_TEST} {FAKE_MAIL} 192.0.2.10"
    assert find_leaks(text) == ["api_key_live", "api_key_test", "bearer_token", "email", "ip"]
    assert find_leaks(mask_text(text)[0]) == []


# --- the real request log ----------------------------------------------------------------

def test_full_request_log_is_masked_and_counts_match_data_card() -> None:
    totals: Counter[str] = Counter()
    raw_idem: set[str] = set()
    hashed_idem: set[str] = set()
    with LOG.open(encoding="utf-8") as f:  # read only, never written
        for line_no, line in enumerate(f, start=1):
            record = json.loads(line)
            masked, counts = mask_record(record)
            totals.update(counts)
            leaks = find_leaks(json.dumps(masked))
            assert leaks == [], f"line {line_no} still has: {leaks}"
            key = record["request_headers"].get("Idempotency-Key")
            if key is not None:
                raw_idem.add(key)
                hashed_idem.add(masked["request_headers"]["Idempotency-Key"])

    # Numbers from backend/data/eval/uc4/DATA_CARD.md, "Sensitive data, on purpose".
    expected = {"bearer_token": 3056, "api_key_live": 2923, "api_key_test": 72, "email": 38}
    got = {kind: totals.get(kind, 0) for kind in expected}
    assert got == expected
    assert totals.get("api_key_other", 0) == 0
    # Repeated keys stay repeated, different keys stay different (no hash collisions).
    assert len(hashed_idem) == len(raw_idem)
