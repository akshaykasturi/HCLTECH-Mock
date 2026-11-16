"""Shared text features for the UC4 classifiers.

TF-IDF turns text into numbers: words that are frequent in this line but rare overall count most.
Restored unchanged from the old ticket classifier's _features() (commit b159907).
"""
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import FeatureUnion


def tfidf_features() -> FeatureUnion:
    """Return a new, unfitted TF-IDF feature union: word 1-2 grams plus character 3-5 grams."""
    # word pairs catch phrases ("account locked"); character pieces catch typos and codes ("0x80070643")
    return FeatureUnion([
        ("words", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
        ("chars", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=3, sublinear_tf=True)),
    ])
