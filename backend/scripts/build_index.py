"""Build (or check) everything the API would otherwise compute on first use, so it starts fast.
The Dockerfile runs this at image build time.

Usage (from backend/):  python scripts/build_index.py
- Search vectors: the first run downloads the embedding model (EMBED_MODEL) into backend/.cache/fastembed.
  The vectors are saved in data/index/ with a hash of the corpus + model name.
- Classifier: trained and saved to data/index/classifier.joblib with a hash of historical_tickets.csv
  + the scikit-learn version.
The API reuses both and rebuilds automatically if the data, the model or scikit-learn changes.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.pipeline.classify import MODEL_FILE, load_or_train  # noqa: E402
from app.pipeline.retrieve import Index  # noqa: E402


def main() -> None:
    start = time.perf_counter()
    index = Index()
    elapsed = time.perf_counter() - start
    rows, dims = index.vectors.shape
    print(f"embedder:   {index.embedder.name}")
    print(f"documents:  {rows} vectors x {dims} dims")
    print(f"cache:      {index.cache_path} ({'rebuilt' if index.vectors_rebuilt else 'up to date, loaded'})")
    print(f"time:       {elapsed:.1f}s (includes loading the model)")

    start = time.perf_counter()
    _, source = load_or_train()
    print(f"classifier: {get_settings().index_dir / MODEL_FILE} "
          f"({'trained and saved' if source == 'trained' else 'up to date, loaded'})")
    print(f"time:       {time.perf_counter() - start:.1f}s")


if __name__ == "__main__":
    main()
