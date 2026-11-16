"""Robustness checks for the UC4 failure-class models: are they learning the text, or just reading the status code?

Check 1 (ablation): retrain each model type with columns removed (same hyperparameters as the tuned models,
no new tuning) and score on validation and test:
  full            all features
  no_status_code  without the `status` and `error_code` columns
  text_only       only the cleaned message text
Check 3 (perturbation): keep the trained models and change the raw test log lines, then measure accuracy and
how many predictions flip compared with the unchanged lines:
  ids_numbers     new IPs, emails, field names, limits and counts (things that should not matter)
  typos           one swapped letter pair in about a third of the message words
  paraphrase      messages reworded with a hand-written phrase map (same meaning, different words)
  no_status_code  status replaced by 000 and error code by none
  paraphrase_no_status   both: only the reworded meaning is left

Run from backend:  .\\.venv\\Scripts\\python.exe scripts\\robustness_checks.py
Add --split grouped to use the template-grouped split (no validation set there).
Writes backend/data/eval/robustness.md (random) or robustness_grouped.md (grouped).
Reporting only: nothing here is used to choose a model.
"""
import argparse
import json
import logging
import re
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.metrics import accuracy_score, f1_score
from sklearn.pipeline import Pipeline

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make "app" importable

from app.uc4.ml.features import CONFIG, _read, get_group_split, get_split, get_validation, load_pool, parse_lines  # noqa: E402
from app.uc4.ml.train_models import MODEL_DIR, load_models  # noqa: E402

SEED = 42
OUT = Path(__file__).resolve().parents[1] / "data" / "eval" / "robustness.md"
TEXT_STEPS = {"text_word", "text_char", "text_embed"}
ABLATIONS = {"full": set(), "no_status_code": {"status", "error_code"}, "text_only": "TEXT_ONLY"}

# Same meaning, different words. Written by hand from the messages in the data; applied to test lines only.
PARAPHRASES = [
    (r"Bearer token expired", "access token is no longer valid"),
    (r"API key not recognised for this environment", "unknown credential for this deployment"),
    (r"\bUnauthorized\b", "authentication failed"),
    (r"Token lacks required scope '([^']+)'", r"token missing permission \1"),
    (r"Source IP (\S+) is not allowlisted for this account", r"caller address \1 blocked by network policy"),
    (r"\bForbidden\b", "access denied"),
    (r"Field '([^']+)' is required", r"missing mandatory property \1"),
    (r"Content-Type '([^']+)' is not supported; use application/json", r"media format \1 rejected, send json"),
    (r"Request validation failed", "payload did not pass schema checks"),
    (r"Rate limit of (\d+) requests/minute exceeded for API key", r"quota of \1 calls per minute used up for this credential"),
    (r"Too many requests", "request quota exhausted"),
    (r"client closed request", "caller hung up before the reply"),
    (r"Upstream (\S+) did not respond within (\d+) ms", r"backend \1 gave no answer after \2 ms"),
    (r"Gateway timeout", "proxy waited too long for the backend"),
    (r"Dependency (\S+) unavailable: connection refused", r"downstream \1 is down, socket refused"),
    (r"Service unavailable", "backend offline"),
    (r"Bad gateway", "invalid reply from upstream"),
    (r"Upstream (\S+): TLS handshake with (\S+) failed: certificate has expired", r"secure channel from \1 to \2 broke, cert out of date"),
    (r"Internal server error", "unexpected failure in the service"),
    (r"TypeError: Cannot read properties of undefined \(reading '([^']+)'\)", r"null reference while accessing \1"),
    (r"Timed out acquiring DB connection: pool exhausted", "no free database connections left in the pool"),
]


def _message(line: str) -> tuple[str, str]:
    """Split a raw line into (prefix up to 'message=', message)."""
    head, _, msg = line.partition("message=")
    return head + "message=", msg


def perturb(lines: list[str], kind: str, rng: np.random.Generator) -> list[str]:
    """Return changed copies of raw log lines for one perturbation kind."""
    out = []
    for line in lines:
        head, msg = _message(line)
        if kind in ("ids_numbers",):
            msg = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", lambda m: f"198.51.100.{rng.integers(1, 255)}", msg)
            msg = re.sub(r"[\w.+-]+@example\.\w+", lambda m: f"user{rng.integers(1000)}@example.org", msg)
            msg = re.sub(r"waiting=\d+", lambda m: f"waiting={rng.integers(20, 900)}", msg)
            msg = re.sub(r"max=\d+", lambda m: f"max={rng.choice([20, 80, 120])}", msg)
            msg = re.sub(r"Rate limit of \d+", lambda m: f"Rate limit of {rng.choice([60, 250, 1000])}", msg)
            msg = re.sub(r"within \d+ ms", lambda m: f"within {rng.choice([3000, 5000, 30000])} ms", msg)
            msg = re.sub(r"Field '[^']+'", lambda m: f"Field '{rng.choice(['order_id', 'sku', 'email', 'country'])}'", msg)
        if kind in ("paraphrase", "paraphrase_no_status"):
            for pattern, repl in PARAPHRASES:
                msg = re.sub(pattern, repl, msg)
        if kind == "typos":
            words = msg.split(" ")
            for i, w in enumerate(words):
                if len(w) > 3 and "=" not in w and rng.random() < 0.33:
                    j = int(rng.integers(0, len(w) - 1))
                    words[i] = w[:j] + w[j + 1] + w[j] + w[j + 2 :]
            msg = " ".join(words)
        if kind in ("no_status_code", "paraphrase_no_status"):
            head = re.sub(r"status=\S+", "status=000", head)
            head = re.sub(r"code=\S+", "code=none", head)
        out.append(head + msg)
    return out


def ablate(features: ColumnTransformer, drop: set[str] | str) -> ColumnTransformer:
    """Copy of an (unfitted) ColumnTransformer with columns removed; steps left with no columns are dropped."""
    steps = []
    for name, trans, cols in features.transformers:
        trans = trans if isinstance(trans, str) else clone(trans)  # "passthrough"/"drop" are strings, not estimators
        if drop == "TEXT_ONLY":
            if name in TEXT_STEPS:
                steps.append((name, trans, cols))
            continue
        if isinstance(cols, str):
            if cols not in drop:
                steps.append((name, trans, cols))
            continue
        kept = [c for c in cols if c not in drop]
        if kept:
            steps.append((name, trans, kept))
    return ColumnTransformer(steps, remainder="drop", sparse_threshold=features.sparse_threshold)


def scores(y_true, y_pred) -> tuple[float, float]:
    """(accuracy, macro-F1)."""
    return accuracy_score(y_true, y_pred), f1_score(y_true, y_pred, average="macro", zero_division=0)


def main() -> None:
    """Run both checks, print tables and write the Markdown report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["random", "grouped"], default="random")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    warnings.filterwarnings("ignore")
    bundles = load_models(["tfidf", "embeddings"], args.split)
    if args.split == "grouped":
        X_train, X_test, y_train, y_test = get_group_split()
        X_val = y_val = None  # grouped mode has no separate validation set
        raw = load_pool()[2].loc[X_test.index, "text"].tolist()
        out = OUT.with_name("robustness_grouped.md")
    else:
        X_train, X_test, y_train, y_test = get_split()
        X_val, y_val = get_validation()
        raw = _read("test")["text"].tolist()
        out = OUT
    models = {n: b for n, b in bundles.items() if n != "rules"}
    md = [f"# UC4 robustness checks ({args.split} split)", "", "Reporting only: nothing here was used to choose a model. Accuracy / macro-F1.", ""]

    # ---- Check 1: ablation (retrain with the tuned hyperparameters, no new tuning) ----
    print("CHECK 1: retrain without columns (val acc / test acc, test macro-F1)")
    md += ["## Check 1: retrain with columns removed", "",
           "Same hyperparameters as the tuned models; only the input columns change.", "",
           "| Model | Full: val / test acc | No status+code: val / test acc | Text only: val / test acc | Text only: test macro-F1 |",
           "|---|---|---|---|---|"]
    rules = bundles["rules"]["model"]
    ablation = {}
    for name, bundle in models.items():
        fitted: Pipeline = bundle["model"]
        row = {}
        for label, drop in ABLATIONS.items():
            pipe = Pipeline([("features", ablate(fitted.named_steps["features"], drop)), ("clf", clone(fitted.named_steps["clf"]))])
            pipe.fit(X_train, y_train)
            va = scores(y_val, pipe.predict(X_val))[0] if X_val is not None else None
            ta, tf = scores(y_test, pipe.predict(X_test))
            row[label] = (va, ta, tf)
        ablation[name] = row
        cell = {k: f"{'-' if v[0] is None else f'{v[0]:.3f}'} / {v[1]:.3f}" for k, v in row.items()}
        print(f"  {name:<24} full {cell['full']}   no status+code {cell['no_status_code']}   text only {cell['text_only']} (F1 {row['text_only'][2]:.3f})")
        md.append(f"| {name} | {cell['full']} | {cell['no_status_code']} | {cell['text_only']} | {row['text_only'][2]:.3f} |")
    rv = f"{scores(y_val, rules.predict(X_val))[0]:.3f}" if X_val is not None else "-"
    rt, _ = scores(y_test, rules.predict(X_test))
    md += ["", f"Rules baseline (status only), for reference: val {rv} / test {rt:.3f}.", ""]

    # ---- Check 3: perturb the raw test lines, keep the trained models ----
    kinds = ["ids_numbers", "typos", "paraphrase", "no_status_code", "paraphrase_no_status"]
    rng = np.random.default_rng(SEED)
    changed = {k: perturb(raw, k, rng) for k in kinds}
    examples = {k: (raw[i], changed[k][i]) for k, i in zip(kinds, [n * len(raw) // 6 for n in range(1, 6)])}
    print("\nCHECK 3: perturbed test lines (accuracy, share of predictions that flipped)")
    md += ["## Check 3: perturbed test lines (trained models, unchanged)", "",
           "Cells: accuracy (share of predictions that flipped vs the original lines).", "",
           "| Model | Original | " + " | ".join(kinds) + " |", "|---" * (len(kinds) + 2) + "|"]
    perturbation = {}
    for name, bundle in {"rules": bundles["rules"], **models}.items():
        model = bundle["model"]
        base = model.predict(X_test)
        cells = {"original": (accuracy_score(y_test, base), 0.0)}
        for k in kinds:
            pred = model.predict(parse_lines(changed[k]))
            cells[k] = (accuracy_score(y_test, pred), float(np.mean(pred != base)))
        perturbation[name] = cells
        print(f"  {name:<24} " + "  ".join(f"{k} {a:.3f} ({f:.0%})" for k, (a, f) in cells.items()))
        md.append(f"| {name} | " + " | ".join(f"{a:.3f} ({f:.0%})" for a, f in cells.values()) + " |")

    md += ["", "Example changes (original -> changed):", ""]
    for k, (a, b) in examples.items():
        md += [f"- **{k}**: `{a}`", f"  -> `{b}`"]
    md += ["", f"Majority-class accuracy on test: {y_test.value_counts(normalize=True).max():.3f}.", ""]
    out.write_text("\n".join(md) + "\n", encoding="utf-8")
    (out.with_suffix(".json")).write_text(json.dumps({"split": args.split, "ablation": ablation, "perturbation": perturbation}, indent=2), encoding="utf-8")
    print(f"\nWrote {out} and {out.with_suffix('.json')}")
    print(f"(models from {MODEL_DIR / args.split}; majority-class test accuracy {y_test.value_counts(normalize=True).max():.3f})")


if __name__ == "__main__":
    main()
