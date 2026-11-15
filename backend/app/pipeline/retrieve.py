"""Step 3: find similar resolved tickets and approved KB articles.

Hybrid search: BM25 (exact words, good for error codes and product names) and dense vectors
(meaning, good for natural wording) each rank the corpus; Reciprocal Rank Fusion merges the two
rankings. Dense search is brute-force cosine with numpy: for ~1,200 documents that is exact and
takes about a millisecond, so no vector database is needed.

Retrieval strength (the gate signal) = cosine similarity between the ticket and the best fused match.
Keyword coverage is still computed and kept in each match's metadata as a diagnostic."""
import csv
import hashlib
import json
import os
import re
import threading
from functools import lru_cache
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from app.config import get_policy, get_settings
from app.contracts import Match, SearchFilters
from app.pipeline.embed import Embedder, get_embedder
from app.pipeline.redact import PATTERNS as REDACT_PATTERNS

STOPWORDS = set("""a an the and or but is are was were be been to of in on at for with my me i it this that
not can cant can't no do does did have has had from as by so if any all our we you your please help hi hello
team thanks dear just since still now get got its it's am im i'm""".split())

# Redaction placeholders such as [EMAIL] carry no meaning for search. Left in, "email" or "ip" would
# count as query words the matching ticket lacks, so the same ticket would look less similar just
# because it had an address in it. Built from redact.PATTERNS so the two lists cannot drift apart.
PLACEHOLDERS = re.compile(r"\[(?:" + "|".join(n.upper() for n in REDACT_PATTERNS) + r")\]")

MODES = ("bm25", "dense", "hybrid")


def tokenize(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS and len(w) > 1]


def clean_query(text: str) -> str:
    """Drop redaction placeholders and squeeze whitespace, so the same ticket with or without
    personal data gives exactly the same query for both BM25 and the embedder."""
    return " ".join(PLACEHOLDERS.sub(" ", text).split())


def rrf(rankings: list[list], k: int) -> list[tuple[object, float]]:
    """Reciprocal Rank Fusion. Each ranking lists ids best-first; an id's score is the sum over the
    rankings it appears in of 1 / (k + rank), rank starting at 1. Large k (60 is the usual choice)
    flattens the curve, so being near the top of both lists beats being first in only one.
    Returns (id, score) best-first; ties go to the id with the better best rank, then the smaller id."""
    scores: dict = {}
    best: dict = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
            best[item] = min(best.get(item, rank), rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], best[kv[0]], kv[0]))


def passes(meta: dict, f: SearchFilters) -> bool:
    for field in ("category", "application", "assignment_group", "environment", "status"):
        want = getattr(f, field)
        if want and meta.get(field, "").lower() != want.lower():
            return False
    created = meta.get("created_at", "")
    if f.date_from and (not created or created[:10] < f.date_from):
        return False
    if f.date_to and (not created or created[:10] > f.date_to):
        return False
    return True


class Index:
    """Loads the corpus once: a BM25 index plus one embedding per document (cached on disk)."""

    def __init__(self, data_dir: Path | None = None, index_dir: Path | None = None,
                 embedder: Embedder | None = None) -> None:
        settings, policy = get_settings(), get_policy()
        data_dir = data_dir or settings.data_dir
        self.index_dir = index_dir or settings.index_dir
        self.embedder = embedder or get_embedder()
        self.rrf_k = policy["retrieval"]["rrf_k"]
        self.candidates = policy["retrieval"]["candidates"]
        allowed = set(policy["retrieval"]["kb_statuses_allowed"])
        self.docs: list[dict] = []
        with (data_dir / "historical_tickets.csv").open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                self.docs.append(dict(
                    source_id=r["ticket_id"], source_type="ticket", title=r["title"],
                    search_text=f"{r['title']} {r['description']}", text=r["resolution_notes"],
                    metadata={k: r[k] for k in ("category", "subcategory", "priority", "application",
                                                "environment", "assignment_group", "status", "created_at")}))
        kb = json.loads((data_dir / "kb_articles.json").read_text(encoding="utf-8"))
        for a in kb:
            if a["status"] not in allowed:  # draft / superseded knowledge is never searchable
                continue
            steps = " ".join(a["steps"])
            self.docs.append(dict(
                source_id=a["kb_id"], source_type="kb", title=a["title"],
                search_text=f"{a['title']} {steps}", text=steps,
                metadata={"category": a["category"], "subcategory": a["subcategory"],
                          "application": a["application"], "status": a["status"]}))
        self.tokens = [tokenize(d["search_text"]) for d in self.docs]
        self.bm25 = BM25Okapi(self.tokens)
        self.max_idf = max(self.bm25.idf.values())  # unknown words count as the rarest possible
        self.vectors, self.vectors_rebuilt = self._load_or_build_vectors()

    # ---------- vector cache ----------
    def corpus_key(self) -> str:
        """Changes whenever a searchable text, the set of documents or the embedding model changes."""
        h = hashlib.sha256(self.embedder.name.encode())
        for d in self.docs:
            h.update(f"\0{d['source_id']}\0{d['search_text']}".encode())
        return h.hexdigest()

    @property
    def cache_path(self) -> Path:
        return self.index_dir / f"vectors-{re.sub(r'[^A-Za-z0-9]+', '_', self.embedder.name)}.npz"

    def _load_or_build_vectors(self) -> tuple[np.ndarray, bool]:
        key, path = self.corpus_key(), self.cache_path
        if path.exists():
            try:
                with np.load(path) as z:
                    if str(z["key"]) == key and z["vectors"].shape[0] == len(self.docs):
                        return z["vectors"], False
            except Exception:  # unreadable or old-format cache: rebuild it
                pass
        vectors = self.embedder.embed([d["search_text"] for d in self.docs])
        self.index_dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        with tmp.open("wb") as f:  # write then rename, so a crash never leaves half a cache
            np.savez(f, vectors=vectors, key=np.array(key), model=np.array(self.embedder.name))
        os.replace(tmp, path)
        return vectors, True

    # ---------- search ----------
    def coverage(self, q: list[str], i: int) -> float:
        """Share of the ticket's key words found in document i, each weighted by rarity (IDF).
        Kept as a diagnostic; the gate uses cosine similarity instead."""
        doc_words = set(self.tokens[i])
        weights = {w: max(self.bm25.idf.get(w, self.max_idf), 0.0) for w in set(q)}
        total = sum(weights.values()) or 1.0
        return round(sum(v for w, v in weights.items() if w in doc_words) / total, 3)

    def rank(self, query: str, top_k: int, filters: SearchFilters | None = None,
             mode: str = "hybrid") -> list[tuple[Match, float]]:
        """Returns (match, cosine) pairs best-first. mode = bm25 | dense | hybrid (RRF of both).
        Filters are applied to the candidates before ranking, so they hold in every mode."""
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        text = clean_query(query)
        q = tokenize(text)
        if not q:
            return []
        allowed = [not filters or passes(d["metadata"], filters) for d in self.docs]
        bm25_scores = self.bm25.get_scores(q)
        cosines = self.vectors @ self.embedder.embed([text])[0]
        bm25_order = [int(i) for i in np.argsort(-bm25_scores, kind="stable")
                      if allowed[i] and bm25_scores[i] > 0][:self.candidates]
        dense_order = [int(i) for i in np.argsort(-cosines, kind="stable") if allowed[i]][:self.candidates]
        fused = rrf([bm25_order, dense_order], self.rrf_k)
        if mode == "bm25":
            order = [(i, float(bm25_scores[i])) for i in bm25_order]
        elif mode == "dense":
            order = [(i, float(cosines[i])) for i in dense_order]
        else:
            order = fused
        bm25_pos = {i: r for r, i in enumerate(bm25_order, start=1)}
        dense_pos = {i: r for r, i in enumerate(dense_order, start=1)}
        rrf_score = dict(fused)
        out = []
        for i, score in order[:top_k]:
            d = self.docs[i]
            meta = {**d["metadata"],  # a copy: the corpus metadata itself is never modified
                    "bm25_rank": bm25_pos.get(i), "dense_rank": dense_pos.get(i),
                    "cosine": round(float(cosines[i]), 3), "rrf_score": round(rrf_score.get(i, 0.0), 5),
                    "coverage": self.coverage(q, i)}
            out.append((Match(source_id=d["source_id"], source_type=d["source_type"], title=d["title"],
                              text=d["text"], score=round(score, 5), metadata=meta),
                        round(float(cosines[i]), 3)))
        return out

    def search(self, query: str, top_k: int, filters: SearchFilters | None = None) -> list[tuple[Match, float]]:
        """Hybrid search. The float is the cosine similarity of each match; the first one is the
        retrieval strength the gate uses."""
        return self.rank(query, top_k, filters, mode="hybrid")


_index_lock = threading.Lock()  # warm-up and a first request must not both build the index


@lru_cache
def _build_index() -> Index:
    return Index()


def get_index() -> Index:
    with _index_lock:
        return _build_index()


def index_built() -> bool:
    """True once the shared index exists. Never waits, so /health can call it while warming up."""
    return _build_index.cache_info().currsize > 0
