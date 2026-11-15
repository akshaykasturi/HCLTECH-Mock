"""Step 1: mask personal data and secrets before anything else sees the text."""
import re

PATTERNS = {
    "email": re.compile(r"\b[\w.+-]+@[\w-]+(\.[\w-]+)+\b"),
    "phone": re.compile(r"(\+\d{1,3}[\s-]?)?\b\d{10}\b"),
    "ip": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "secret": re.compile(r"(?i)\b(password|passwd|pwd|api[_-]?key|token)\s*[:=]\s*\S+"),
}


def redact(text: str) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}
    for name, pattern in PATTERNS.items():
        text, n = pattern.subn(f"[{name.upper()}]", text)
        if n:
            counts[name] = n
    return text, counts
