"""Inspect the UC4 embedding features: shape, timing, and whether the embeddings carry class signal.

Run from backend:  .\\.venv\\Scripts\\python.exe scripts\\inspect_embeddings.py
Similarity checks use the train split only.
"""
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make "app" importable

from app.uc4.ml.embed_features import (  # noqa: E402
    CONFIG,
    TextEmbedder,
    build_embed_features,
    get_groups,
    get_split,
    load_dataset,
)

MIN_GAP = 0.05  # warn when within-class similarity is not at least this much above between-class


def timing() -> None:
    """Embed every row of all splits with an empty cache (cold), then again (cached)."""
    X_all, _ = load_dataset("all")
    with tempfile.TemporaryDirectory() as tmp:
        emb = TextEmbedder(cache_dir=tmp)
        emb.transform(X_all[CONFIG["text"]].head(2))  # load the model first, so cold = embedding only
        tmp_cache = Path(tmp)
        for f in tmp_cache.glob("*.npz"):
            f.unlink()
        t0 = time.perf_counter()
        emb.transform(X_all[CONFIG["text"]])
        cold = time.perf_counter() - t0
        t0 = time.perf_counter()
        emb.transform(X_all[CONFIG["text"]])
        cached = time.perf_counter() - t0
    distinct = X_all[CONFIG["text"]].nunique()
    print(f"embed all {len(X_all)} rows ({distinct} distinct texts): cold {cold:.2f}s, cached {cached:.3f}s")


def similarity_table(E: np.ndarray, labels: np.ndarray) -> bool:
    """Print mean cosine within vs between classes on distinct (text, label) rows; return True if signal is clear."""
    sims = E @ E.T
    ok = True
    print(f"\n{'class':<15} {'n':>3} {'within':>7} {'between':>8} {'gap':>6}")
    for label in sorted(set(labels)):
        inside = labels == label
        block = sims[np.ix_(inside, inside)]
        n = int(inside.sum())
        within = (block.sum() - n) / (n * (n - 1)) if n > 1 else float("nan")
        between = float(sims[np.ix_(inside, ~inside)].mean())
        gap = within - between
        flag = "" if gap >= MIN_GAP else "  <-- weak"
        ok &= bool(gap >= MIN_GAP)
        print(f"{label:<15} {n:>3} {within:>7.3f} {between:>8.3f} {gap:>6.3f}{flag}")
    return ok


def nearest_neighbour(E: np.ndarray, labels: np.ndarray, groups: np.ndarray) -> np.ndarray:
    """Index of each row's most similar row from a DIFFERENT case (same-case rows are near-copies)."""
    sims = E @ E.T
    sims[groups[:, None] == groups[None, :]] = -np.inf
    return sims.argmax(axis=1)


def main() -> None:
    """Fit on train, print shape/dim, timing, class-signal checks and example neighbour pairs."""
    X_train, _, y_train, _ = get_split()
    features = build_embed_features().fit(X_train)
    Xt = features.transform(X_train)
    dim = features.named_transformers_["text_embed"].dim_
    print(f"train matrix shape: {Xt.shape} (dense: {isinstance(Xt, np.ndarray)}), embedding dim: {dim}")
    timing()

    E = TextEmbedder().transform(X_train[CONFIG["text"]])
    labels = y_train.to_numpy()
    groups = get_groups("train").to_numpy()

    # Within/between on distinct (text, label) pairs, so duplicated log lines don't inflate "within".
    _, first = np.unique(np.array([f"{t}\x00{l}" for t, l in zip(X_train[CONFIG["text"]], labels)]), return_index=True)
    print(f"\nMean cosine similarity on {len(first)} distinct (message, label) pairs:")
    clear = similarity_table(E[first], labels[first])

    nn = nearest_neighbour(E, labels, groups)
    agree = float((labels[nn] == labels).mean())
    print(f"\n1-nearest-neighbour label agreement (neighbour from another case): {agree:.3f} on {len(labels)} rows")

    print("\nExample pairs (message -> nearest message from another case; exact copies skipped when possible):")
    rng = np.random.default_rng(42)
    texts = X_train[CONFIG["text"]].to_numpy()
    for label in rng.choice(sorted(set(labels)), size=3, replace=False):
        rows = np.flatnonzero(labels == label)
        differs = rows[texts[rows] != texts[nn[rows]]]
        i = int(rng.choice(differs if len(differs) else rows))
        j = int(nn[i])
        print(f"  [{labels[i]}] {X_train[CONFIG['text']].iloc[i]}")
        print(f"   -> [{labels[j]}] {X_train[CONFIG['text']].iloc[j]}  (cos {float(E[i] @ E[j]):.3f})")

    if not clear:
        print(f"\nWARNING: within-class similarity is not clearly above between-class (gap < {MIN_GAP}) for some classes.")
    else:
        print(f"\nOK: every class has within-class similarity at least {MIN_GAP} above between-class.")


if __name__ == "__main__":
    main()
