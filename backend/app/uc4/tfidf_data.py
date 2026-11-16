"""UC4 TF-IDF dataset: load the classifier splits, fit TF-IDF on train only, save a cache.

Rows come from backend/data/eval/uc4/classifier_{train,calibration,test}.csv (one failing log line per row).
"calibration" in the file names is our validation split. expected_cause is joined from cases.jsonl.
Insufficient-evidence cases (expected_cause is null) are left out of train, because they have no cause
to learn; in validation and test they stay in, flagged, so the evaluation can score CLARIFY.
"""
import csv
import json
from pathlib import Path

import joblib
import numpy as np
from scipy import sparse
from sklearn.pipeline import FeatureUnion

from app.uc4.features import tfidf_features

BACKEND = Path(__file__).resolve().parents[2]
EVAL_DIR = BACKEND / "data" / "eval" / "uc4"
OUT_DIR = BACKEND / "data" / "processed" / "tfidf_uc4"

SPLITS = ("train", "validation", "test")
CSV_NAME = {"train": "classifier_train.csv", "validation": "classifier_calibration.csv",
            "test": "classifier_test.csv"}
META_KEYS = ("case_id", "is_focal", "expected_class", "expected_cause", "insufficient")


def _cases(data_dir: Path) -> dict[str, dict]:
    """Read cases.jsonl into {case_id: case}."""
    with open(data_dir / "cases.jsonl", encoding="utf-8") as f:
        return {c["case_id"]: c for c in (json.loads(line) for line in f if line.strip())}


def load_split(split: str, data_dir: Path = EVAL_DIR) -> tuple[list[dict], list[dict]]:
    """Return (rows, insufficient_rows) for one split; train rows never include insufficient cases."""
    if split not in CSV_NAME:
        raise ValueError(f"split must be one of {SPLITS}, not {split!r}")
    cases = _cases(data_dir)
    rows: list[dict] = []
    insufficient: list[dict] = []
    with open(data_dir / CSV_NAME[split], encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            case = cases[r["case_id"]]
            row = {"case_id": r["case_id"], "is_focal": r["is_focal"] == "True", "text": r["text"],
                   "expected_class": r["label"], "expected_cause": case["expected_cause"],
                   "insufficient": case["expected_cause"] is None}
            if row["insufficient"]:
                insufficient.append(row)
                if split == "train":
                    continue
            rows.append(row)
    return rows, insufficient


def build_tfidf(data_dir: Path = EVAL_DIR) -> dict:
    """Fit tfidf_features() on train text only and transform every split; returns union, matrices and rows."""
    rows = {}
    insufficient = {}
    for split in SPLITS:
        rows[split], insufficient[split] = load_split(split, data_dir)
    union: FeatureUnion = tfidf_features()
    union.fit([r["text"] for r in rows["train"]])
    matrices = {split: union.transform([r["text"] for r in rows[split]]).tocsr() for split in SPLITS}
    return {"union": union, "matrices": matrices, "rows": rows, "insufficient": insufficient}


def save_tfidf(result: dict, out_dir: Path = OUT_DIR) -> None:
    """Write {split}.npz, vectorizer.joblib and {split}_rows.jsonl (no text) to out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for split in SPLITS:
        sparse.save_npz(out_dir / f"{split}.npz", result["matrices"][split])
        with open(out_dir / f"{split}_rows.jsonl", "w", encoding="utf-8") as f:
            for r in result["rows"][split]:
                f.write(json.dumps({k: r[k] for k in META_KEYS}) + "\n")
    joblib.dump(result["union"], out_dir / "vectorizer.joblib")


def vocab_sizes(union: FeatureUnion) -> dict[str, int]:
    """Number of word and character features in a fitted union."""
    return {name: len(vec.vocabulary_) for name, vec in union.transformer_list}


def top_word_terms(result: dict, k: int = 10) -> dict[str, list[tuple[str, float]]]:
    """Top k word terms per cause on train, ranked by mean TF-IDF over that cause's rows."""
    words = dict(result["union"].transformer_list)["words"]
    names = words.get_feature_names_out()
    train = result["rows"]["train"]
    x = words.transform([r["text"] for r in train])
    causes = np.array([r["expected_cause"] for r in train])
    out = {}
    for cause in sorted(set(causes)):
        mean = np.asarray(x[causes == cause].mean(axis=0)).ravel()
        order = np.lexsort((names, -mean))[:k]  # highest mean first, ties broken alphabetically
        out[cause] = [(str(names[i]), round(float(mean[i]), 3)) for i in order]
    return out
