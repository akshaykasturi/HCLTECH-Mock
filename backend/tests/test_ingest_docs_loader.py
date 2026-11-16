"""Tests for the API documentation loader (app/uc4/docs_loader.py).

Real-data tests read backend/data/raw/uc4/api_docs (read-only). Failure scenarios use synthetic
files in pytest's tmp_path. No secrets, no network.
"""
import ast
import hashlib
import json
import shutil
from io import BytesIO
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.uc4 import docs_loader
from app.uc4.docs_loader import (
    DEFAULT_DOCS_DIR, DocSection, DocsLoaderError, clean_text, discover_files, ingest, load_docs,
    load_docs_with_report, normalise_doc_ref, validate_sections,
)
from app.uc4.settings import BACKEND_DIR

GOLD_FILE = BACKEND_DIR / "data" / "eval" / "uc4" / "retrieval_gold.jsonl"
EXPECTED_DOC_IDS = {
    "architecture-and-dependencies", "authentication", "authorization-and-scopes", "changelog",
    "endpoints/customers", "endpoints/inventory", "endpoints/orders", "endpoints/payments",
    "endpoints/refunds", "endpoints/search", "errors", "integration-guide",
    "legacy/rate-limits-v1", "overview", "rate-limits", "sla-and-status",
    "timeouts-and-retries", "troubleshooting",
}
DOCSECTION_FIELDS = ["id", "doc_id", "title", "heading", "heading_path", "text", "version", "status",
                     "updated", "superseded_by", "format", "source_path"]
MD_FRONT = "---\ntitle: {title}\nversion: \"1.0\"\nstatus: current\nupdated: 2026-01-01\n---\n"


@pytest.fixture(scope="module")
def real():
    """One ingestion run over the real docs folder, shared by the read-only tests."""
    return ingest(DEFAULT_DOCS_DIR)


@pytest.fixture(scope="module")
def by_id(real):
    return {s.id: s for s in real.sections}


def write(folder: Path, rel: str, content, binary: bool = False) -> Path:
    path = folder / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if binary:
        path.write_bytes(content)
    else:
        path.write_bytes(content.encode("utf-8"))
    return path


def md(title: str, body: str) -> str:
    return MD_FRONT.format(title=title) + body


def blank_pdf_bytes() -> bytes:
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def tree_fingerprint(folder: Path) -> dict[str, tuple[str, int]]:
    return {p.relative_to(folder).as_posix(): (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in sorted(folder.rglob("*")) if p.is_file()}


# 1. Recursive discovery
def test_recursive_discovery(tmp_path):
    write(tmp_path, "a.md", md("A", "# A\n\ntext"))
    write(tmp_path, "sub/b.md", md("B", "# B\n\ntext"))
    write(tmp_path, "sub/deeper/c.html", "<title>C</title><h1>C</h1><p>text</p>")
    files = discover_files(tmp_path)
    assert [f.doc_id for f in files] == ["a", "sub/b", "sub/deeper/c"]
    assert [f.rel_path for f in files] == ["a.md", "sub/b.md", "sub/deeper/c.html"]
    assert {s.doc_id for s in load_docs(tmp_path)} == {"a", "sub/b", "sub/deeper/c"}


# 2 + 26. Supported extension filtering; unsupported files reported, never loaded
def test_unsupported_files_are_reported_not_loaded(tmp_path):
    write(tmp_path, "good.md", md("Good", "# Good\n\ntext"))
    write(tmp_path, "notes.txt", "plain text")
    write(tmp_path, "img/logo.png", b"\x89PNG\r\n", binary=True)
    write(tmp_path, "UPPER.MD", md("Upper", "# Upper\n\ntext"))
    sections, report = load_docs_with_report(tmp_path)
    assert report.files_discovered == 4 and report.supported_files == 2
    assert report.unsupported_files == ["img/logo.png", "notes.txt"]
    assert {s.doc_id for s in sections} == {"good", "UPPER"}


# 3. Deterministic processing order
def test_processing_order_is_sorted_and_repeatable(tmp_path):
    for name in ("zeta.md", "alpha.md", "mid/beta.md"):
        write(tmp_path, name, md(name, f"# {name}\n\nbody of {name}"))
    first = [s.id for s in load_docs(tmp_path)]
    second = [s.id for s in load_docs(tmp_path)]
    assert first == second == ["doc:alpha#1", "doc:mid/beta#1", "doc:zeta#1"]


# 4. All 18 documents load
def test_all_18_documents_load(real):
    r = real.report
    assert r.files_discovered == 18 and r.supported_files == 18 and r.documents_loaded == 18
    assert r.documents_by_format == {"md": 16, "html": 1, "pdf": 1}
    assert r.documents_skipped == [] and r.errors == []


# 5. All expected document ids exist
def test_expected_document_ids(real):
    assert {d.doc_id for d in real.documents} == EXPECTED_DOC_IDS
    assert {s.doc_id for s in real.sections} == EXPECTED_DOC_IDS


# 6. Document ids match retrieval_gold.jsonl
def test_every_gold_doc_id_is_ingested(real):
    gold_ids = set()
    for line in GOLD_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            gold_ids.update(json.loads(line)["gold_doc_ids"])
    loaded = {d.doc_id for d in real.documents}
    assert gold_ids, "retrieval_gold.jsonl should name some documents"
    assert gold_ids - loaded == set()
    assert "integration-guide" in gold_ids


# Data card reference values (measured, not forced: H2 sections + intro text, see module docstring)
def test_section_count_matches_data_card(real):
    assert real.report.sections_total == len(real.sections) == 55


# 7. Markdown metadata
def test_markdown_metadata(by_id):
    s = by_id["doc:rate-limits#1"]
    assert (s.title, s.version, s.status, s.updated, s.superseded_by, s.format) == (
        "Rate limits", "2.3", "current", "2026-09-01", None, "md")
    assert s.heading_path == ["Rate limits"]  # intro section
    assert "100 requests per minute" in s.text
    assert "title:" not in s.text and "---" not in s.text  # front matter removed from the body


# 8. HTML metadata and clean HTML text
def test_html_metadata_and_text(real, by_id):
    sla = [s for s in real.sections if s.doc_id == "sla-and-status"]
    assert [s.heading for s in sla] == ["Service levels and status page", "Latency objectives",
                                        "Error budget", "Incident communication"]
    first = sla[0]
    assert (first.title, first.version, first.status, first.updated, first.format) == (
        "Service levels and status page", "2.3", "current", "2026-09-01", "html")
    all_text = " ".join(s.text for s in sla)
    for junk in ("Home | Docs | Status", "statusWidget", "font-family", "(c) NovaPay"):
        assert junk not in all_text
    assert "Payments: p95 under 1500 ms" in by_id["doc:sla-and-status#2"].text


def test_html_parsing_details(tmp_path):
    html = ("<html><head><title>T &amp; C</title><meta name='status' content='current'></head><body>"
            "<header>site header</header><h1>T &amp; C</h1><p>one</p><p>two</p>"
            "<h2>Codes &lt;4xx&gt;</h2><p>A&nbsp;B</p><pre>  keep   spacing</pre><h3>Sub</h3><p>deep</p>"
            "<script>alert(1)</script><aside>ad</aside></body></html>")
    write(tmp_path, "page.html", html)
    sections = load_docs(tmp_path)
    assert sections[0].title == "T & C" and sections[0].text == "one\ntwo"  # words not joined
    assert sections[1].heading == "Codes <4xx>"
    assert "A B" in sections[1].text and "keep   spacing" in sections[1].text
    assert "### Sub\ndeep" in sections[1].text  # nested heading stays in its parent section
    joined = " ".join(s.text for s in sections)
    assert "site header" not in joined and "alert" not in joined and " ad" not in joined


# 9. PDF text extraction
def test_pdf_extraction(real, by_id):
    pdf = [s for s in real.sections if s.doc_id == "integration-guide"]
    assert [s.heading for s in pdf] == ["NovaPay integration guide", "1. Credentials",
                                        "2. Request checklist", "3. Timeouts and retries", "4. Going live"]
    assert all(s.format == "pdf" and s.title == "NovaPay integration guide" for s in pdf)
    assert pdf[0].version == "2.3" and pdf[0].updated == "2026-09-01"
    assert pdf[0].status is None  # the PDF does not state a status: not invented
    assert "at least 15000 ms" in by_id["doc:integration-guide#4"].text
    assert "Bearer tokens live 3600 seconds" in by_id["doc:integration-guide#2"].text  # wrapped line joined
    entry = real.report.pdf_extraction[0]
    assert entry["status"] == "ok" and entry["pages"] == 2 and entry["pages_with_text"] == 2
    assert entry["empty_pages"] == [] and entry["headings_detected"] == 4
    assert {"doc_id": "integration-guide", "fields": ["status"]} in real.report.missing_metadata


def test_pdf_without_text_is_reported_not_fabricated(tmp_path):
    write(tmp_path, "scan.pdf", blank_pdf_bytes(), binary=True)
    sections, report = load_docs_with_report(tmp_path)
    assert sections == []
    assert report.documents_skipped == [{"path": "scan.pdf", "reason": "PDF has no extractable text (scanned image or empty)"}]
    assert report.pdf_extraction[0]["status"] == "failed" and report.pdf_extraction[0]["empty_pages"] == [1]


# 10. Missing metadata
def test_missing_metadata_is_none_and_reported(tmp_path):
    write(tmp_path, "bare.md", "# Bare doc\n\nSome text.\n\n## Part\n\nMore.")
    sections, report = load_docs_with_report(tmp_path)
    s = sections[0]
    assert s.title == "Bare doc"  # taken from the document's own top heading (reported)
    assert (s.version, s.status, s.updated, s.superseded_by) == (None, None, None, None)
    assert report.missing_metadata == [{"doc_id": "bare", "fields": ["title", "version", "status", "updated"]}]
    assert {"path": "bare.md", "message": "title taken from the document's top heading"} in report.warnings


def test_document_without_any_title(tmp_path):
    write(tmp_path, "notitle.md", "Just a paragraph.")
    sections, report = load_docs_with_report(tmp_path)
    assert sections[0].title is None and sections[0].heading == "notitle"  # falls back to the doc id
    assert report.missing_metadata[0]["fields"][0] == "title"


# 11. Invalid metadata
def test_invalid_metadata_is_reported_and_not_replaced(tmp_path):
    write(tmp_path, "bad.md", "---\ntitle: Bad\nversion: 2.3\nstatus: retired\nupdated: 01/09/2026\n"
                              "superseded_by: nowhere.md\n---\n# Bad\n\ntext")
    sections, report = load_docs_with_report(tmp_path)
    s = sections[0]
    assert (s.title, s.version, s.status, s.updated) == ("Bad", None, None, None)
    assert s.superseded_by == "nowhere"  # kept as stated, flagged as unknown
    fields = {(i["field"], i["reason"]) for i in report.invalid_metadata}
    assert ("version", "must be non-empty text (got float)") in fields
    assert ("status", "must be one of current, deprecated") in fields
    assert ("updated", "must be a date in YYYY-MM-DD form") in fields
    assert ("superseded_by", "points to an unknown document") in fields


def test_broken_front_matter_does_not_stop_loading(tmp_path):
    write(tmp_path, "broken.md", "---\ntitle: [unclosed\n---\n# Broken\n\nstill readable")
    sections, report = load_docs_with_report(tmp_path)
    assert sections[0].text == "still readable"
    assert {"path": "broken.md", "message": "front matter is not valid YAML; metadata ignored"} in report.warnings


# 12. Deprecated documents are kept
def test_deprecated_document_is_preserved(real):
    legacy = [s for s in real.sections if s.doc_id == "legacy/rate-limits-v1"]
    assert len(legacy) == 2
    assert all(s.status == "deprecated" and s.superseded_by == "rate-limits" and s.version == "1.9" for s in legacy)
    assert "60 requests per minute" in legacy[1].text
    assert real.report.deprecated_documents == ["legacy/rate-limits-v1"]


# 13. superseded_by normalisation
def test_superseded_by_normalisation():
    known = {"rate-limits", "legacy/old", "legacy/new", "guide"}
    assert normalise_doc_ref("rate-limits.md", "legacy/old", known) == "rate-limits"
    assert normalise_doc_ref("./rate-limits.md", "legacy/old", known) == "rate-limits"
    assert normalise_doc_ref("/rate-limits", "legacy/old", known) == "rate-limits"
    assert normalise_doc_ref("guide.PDF", "x", known) == "guide"
    assert normalise_doc_ref("new.md", "legacy/old", known) == "legacy/new"  # sibling in the same folder
    assert normalise_doc_ref("legacy\\new.html", "x", known) == "legacy/new"
    assert normalise_doc_ref("missing.md", "legacy/old", known) == "missing"


# 14 + 18. Heading-based chunking and hierarchy
def test_heading_chunking_keeps_nested_content(real, by_id):
    orders = [s for s in real.sections if s.doc_id == "endpoints/orders"]
    assert [s.heading_path for s in orders] == [["Orders endpoints", "POST /v1/orders"],
                                                ["Orders endpoints", "GET /v1/orders/{id}"]]
    assert "### Required fields for POST /v1/orders" in orders[0].text
    assert "`currency` (ISO 4217" in orders[0].text and "currency" not in orders[1].text
    trouble = [s.heading for s in real.sections if s.doc_id == "troubleshooting"]
    assert trouble == ["Troubleshooting guide", "401 Unauthorized", "403 Forbidden", "400 and 415",
                       "429 Too Many Requests", "499, 504 and other timeouts", "500, 502 and 503"]
    for s in real.sections:
        assert s.heading_path[-1] == s.heading and 1 <= len(s.heading_path) <= 2
        assert s.text.strip()


def test_headings_inside_code_blocks_do_not_split(tmp_path):
    body = "# Doc\n\n## Real\n\n```bash\n## not a heading\ncurl  -X POST /v1/orders\n```\n\nafter"
    write(tmp_path, "code.md", md("Doc", body))
    sections = load_docs(tmp_path)
    assert len(sections) == 1 and sections[0].heading == "Real"
    assert "```bash\n## not a heading\ncurl  -X POST /v1/orders\n```" in sections[0].text


# 15 + 16 + 17. Numbering from 1, stable ids, unique ids
def test_section_ids_start_at_one_and_are_consecutive(real):
    per_doc: dict[str, list[str]] = {}
    for s in real.sections:
        per_doc.setdefault(s.doc_id, []).append(s.id)
    for doc_id, ids in per_doc.items():
        assert ids == [f"doc:{doc_id}#{n}" for n in range(1, len(ids) + 1)]
    assert "doc:rate-limits#1" in {s.id for s in real.sections}
    assert "doc:integration-guide#1" in {s.id for s in real.sections}


def test_ids_and_output_are_stable_across_runs(real):
    again = load_docs(DEFAULT_DOCS_DIR)
    assert [s.model_dump() for s in again] == [s.model_dump() for s in real.sections]


def test_section_ids_are_unique(real):
    ids = [s.id for s in real.sections]
    assert len(ids) == len(set(ids))


def test_id_collisions_are_refused():
    s = DocSection(id="doc:a#1", doc_id="a", title="A", heading="A", heading_path=["A"], text="x",
                   version=None, status=None, updated=None, superseded_by=None, format="md", source_path="a.md")
    with pytest.raises(DocsLoaderError):
        validate_sections([s, s])
    with pytest.raises(DocsLoaderError):
        validate_sections([s.model_copy(update={"id": "doc:a#2"})])


def test_duplicate_document_ids_are_reported(tmp_path):
    write(tmp_path, "guide.md", md("Guide md", "# Guide\n\nmarkdown"))
    write(tmp_path, "guide.html", "<title>Guide html</title><h1>Guide</h1><p>html</p>")
    sections, report = load_docs_with_report(tmp_path)
    assert [s.format for s in sections] == ["html"]  # first in sorted order wins, nothing overwritten
    assert report.documents_skipped[0]["path"] == "guide.md"
    assert "duplicate document id 'guide'" in report.documents_skipped[0]["reason"]


# 19 + 20 + 21. Duplicates are reported, never removed
def test_exact_file_duplicates_are_reported_not_removed(tmp_path):
    original = DEFAULT_DOCS_DIR / "rate-limits.md"
    shutil.copyfile(original, tmp_path / "rate-limits.md")
    shutil.copyfile(original, tmp_path / "copy-of-rate-limits.md")
    sections, report = load_docs_with_report(tmp_path)
    assert report.documents_loaded == 2
    assert len(report.duplicate_files) == 1
    assert [Path(p).name for p in report.duplicate_files[0]["paths"]] == ["copy-of-rate-limits.md", "rate-limits.md"]
    assert {s.doc_id for s in sections} == {"rate-limits", "copy-of-rate-limits"}


def test_exact_section_duplicates_are_reported_not_removed(tmp_path):
    write(tmp_path, "a.md", md("A", "# A\n\n## Retry\n\nRetry 429 with   backoff.\n\n## Other\n\nunique a"))
    write(tmp_path, "b.md", md("B", "# B\n\n## Retries\n\nretry 429 WITH backoff.\n"))
    sections, report = load_docs_with_report(tmp_path)
    assert report.duplicate_sections == [{"sha256": report.duplicate_sections[0]["sha256"],
                                          "section_ids": ["doc:a#1", "doc:b#1"]}]
    assert len(sections) == 3  # both copies kept


def test_real_dataset_has_no_exact_duplicates(real):
    assert real.report.duplicate_files == [] and real.report.duplicate_sections == []


# 22. Empty documents
def test_empty_documents(tmp_path):
    write(tmp_path, "zero.md", "")
    write(tmp_path, "spaces.md", "   \n\n  ")
    write(tmp_path, "frontonly.md", md("Only metadata", ""))
    write(tmp_path, "ok.md", md("Ok", "# Ok\n\ncontent"))
    sections, report = load_docs_with_report(tmp_path)
    assert [s.doc_id for s in sections] == ["ok"]
    assert {d["path"]: d["reason"] for d in report.documents_skipped} == {
        "spaces.md": "file is empty", "zero.md": "file is empty"}
    assert report.empty_documents == ["frontonly", "spaces.md", "zero.md"]
    assert report.documents_loaded == 2  # frontonly loaded (metadata) but has no sections


# 23. Empty sections
def test_empty_sections_are_reported_and_not_emitted(tmp_path):
    write(tmp_path, "doc.md", md("Doc", "# Doc\n\n## Empty one\n\n\n## Full\n\nreal text\n\n## Empty two\n"))
    sections, report = load_docs_with_report(tmp_path)
    assert [(s.id, s.heading) for s in sections] == [("doc:doc#1", "Full")]
    assert report.empty_sections == [{"doc_id": "doc", "heading": "Empty one"},
                                     {"doc_id": "doc", "heading": "Empty two"}]


# 24. Corrupted PDF
def test_corrupted_pdf_is_reported(tmp_path):
    write(tmp_path, "broken.pdf", b"%PDF-1.4\nthis is not really a pdf\n%%EOF", binary=True)
    sections, report = load_docs_with_report(tmp_path)
    assert sections == []
    assert report.documents_skipped[0]["path"] == "broken.pdf"
    assert report.documents_skipped[0]["reason"].startswith(("corrupted or unreadable PDF", "PDF has no"))
    assert report.pdf_extraction[0]["status"] == "failed"


# 25. Invalid encoding
def test_invalid_encoding_is_reported(tmp_path):
    write(tmp_path, "latin.md", "---\ntitle: Caf\xe9\n---\n# Caf\xe9\n".encode("latin-1"), binary=True)
    write(tmp_path, "bom.md", "﻿".encode("utf-8") + md("Bom", "# Bom\n\nok").encode("utf-8"), binary=True)
    sections, report = load_docs_with_report(tmp_path)
    assert [s.doc_id for s in sections] == ["bom"]  # a UTF-8 BOM is fine
    assert report.documents_skipped == [{"path": "latin.md", "reason": "invalid UTF-8 encoding at byte 14"}]


# 27. Source-path traceability
def test_source_paths_point_at_the_real_files(real):
    for s in real.sections:
        assert (BACKEND_DIR / s.source_path).is_file()
        assert s.source_path.startswith("data/raw/uc4/api_docs/")
        assert Path(s.source_path).with_suffix("").as_posix().endswith(s.doc_id)
        assert s.title is not None


# 28. Whitespace normalisation
def test_clean_text_whitespace():
    raw = "  \r\nLine  one  has   gaps  \r\n\r\n\r\n\r\n  - indented  item\rzero​width﻿\n\n"
    assert clean_text(raw) == "Line one has gaps\n\n  - indented item\nzerowidth"
    assert clean_text("é") == "é"  # Unicode NFC


# 29. Technical content preservation
def test_technical_content_is_preserved(by_id, real):
    text = " ".join(s.text for s in real.sections)
    for token in ("GET /v1/orders/{id}", "`429 ERR_RATE_LIMITED`", "X-RateLimit-Limit", "99.9%",
                  "`orders:write`", "Retry-After", "ISO 4217", "nvp_test_"):
        assert token in text, token
    raw = "```json\n{\"a\":   1,\n  \"b\": [1,  2]}\n```"
    assert clean_text(raw) == raw  # code block untouched


# 30. Schema compatibility
def test_docsection_schema_is_exact(real):
    assert list(DocSection.model_fields) == DOCSECTION_FIELDS
    sample = real.sections[0]
    assert list(sample.model_dump()) == DOCSECTION_FIELDS
    assert DocSection.model_validate_json(sample.model_dump_json()) == sample
    with pytest.raises(ValidationError):
        DocSection(**sample.model_dump(), extra_field=1)
    with pytest.raises(ValidationError):
        DocSection(**{**sample.model_dump(), "format": "docx"})
    with pytest.raises(ValidationError):
        sample.text = "changed"  # frozen: consumers cannot mutate shared sections
    assert isinstance(load_docs(DEFAULT_DOCS_DIR), list)


# 31. Report accuracy
def test_report_counts_are_exact(tmp_path):
    write(tmp_path, "one.md", md("One", "# One\n\nintro\n\n## A\n\na\n\n## B\n\nb"))
    write(tmp_path, "dir/two.html", "<title>Two</title><meta name='version' content='2'><h1>Two</h1><h2>X</h2><p>x</p>")
    write(tmp_path, "bad.pdf", b"not a pdf", binary=True)
    write(tmp_path, "readme.txt", "ignored")
    sections, report = load_docs_with_report(tmp_path)
    assert (report.files_discovered, report.supported_files, report.documents_loaded) == (4, 3, 2)
    assert report.sections_total == len(sections) == 4
    assert report.documents_by_format == {"md": 1, "html": 1, "pdf": 0}
    assert [d["path"] for d in report.documents_skipped] == ["bad.pdf"]
    assert [e["path"] for e in report.errors] == ["bad.pdf"]
    assert report.unsupported_files == ["readme.txt"]
    assert report.missing_metadata == [{"doc_id": "dir/two", "fields": ["status", "updated"]}]
    assert report.duration_ms >= 0
    first = report.model_dump(exclude={"duration_ms"})
    assert load_docs_with_report(tmp_path)[1].model_dump(exclude={"duration_ms"}) == first


# 32. No source-file modification
def test_source_files_are_not_modified():
    before = tree_fingerprint(DEFAULT_DOCS_DIR)
    ingest(DEFAULT_DOCS_DIR)
    assert tree_fingerprint(DEFAULT_DOCS_DIR) == before


# 33. One bad document does not stop the batch
def test_recovers_from_invalid_documents(tmp_path):
    write(tmp_path, "a-good.md", md("Good", "# Good\n\nfine"))
    write(tmp_path, "b-broken.pdf", b"\x00\x01garbage", binary=True)
    write(tmp_path, "c-latin.md", b"caf\xe9", binary=True)
    write(tmp_path, "d-empty.html", "")
    write(tmp_path, "e-good.html", "<title>E</title><h1>E</h1><p>fine too</p>")
    sections, report = load_docs_with_report(tmp_path)
    assert [s.doc_id for s in sections] == ["a-good", "e-good"]
    assert [d["path"] for d in report.documents_skipped] == ["b-broken.pdf", "c-latin.md", "d-empty.html"]
    assert all(d["reason"] for d in report.documents_skipped)


# 34. No unnecessary dependencies
def test_only_approved_imports():
    tree = ast.parse(Path(docs_loader.__file__).read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    third_party = roots - {"__future__", "hashlib", "logging", "os", "re", "time", "unicodedata",
                           "collections", "dataclasses", "datetime", "html", "io", "pathlib", "typing", "app"}
    assert third_party == {"yaml", "pydantic", "pypdf"}


# Configuration errors
def test_invalid_folder_raises(tmp_path):
    with pytest.raises(DocsLoaderError):
        load_docs(tmp_path / "missing")
    file_path = write(tmp_path, "file.md", "x")
    with pytest.raises(DocsLoaderError):
        load_docs(file_path)
    with pytest.raises(DocsLoaderError):
        load_docs("")


def test_empty_folder_gives_empty_result(tmp_path):
    sections, report = load_docs_with_report(tmp_path)
    assert sections == [] and report.files_discovered == 0 and report.documents_loaded == 0


def test_invalid_file_names_are_reported(tmp_path):
    write(tmp_path, "has space.md", md("S", "# S\n\ntext"))
    sections, report = load_docs_with_report(tmp_path)
    assert sections == [] and "invalid document id" in report.documents_skipped[0]["reason"]


def test_oversized_file_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(docs_loader, "MAX_FILE_BYTES", 50)
    write(tmp_path, "big.md", md("Big", "# Big\n\n" + "x" * 100))
    sections, report = load_docs_with_report(tmp_path)
    assert sections == [] and report.documents_skipped[0]["reason"] == "file is larger than 50 bytes"
