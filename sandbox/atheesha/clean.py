"""Clean messy IT tickets: data/raw_tickets.csv -> data/clean_tickets.csv."""
import csv
import html
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
RAW_PATH = BASE / "data" / "raw_tickets.csv"
CLEAN_PATH = BASE / "data" / "clean_tickets.csv"
FIELDS = ["id", "title", "description", "application", "created_at"]

TAG_RE = re.compile(r"<[^>]+>")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Candidate phone numbers: optional +country code, optional (area), then 2+ digit groups.
# A candidate is only redacted if it has 9-15 digits, so short codes like "F5 201",
# "company code 1000" or dates are left alone.
PHONE_RE = re.compile(
    r"(?<![\w+])(?:\+\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)[\s.-]?)?\d{2,5}(?:[\s.-]?\d{2,5}){1,3}(?!\w)"
)

# Numeric slash/dash dates are interpreted day-first (DD/MM/YYYY).
DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d %B %Y",
    "%d %b %Y",
]


def normalize_ws(text):
    """Collapse all whitespace (spaces, tabs, newlines, nbsp) to single spaces."""
    return " ".join((text or "").split())


def strip_markup(text):
    """Remove HTML tags, unescape entities, normalize whitespace."""
    text = TAG_RE.sub(" ", text or "")
    text = html.unescape(text)
    return normalize_ws(text)


def _phone_sub(match):
    digits = sum(ch.isdigit() for ch in match.group())
    return "<PHONE>" if 9 <= digits <= 15 else match.group()


def redact(text):
    text = EMAIL_RE.sub("<EMAIL>", text)
    return PHONE_RE.sub(_phone_sub, text)


def clean_text(text):
    return redact(strip_markup(text))


def parse_date(value):
    """Return YYYY-MM-DD, or None if the value matches no known format."""
    value = normalize_ws(value)
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def dedup_key(title, description):
    """Lowercased, whitespace-collapsed title+description (before redaction)."""
    return normalize_ws(f"{strip_markup(title)} {strip_markup(description)}").lower()


def clean_rows(raw_rows):
    """Clean and de-duplicate rows. Returns (kept_rows, Counter of drop reasons)."""
    dropped = Counter()
    seen_raw = set()
    seen_keys = set()
    kept = []
    for row in raw_rows:
        raw_sig = tuple(row.get(f) or "" for f in FIELDS)
        if raw_sig in seen_raw:
            dropped["exact duplicate"] += 1
            continue
        seen_raw.add(raw_sig)

        description = clean_text(row.get("description"))
        if not description:
            dropped["empty description"] += 1
            continue

        key = dedup_key(row.get("title"), row.get("description"))
        if key in seen_keys:
            dropped["near duplicate"] += 1
            continue
        seen_keys.add(key)

        created = parse_date(row.get("created_at"))
        if created is None:
            print(f"WARNING: unparseable date {row.get('created_at')!r} for {row.get('id')}")
        kept.append({
            "id": normalize_ws(row.get("id")),
            "title": clean_text(row.get("title")),
            "description": description,
            "application": normalize_ws(row.get("application")).upper(),
            "created_at": created or "",
        })
    return kept, dropped


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    raw = read_csv(RAW_PATH)
    kept, dropped = clean_rows(raw)
    write_csv(CLEAN_PATH, kept)

    print(f"Rows in:      {len(raw)}")
    print(f"Rows dropped: {sum(dropped.values())}")
    for reason, count in dropped.items():
        print(f"  - {reason}: {count}")
    print(f"Rows out:     {len(kept)}")
    print(f"Wrote {CLEAN_PATH.relative_to(BASE)}")


if __name__ == "__main__":
    main()
