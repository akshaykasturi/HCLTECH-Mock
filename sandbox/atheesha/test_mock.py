import pytest

import chunk
import clean


def row(id_, title, description, app="sap fi", date="2026-01-05"):
    return {"id": id_, "title": title, "description": description,
            "application": app, "created_at": date}


@pytest.fixture(scope="module")
def cleaned():
    kept, dropped = clean.clean_rows(clean.read_csv(clean.RAW_PATH))
    return kept, dropped


@pytest.fixture(scope="module")
def chunks(cleaned):
    return chunk.make_chunks(cleaned[0])


# --- redaction -------------------------------------------------------------

def test_redaction_emails_and_phones():
    text = ("Mail john.doe@acme.com or FINANCE.TEAM@ACME.CO.UK, call +1 (555) 123-4567, "
            "555-987-6543, +91 98765 43210 or 020 7946 0958.")
    out = clean.clean_text(text)
    assert out.count("<EMAIL>") == 2
    assert out.count("<PHONE>") == 4
    assert "@" not in out
    assert not any(ch.isdigit() for ch in out)


def test_redaction_leaves_short_numbers_alone():
    text = "Error F5 201 for company code 1000, PO 45001234, period 12."
    assert clean.clean_text(text) == text


def test_no_pii_in_cleaned_dataset(cleaned):
    for r in cleaned[0]:
        for field in ("title", "description"):
            assert "@" not in r[field]
            assert not clean.EMAIL_RE.search(r[field])


def test_html_and_whitespace_cleaned():
    out = clean.clean_text("  Q&amp;A <b>urgent</b><br/>line\n\n two\t\tthree&nbsp;x ")
    assert out == "Q&A urgent line two three x"


# --- duplicates & empty rows ---------------------------------------------------

def test_exact_and_near_duplicates_removed():
    rows = [
        row("T1", "Cannot post invoice", "Error F5 201 <br>on posting."),
        row("T1", "Cannot post invoice", "Error F5 201 <br>on posting."),   # exact
        row("T2", "  cannot POST invoice ", "error f5 201\n on   posting."),  # near
        row("T3", "Different ticket", "Something else."),
    ]
    kept, dropped = clean.clean_rows(rows)
    assert [r["id"] for r in kept] == ["T1", "T3"]
    assert dropped["exact duplicate"] == 1
    assert dropped["near duplicate"] == 1


def test_dataset_duplicates_removed(cleaned):
    kept, dropped = cleaned
    assert dropped["exact duplicate"] == 2
    assert dropped["near duplicate"] == 1
    ids = [r["id"] for r in kept]
    assert len(ids) == len(set(ids))
    assert "T007" not in ids  # near-duplicate of T001
    keys = [clean.dedup_key(r["title"], r["description"]) for r in kept]
    assert len(keys) == len(set(keys))


def test_empty_description_dropped(cleaned):
    rows = [row("A", "Has text", "ok"), row("B", "Empty", "   "), row("C", "Only tags", "<br/>&nbsp;")]
    kept, dropped = clean.clean_rows(rows)
    assert [r["id"] for r in kept] == ["A"]
    assert dropped["empty description"] == 2

    kept, dropped = cleaned
    assert dropped["empty description"] == 1
    assert "T005" not in [r["id"] for r in kept]
    assert all(r["description"] for r in kept)


def test_applications_and_dates_standardized(cleaned):
    for r in cleaned[0]:
        assert r["application"] == r["application"].upper().strip()
        assert clean.parse_date(r["created_at"]) == r["created_at"]  # already YYYY-MM-DD
    assert clean.parse_date("05/01/2026") == "2026-01-05"
    assert clean.parse_date("Jan 7, 2026") == "2026-01-07"
    assert clean.parse_date("2026-01-09T10:15:00") == "2026-01-09"


# --- chunking ------------------------------------------------------------------

def test_chunks_never_exceed_40_words(chunks):
    assert len(chunks) > len(set(c["ticket_id"] for c in chunks))  # some multi-chunk tickets
    for c in chunks:
        assert 1 <= len(c["text"].split()) <= 40
    long_text = " ".join(f"w{i}" for i in range(137))
    assert all(len(t.split()) <= 40 for t in chunk.split_words(long_text))


def test_overlap_is_correct_and_no_words_cut():
    assert chunk.OVERLAP == 5
    words = [f"w{i}" for i in range(100)]
    parts = [p.split() for p in chunk.split_words(" ".join(words))]
    # step = 40 - 5 = 35 -> chunks start at w0, w35, w70
    assert [p[0] for p in parts] == ["w0", "w35", "w70"]
    for a, b in zip(parts, parts[1:]):
        assert a[-5:] == b[:5]
        assert a[-6] != b[0]  # overlap is exactly 5, not more
    # every chunk is a contiguous slice of whole words, and together they cover the text
    rebuilt = parts[0] + [w for p in parts[1:] for w in p[5:]]
    assert rebuilt == words


def test_overlap_on_dataset(chunks):
    by_ticket = {}
    for c in chunks:
        by_ticket.setdefault(c["ticket_id"], []).append(c["text"].split())
    multi = [parts for parts in by_ticket.values() if len(parts) > 1]
    assert multi
    for parts in multi:
        for a, b in zip(parts, parts[1:]):
            assert len(a) == 40
            assert a[-5:] == b[:5]


def test_short_text_single_chunk():
    assert chunk.split_words("just a few words") == ["just a few words"]
    assert chunk.split_words("   ") == []


def test_chunk_ids_unique(chunks):
    ids = [c["chunk_id"] for c in chunks]
    assert len(ids) == len(set(ids))
    for c in chunks:
        assert c["chunk_id"].startswith(c["ticket_id"] + "-c")
        assert set(c) == {"chunk_id", "ticket_id", "application", "created_at", "text"}
