"""Build the UC4 TF-IDF cache and print a summary.

Run from backend:  .venv/bin/python -m scripts.build_tfidf_uc4
Writes backend/data/processed/tfidf_uc4/ (git-ignored).
"""
from app.uc4.tfidf_data import OUT_DIR, SPLITS, build_tfidf, save_tfidf, top_word_terms, vocab_sizes


def main() -> None:
    """Fit on train, transform validation and test, save, then print the summary."""
    result = build_tfidf()
    save_tfidf(result)
    print(f"Saved to {OUT_DIR}\n")
    print("split       rows  cases  insufficient cases (rows)  matrix shape")
    for split in SPLITS:
        rows = result["rows"][split]
        ins = result["insufficient"][split]
        kept = "excluded" if split == "train" else "kept, flagged"
        print(f"{split:<10} {len(rows):>5} {len({r['case_id'] for r in rows}):>6}  "
              f"{len({r['case_id'] for r in ins})} ({len(ins)} rows, {kept}){'':<4} "
              f"{result['matrices'][split].shape}")
    sizes = vocab_sizes(result["union"])
    print(f"\nVocabulary (fitted on train only): words {sizes['words']}, chars {sizes['chars']}, "
          f"total {sum(sizes.values())}")
    print("\nTop 10 word terms per cause on train (mean TF-IDF):")
    for cause, terms in top_word_terms(result).items():
        print(f"  {cause}: " + ", ".join(f"{t} ({s})" for t, s in terms))


if __name__ == "__main__":
    main()
