"""Chunk cleaned tickets: data/clean_tickets.csv -> data/chunks.jsonl."""
import csv
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
CLEAN_PATH = BASE / "data" / "clean_tickets.csv"
CHUNKS_PATH = BASE / "data" / "chunks.jsonl"

MAX_WORDS = 40
OVERLAP = 5


def split_words(text, max_words=MAX_WORDS, overlap=OVERLAP):
    """Split text on whitespace into word windows of <= max_words, sharing `overlap` words."""
    if not 0 <= overlap < max_words:
        raise ValueError("overlap must be >= 0 and < max_words")
    words = text.split()
    if not words:
        return []
    step = max_words - overlap
    chunks = []
    start = 0
    while True:
        chunks.append(" ".join(words[start:start + max_words]))
        if start + max_words >= len(words):
            break
        start += step
    return chunks


def build_text(row):
    title = row["title"].rstrip(" .")
    return f"{title}. {row['description']}"


def make_chunks(rows, max_words=MAX_WORDS, overlap=OVERLAP):
    chunks = []
    for row in rows:
        for n, text in enumerate(split_words(build_text(row), max_words, overlap), start=1):
            chunks.append({
                "chunk_id": f"{row['id']}-c{n}",
                "ticket_id": row["id"],
                "application": row["application"],
                "created_at": row["created_at"],
                "text": text,
            })
    return chunks


def main():
    with open(CLEAN_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    chunks = make_chunks(rows)
    with open(CHUNKS_PATH, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    print(f"Tickets read: {len(rows)}")
    print(f"Chunks written: {len(chunks)}")
    print(f"Wrote {CHUNKS_PATH.relative_to(BASE)}")


if __name__ == "__main__":
    main()
