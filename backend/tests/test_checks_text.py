"""checks_text.yaml: readable, read-only checks and an owner for every cause."""
import re

from app.uc4.checks import get_check_settings
from app.uc4.doc_search import get_section
from app.uc4.rank import load_catalog
from app.uc4.settings import get_settings
from app.uc4.template_report import load_checks_text


def test_every_cause_has_check_text_and_an_owner() -> None:
    texts = load_checks_text()["causes"]
    for cause in load_catalog():
        entry = texts.get(cause)
        assert entry, f"{cause} missing from checks_text.yaml"
        assert entry["check_text"].strip() and entry["owner"].strip() and entry["owner_why"].strip(), cause
        assert "If this is the cause" in entry["check_text"], cause  # says what you'd expect to see


def test_check_text_is_read_only_and_has_no_numbers_of_its_own() -> None:
    verbs = get_check_settings()["safe_steps"]["verbs"]
    for cause, entry in load_checks_text()["causes"].items():
        low = entry["check_text"].lower()
        for verb in verbs:
            assert not re.search(r"(?<!\w)" + re.escape(verb) + r"(?:s|es|ed|d|ing)?(?!\w)", low), (cause, verb)
        # HTTP status codes (429, 504...) are names, not measurements; any other number is not allowed.
        numbers = re.findall(r"(?<![\w_])\d+(?:\.\d+)?", entry["check_text"])
        assert all(re.fullmatch(r"[1-5]\d\d", n) for n in numbers), (cause, numbers)


def test_sources_are_real_doc_sections() -> None:
    for cause, entry in load_checks_text()["causes"].items():
        if entry.get("source"):
            section = get_section(entry["source"])
            assert section is not None and section.status != "deprecated", (cause, entry["source"])


def test_every_route_dependency_has_an_owner() -> None:
    owners = load_checks_text()["dependencies"]
    for route, info in get_settings()["routes"].items():
        for dep in info["dependencies"]:
            assert dep in owners, (route, dep)


def test_owners_reference_a_known_placeholder_or_a_name() -> None:
    for cause, entry in load_checks_text()["causes"].items():
        owner = entry["owner"]
        assert owner in ("{client}", "@dependency", "@service") or not owner.startswith(("@", "{")), cause
