"""How numbers are shown to people (the stored numbers never change)."""


def format_confidence(x: float) -> str:
    """0.9996 -> "> 0.99", 0.00004 -> "< 0.01", else two decimals. Naive Bayes pushes values to the
    extremes, so "1.00" or "0.00" would overstate how sure we are.

    TODO: calibrate confidences on the validation split (e.g. temperature or isotonic scaling, checked
    with a reliability plot / Brier score from app/analysis/stats.py) before showing them as probabilities.
    """
    if x > 0.99:
        return "> 0.99"
    if x < 0.01:
        return "< 0.01"
    return f"{x:.2f}"
