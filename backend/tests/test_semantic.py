"""Semantic search: RRF fusion, filters, the on-disk vector cache and the cosine-based gate signal.
Runs with the offline hash embedder (EMBEDDER=hash in conftest.py), so no model is downloaded."""
import csv
import json

import numpy as np
import pytest

from app.config import get_policy
from app.contracts import SearchFilters, TicketIn
from app.pipeline.embed import HashEmbedder
from app.pipeline.gate import retrieval_threshold
from app.pipeline.orchestrator import analyse
from app.pipeline.redact import redact
from app.pipeline.retrieve import Index, clean_query, get_index, rrf


# ---------- RRF ----------
def test_rrf_combines_two_rankings():
    # k=60: A = 1/61 + 1/62, C = 1/63 + 1/61, B = 1/62, D = 1/63
    fused = rrf([["A", "B", "C"], ["C", "A", "D"]], k=60)
    assert [i for i, _ in fused] == ["A", "C", "B", "D"]
    assert dict(fused)["A"] == pytest.approx(1 / 61 + 1 / 62)
    assert dict(fused)["D"] == pytest.approx(1 / 63)


def test_rrf_prefers_agreement_over_one_first_place():
    # X is 1st in one list only; Y is 2nd in both -> Y wins (1/62 + 1/62 > 1/61)
    fused = rrf([["X", "Y"], ["Z", "Y"]], k=60)
    assert fused[0][0] == "Y"


# ---------- hybrid search ----------
def test_filters_still_apply_in_every_mode():
    f = SearchFilters(application="Active Directory", date_from="2026-01-01")
    for mode in ("bm25", "dense", "hybrid"):
        hits = get_index().rank("password expired cannot log in", top_k=20, filters=f, mode=mode)
        assert hits, mode
        for m, _ in hits:
            assert m.metadata["application"] == "Active Directory", mode
            assert m.metadata["created_at"][:10] >= "2026-01-01", mode


def test_matches_carry_ranks_and_cosine_without_changing_the_corpus():
    index = get_index()
    m, cosine = index.search("GlobalProtect VPN certificate error", top_k=1)[0]
    for key in ("bm25_rank", "dense_rank", "cosine", "rrf_score", "coverage"):
        assert key in m.metadata
    assert m.metadata["cosine"] == cosine
    assert all("cosine" not in d["metadata"] for d in index.docs)  # metadata was copied, not modified


def test_strength_is_cosine_of_the_best_fused_match():
    index = get_index()
    query = "Outlook keeps asking for my password after I changed it this morning"
    best, strength = index.search(query, top_k=3)[0]
    doc = next(i for i, d in enumerate(index.docs) if d["source_id"] == best.source_id)
    expected = float(index.embedder.embed([clean_query(query)])[0] @ index.vectors[doc])
    assert strength == round(expected, 3)


def test_pipeline_uses_cosine_as_retrieval_signal_and_keeps_coverage_in_trace():
    ticket = TicketIn(title="VPN not connecting", description="GlobalProtect shows certificate error from home.")
    r = analyse(ticket, None)
    text = redact(f"{ticket.title}. {ticket.description}")[0]
    best, cosine = get_index().search(text, top_k=1)[0]
    assert r.signals["retrieval"] == cosine
    detail = next(e.detail for e in r.trace if e.step == "retrieve")
    assert detail["retrieval_strength"] == cosine and detail["embedder"] == "hash-512"
    assert detail["keyword_coverage"] == best.metadata["coverage"]


def test_missing_threshold_for_embedder_is_a_clear_error():
    assert retrieval_threshold(get_policy(), "hash-512") == get_policy()["gate"]["min_retrieval_strength"]["hash-512"]
    with pytest.raises(KeyError, match="no threshold for embedder 'some/other-model'"):
        retrieval_threshold(get_policy(), "some/other-model")


def test_hash_embedder_is_deterministic_and_normalised():
    a = HashEmbedder().embed(["vpn certificate error", ""])
    b = HashEmbedder().embed(["vpn certificate error", ""])
    assert np.array_equal(a, b)
    assert np.linalg.norm(a[0]) == pytest.approx(1.0) and not a[1].any()  # empty text -> zero vector, no NaN


# ---------- vector cache ----------
class CountingEmbedder(HashEmbedder):
    def __init__(self, name: str = "counting") -> None:
        super().__init__()
        self.name = name
        self.embedded = 0

    def embed(self, texts):
        self.embedded += len(texts)
        return super().embed(texts)


FIELDS = ["ticket_id", "title", "description", "resolution_notes", "category", "subcategory", "priority",
          "application", "environment", "assignment_group", "status", "created_at"]


def write_corpus(data_dir, third_description="Printer queue stuck"):
    rows = [("INC1", "VPN cert error", "GlobalProtect certificate invalid", "Re-enrolled cert."),
            ("INC2", "Outlook password prompt", "Outlook asks for password again", "Cleared credentials."),
            ("INC3", "Printer", third_description, "Restarted spooler.")]
    data_dir.mkdir(parents=True, exist_ok=True)
    with (data_dir / "historical_tickets.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for tid, title, desc, notes in rows:
            w.writerow(dict(ticket_id=tid, title=title, description=desc, resolution_notes=notes, category="c",
                            subcategory="s", priority="P3", application="a", environment="prod",
                            assignment_group="g", status="Resolved", created_at="2026-01-01T00:00"))
    (data_dir / "kb_articles.json").write_text(json.dumps([]), encoding="utf-8")


def test_vectors_are_cached_and_rebuilt_when_the_corpus_changes(tmp_path):
    data, cache = tmp_path / "data", tmp_path / "index"
    write_corpus(data)

    first = CountingEmbedder()
    built = Index(data_dir=data, index_dir=cache, embedder=first)
    assert built.vectors_rebuilt and first.embedded == 3 and built.cache_path.exists()

    second = CountingEmbedder()
    loaded = Index(data_dir=data, index_dir=cache, embedder=second)
    assert not loaded.vectors_rebuilt and second.embedded == 0          # loaded from disk, nothing embedded
    assert np.array_equal(loaded.vectors, built.vectors)

    write_corpus(data, third_description="Printer queue stuck and jobs vanish")  # corpus changed
    third = CountingEmbedder()
    rebuilt = Index(data_dir=data, index_dir=cache, embedder=third)
    assert rebuilt.vectors_rebuilt and third.embedded == 3
    assert rebuilt.corpus_key() != built.corpus_key()

    other_model = CountingEmbedder(name="other-model")                  # model changed
    assert Index(data_dir=data, index_dir=cache, embedder=other_model).vectors_rebuilt


def test_corrupt_cache_is_rebuilt(tmp_path):
    data, cache = tmp_path / "data", tmp_path / "index"
    write_corpus(data)
    path = Index(data_dir=data, index_dir=cache, embedder=CountingEmbedder()).cache_path
    path.write_bytes(b"not a numpy file")
    assert Index(data_dir=data, index_dir=cache, embedder=CountingEmbedder()).vectors_rebuilt
