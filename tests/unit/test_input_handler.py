"""Unit tests for stage 1 (input handler).

One stage in isolation: no LLM call, no DB, and no network — the URL path
is exercised against a stubbed `requests.get`.
"""
from __future__ import annotations

import pytest

from pipeline import input_handler
from pipeline.input_handler import handle_input


# ---------------------------------------------------------------------------
# text
# ---------------------------------------------------------------------------
def test_text_input_normalizes_to_raw_document():
    doc = handle_input("text", "  Material: Stainless Steel 18-8  ")

    assert doc.source_type == "text"
    assert doc.source_ref == "inline"  # raw text isn't echoed back as a ref
    assert doc.raw_text == "Material: Stainless Steel 18-8"
    assert doc.tables == []


# ---------------------------------------------------------------------------
# csv
# ---------------------------------------------------------------------------
def test_csv_input_yields_both_text_and_a_table(tmp_path):
    csv_path = tmp_path / "products.csv"
    csv_path.write_text("part,material\nHHC-0250,Stainless Steel 18-8\n", encoding="utf-8")

    doc = handle_input("csv", str(csv_path))

    assert doc.source_type == "csv"
    # One table per document, so a CSV is a single table of rows.
    assert doc.tables == [[["part", "material"], ["HHC-0250", "Stainless Steel 18-8"]]]
    assert "Stainless Steel 18-8" in doc.raw_text
    assert doc.metadata["row_count"] == 2


def test_csv_strips_utf8_bom_from_first_header():
    """Excel writes a BOM; without utf-8-sig the first column name would come
    back as "﻿part" and never match a schema field."""
    import tempfile
    from pathlib import Path

    path = Path(tempfile.mkstemp(suffix=".csv")[1])
    path.write_bytes("﻿part,material\nA,B\n".encode("utf-8"))

    doc = handle_input("csv", str(path))

    assert doc.tables[0][0][0] == "part"


# ---------------------------------------------------------------------------
# pdf
# ---------------------------------------------------------------------------
def test_pdf_input_extracts_text_and_page_count(sample_pdf_path):
    doc = handle_input("pdf", str(sample_pdf_path))

    assert doc.source_type == "pdf"
    assert doc.source_ref == str(sample_pdf_path)
    assert "Hex Head Cap Screw" in doc.raw_text
    assert "Stainless Steel 18-8" in doc.raw_text
    assert doc.metadata["page_count"] >= 1
    # The fixture is a real text PDF, so the OCR fallback must not have fired.
    assert doc.metadata["ocr_pages"] == 0


def test_pdf_ocr_fallback_degrades_to_empty_string_without_tesseract(monkeypatch):
    """A missing tesseract binary must not take down the whole pipeline."""

    class BrokenPage:
        def to_image(self, resolution=300):
            raise OSError("tesseract is not installed")

    assert input_handler._ocr_page(BrokenPage()) == ""


# ---------------------------------------------------------------------------
# url
# ---------------------------------------------------------------------------
def test_url_input_strips_chrome_and_collects_tables(monkeypatch):
    html = """
    <html><body>
      <nav>Home About</nav>
      <script>var tracking = 1;</script>
      <p>Material: Stainless Steel 18-8</p>
      <table><tr><th>Length</th><td>25.4 mm</td></tr></table>
      <footer>Copyright</footer>
    </body></html>
    """

    class FakeResponse:
        status_code = 200
        text = html
        is_redirect = False

        def raise_for_status(self):
            return None

    # Bypass the SSRF guard (_is_unsafe_target) rather than let it run for
    # real: it does a live DNS lookup, which is exactly the network call
    # this file's docstring promises not to make.
    monkeypatch.setattr(input_handler, "_is_unsafe_target", lambda url: False)
    monkeypatch.setattr(input_handler.requests, "get", lambda *a, **k: FakeResponse())

    doc = handle_input("url", "https://example.com/product")

    assert doc.source_ref == "https://example.com/product"
    assert "Stainless Steel 18-8" in doc.raw_text
    # nav / script / footer are decomposed before text extraction.
    assert "tracking" not in doc.raw_text
    assert "Home About" not in doc.raw_text
    assert "Copyright" not in doc.raw_text
    assert doc.tables == [[["Length", "25.4 mm"]]]


def test_url_input_propagates_http_errors(monkeypatch):
    class FailingResponse:
        status_code = 404
        is_redirect = False

        def raise_for_status(self):
            raise RuntimeError("404 Not Found")

    monkeypatch.setattr(input_handler, "_is_unsafe_target", lambda url: False)
    monkeypatch.setattr(input_handler.requests, "get", lambda *a, **k: FailingResponse())

    with pytest.raises(RuntimeError):
        handle_input("url", "https://example.com/missing")


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------
def test_unsupported_source_type_raises():
    with pytest.raises(ValueError, match="Unsupported source_type"):
        handle_input("docx", "whatever.docx")  # type: ignore[arg-type]
