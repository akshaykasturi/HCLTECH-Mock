"""Test-wide settings.

Doc search runs BM25 only in tests (no embedding model download, same as the fake embedder in
test_ml_embed_features.py): tests stay offline and deterministic. The hybrid path is tested with a
fake embedder in test_doc_search.py; scripts/eval_doc_search.py measures the real model.
"""
import os

os.environ.setdefault("UC4_DOC_SEARCH_DENSE", "0")
