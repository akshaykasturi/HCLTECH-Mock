"""Step 2: category, subcategory, priority and a confidence you can trust.

Main model: TF-IDF features + Logistic Regression, wrapped in probability calibration.
  - TF-IDF turns text into numbers: words that are frequent in this ticket but rare overall count most.
  - Logistic Regression learns which words point to which subcategory.
  - Calibration (CalibratedClassifierCV) adjusts the probabilities so "0.8" really means right ~80% of the time.
The category comes from the predicted subcategory (each subcategory belongs to exactly one category).

knn_vote() is the old baseline, kept so the evaluation can compare the two honestly.

Training takes ~1-2 s on a laptop but minutes on a small cloud CPU, so scripts/build_index.py trains
once at image build time and saves the models to data/index/classifier.joblib (git-ignored, never in
git). The file stores a hash of historical_tickets.csv + the scikit-learn version; it is only used
when both still match, otherwise the models are retrained (and the file rewritten). joblib files run
code when loaded, so only files this app wrote itself are ever loaded.
"""
import csv
import hashlib
import logging
import os
import threading
from collections import Counter
from pathlib import Path

import joblib
import sklearn
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, make_pipeline
from sklearn.feature_extraction.text import TfidfVectorizer

from app.config import get_settings
from app.contracts import Classification
from app.pipeline.retrieve import get_index

SEED = 42
MODEL_FILE = "classifier.joblib"
log = logging.getLogger("ticket-assistant")


def _features() -> FeatureUnion:
    # word pairs catch phrases ("account locked"); character pieces catch typos and codes ("0x80070643")
    return FeatureUnion([
        ("words", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
        ("chars", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=3, sublinear_tf=True)),
    ])


def _model():
    base = LogisticRegression(C=4.0, max_iter=2000, random_state=SEED)
    return make_pipeline(_features(), CalibratedClassifierCV(base, method="sigmoid", cv=5))


class TicketClassifier:
    def __init__(self, rows: list[dict]) -> None:
        texts = [f"{r['title']}. {r['description']}" for r in rows]
        self.parent = {r["subcategory"]: r["category"] for r in rows}
        self.sub_model = _model().fit(texts, [r["subcategory"] for r in rows])
        self.pri_model = _model().fit(texts, [r["priority"] for r in rows])

    def predict(self, text: str) -> Classification:
        sub_probs = self.sub_model.predict_proba([text])[0]
        best = sub_probs.argmax()
        subcategory = self.sub_model.classes_[best]
        pri_probs = self.pri_model.predict_proba([text])[0]
        return Classification(
            category=self.parent[subcategory], subcategory=subcategory,
            priority=self.pri_model.classes_[pri_probs.argmax()],
            confidence=round(float(sub_probs[best]), 3), method="calibrated_logreg")


def load_rows(data_dir: Path | None = None) -> list[dict]:
    with ((data_dir or get_settings().data_dir) / "historical_tickets.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def model_key(data_dir: Path) -> str:
    """Changes when the training data or the scikit-learn version changes (old pickles may not load)."""
    h = hashlib.sha256((data_dir / "historical_tickets.csv").read_bytes())
    h.update(f"\0sklearn={sklearn.__version__}".encode())
    return h.hexdigest()


def load_or_train(data_dir: Path | None = None, index_dir: Path | None = None) -> tuple[TicketClassifier, str]:
    """The saved classifier if its key matches, else a freshly trained one (saved for next time).
    Returns (classifier, "loaded" | "trained")."""
    settings = get_settings()
    data_dir, index_dir = data_dir or settings.data_dir, index_dir or settings.index_dir
    key, path = model_key(data_dir), index_dir / MODEL_FILE
    if path.exists():
        try:
            saved = joblib.load(path)
            if saved.get("key") == key:
                return saved["classifier"], "loaded"
        except Exception:  # unreadable or old-format file: retrain and overwrite it
            pass
    clf = TicketClassifier(load_rows(data_dir))
    try:
        index_dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        joblib.dump({"key": key, "sklearn": sklearn.__version__, "classifier": clf}, tmp)
        os.replace(tmp, path)  # write then rename, so a crash never leaves half a file
    except OSError as e:  # e.g. read-only filesystem: still serve the trained model
        log.warning("could not save classifier to %s: %s", path, e)
    return clf, "trained"


_classifier: TicketClassifier | None = None
_classifier_lock = threading.Lock()  # warm-up and a first request must not both train


def ensure_classifier() -> str:
    """Load or train the shared classifier once. Returns "loaded", "trained" or "already in memory"."""
    global _classifier
    if _classifier is not None:
        return "already in memory"
    with _classifier_lock:
        if _classifier is not None:
            return "already in memory"
        _classifier, source = load_or_train()
        return source


def get_classifier() -> TicketClassifier:
    ensure_classifier()
    return _classifier


def classify(text: str) -> Classification:
    return get_classifier().predict(text)


def knn_vote(text: str, k: int = 10) -> Classification:
    """Baseline: the k most similar historical tickets vote. Confidence = share of votes (not calibrated)."""
    # BM25 only, so this baseline stays the same while the main retrieval changes
    hits = [m for m, _ in get_index().rank(text, top_k=k * 2, mode="bm25") if m.source_type == "ticket"][:k]
    if not hits:
        return Classification(category="Unknown", subcategory="Unknown", priority="P3",
                              confidence=0.0, method="knn_vote")
    votes = Counter((m.metadata["category"], m.metadata["subcategory"]) for m in hits)
    (category, subcategory), n = votes.most_common(1)[0]
    pri = Counter(m.metadata["priority"] for m in hits
                  if (m.metadata["category"], m.metadata["subcategory"]) == (category, subcategory))
    return Classification(category=category, subcategory=subcategory, priority=pri.most_common(1)[0][0],
                          confidence=round(n / len(hits), 3), method="knn_vote")
