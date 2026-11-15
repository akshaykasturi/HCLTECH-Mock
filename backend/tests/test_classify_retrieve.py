"""Behaviour the evaluation relies on: honest classifier confidence and filler-proof retrieval strength."""
from app.config import get_policy
from app.pipeline.classify import classify, knn_vote
from app.pipeline.gate import retrieval_threshold
from app.pipeline.redact import redact
from app.pipeline.retrieve import get_index


def test_known_ticket_is_classified_confidently():
    c = classify("GlobalProtect VPN shows certificate error when connecting from home")
    assert (c.category, c.subcategory) == ("Network", "VPN")
    assert c.confidence > 0.7 and c.method == "calibrated_logreg"


def test_unknown_problem_gets_low_confidence_unlike_knn():
    text = "My ID badge does not open the office main door anymore."
    assert classify(text).confidence < 0.5
    assert knn_vote(text).confidence > classify(text).confidence  # the baseline is over-confident


def test_filler_words_do_not_weaken_a_good_match():
    index, threshold = get_index(), retrieval_threshold(get_policy())  # threshold of the active embedder
    match, strength = index.search("GlobalProtect certificate error. Started yesterday, manager approved, "
                                   "I already restarted my laptop, kindly assist", top_k=1)[0]
    assert strength >= threshold                      # still passes the gate
    assert "certificate" in match.title.lower()       # still finds the right fix


def test_redaction_placeholders_do_not_change_retrieval():
    # the same ticket, once with personal data and once without: only the PII differs
    ticket = "VPN not connecting. GlobalProtect shows certificate error from home. Worked last week. {} {} {}"
    plain, _ = redact(ticket.format("", "", ""))
    with_pii, counts = redact(ticket.format("demo.user@example.com", "9876543210", "10.1.2.3"))
    assert counts == {"email": 1, "phone": 1, "ip": 1} and "[EMAIL]" in with_pii
    a, b = get_index().search(plain, top_k=5), get_index().search(with_pii, top_k=5)
    assert b[0][1] == a[0][1]                                   # same retrieval strength
    assert [m.source_id for m, _ in b] == [m.source_id for m, _ in a]


def test_unrelated_text_has_weak_retrieval_strength():
    threshold = retrieval_threshold(get_policy())  # was a hard-coded 0.45 before thresholds became per-embedder
    assert get_index().search("server room air conditioning is beeping", top_k=1)[0][1] < threshold
