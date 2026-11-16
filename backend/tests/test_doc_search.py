"""Doc search (app/uc4/doc_search.py) and doc evidence items."""
import hashlib

import numpy as np
import pytest

from app.uc4.diagnose import run_code_steps
from app.uc4.doc_search import build_index, first_sentences, get_index, get_section, search, tokenize
from app.uc4.rank import rank_causes
from app.uc4.store import get_case, load_cases, logs_by_correlation_id

DEPRECATED = "legacy/rate-limits-v1"


@pytest.fixture(scope="module")
def all_runs() -> dict:
    return {cid: run_code_steps(case) for cid, case in load_cases().items()}


def test_tokenizer_keeps_error_codes_and_status_numbers() -> None:
    tokens = tokenize("429 Too Many Requests ERR_RATE_LIMITED on GET /v1/inventory/{sku}")
    assert "429" in tokens and "err_rate_limited" in tokens
    assert {"rate", "limited"} <= set(tokens)  # parts too, so prose "rate limit" still matches
    assert "on" not in tokens  # stop word


def test_deprecated_is_excluded_by_default_and_found_when_asked() -> None:
    query = "rate limit requests per minute"
    assert all(h.doc_id != DEPRECATED for h in search(query, k=55))
    assert any(h.doc_id == DEPRECATED for h in search(query, k=5, include_deprecated=True))


def test_hits_carry_section_metadata() -> None:
    hit = search("429 Too Many Requests ERR_RATE_LIMITED", k=1)[0]
    assert hit.section_id.startswith("doc:") and hit.doc_id and hit.heading
    assert hit.status == "current" and hit.version and hit.rank == 1 and hit.score > 0


def test_doc_id_filter_limits_to_one_document() -> None:
    hits = search("429 Too Many Requests ERR_RATE_LIMITED", k=3, doc_id="troubleshooting")
    assert hits and all(h.doc_id == "troubleshooting" for h in hits)


class FakeEmbed:
    """Deterministic bag-of-words vectors, so the hybrid path is tested offline."""

    def __call__(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), 64), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in tokenize(text):
                out[row, int(hashlib.md5(token.encode()).hexdigest(), 16) % 64] += 1.0
        return out


def test_hybrid_fuses_both_rankings_with_rrf() -> None:
    idx = build_index(embed=FakeEmbed())
    assert idx.mode == "hybrid"
    query = "429 Too Many Requests ERR_RATE_LIMITED"
    hybrid = search(query, k=5, method="hybrid", index=idx)
    bm25 = {h.section_id: h.rank for h in search(query, k=55, method="bm25", index=idx)}
    dense = {h.section_id: h.rank for h in search(query, k=55, method="dense", index=idx)}
    top = hybrid[0]
    assert top.score == pytest.approx(1 / (60 + bm25[top.section_id]) + 1 / (60 + dense[top.section_id]), abs=1e-6)
    assert top.dense_score is not None and top.mode == "hybrid"
    assert all(h.doc_id != DEPRECATED for h in hybrid)


def test_first_sentences_quotes_the_start_of_a_section() -> None:
    text = get_section("doc:rate-limits#1").text
    quote = first_sentences(text, 1)
    assert quote.startswith("Each API key may send 100 requests per minute")
    assert "*" not in quote and "\n" not in quote


def test_429_case_cites_rate_limits_and_never_the_legacy_page(all_runs) -> None:
    docs = [e for e in all_runs["UC4-0038"].evidence if e.kind == "doc"]
    assert any(e.data["doc_id"] == "rate-limits" for e in docs)
    assert 1 <= len(docs) <= 3
    for e in docs:
        assert e.id == e.data["section_id"] and e.id.startswith("doc:")
        assert f'v{e.data["version"]}' in e.text and e.data["heading"] in e.text
    for cid, run in all_runs.items():
        assert all(e.data.get("doc_id") != DEPRECATED for e in run.evidence if e.kind == "doc"), cid


def test_doc_items_do_not_change_the_ranking(all_runs) -> None:
    for cid, run in all_runs.items():
        without = [e for e in run.evidence if e.kind != "doc"]
        a = rank_causes(run.signals, run.evidence)
        b = rank_causes(run.signals, without)
        assert [(r.cause, r.confidence, r.status) for r in a] == [(r.cause, r.confidence, r.status) for r in b], cid
        # and no signal is ever linked to a doc item
        assert not any(i.startswith("doc:") for r in a for link in r.supporting + r.contradicting
                       for i in link.evidence_ids), cid


def test_doc_query_uses_route_status_code_and_upstream() -> None:
    from app.uc4.evidence import doc_queries
    case = get_case("UC4-0050")
    row = logs_by_correlation_id(case.focal_correlation_id)[0]
    error_query, full_query = doc_queries(row, case.route)
    assert error_query.startswith("504 Gateway Timeout ERR_UPSTREAM_TIMEOUT") and "orders-db" in error_query
    assert full_query.endswith(case.route)


def test_tests_run_offline_with_bm25() -> None:
    assert get_index().mode == "bm25"  # conftest.py switches embeddings off for tests
