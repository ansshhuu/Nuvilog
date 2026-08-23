"""
Stage 1: input handler.

Contract: handle_input(source_type, source_ref) -> RawDocument
Every input type — pdf, csv, text, url — normalizes to the same shape:
raw_text + tables. Downstream stages never need to know where the text
came from.
"""
from __future__ import annotations

import csv
import os
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from pipeline.manufacturer_enrichment import _is_unsafe_target
from pipeline.types import InputType, RawDocument

OCR_MIN_CHARS_PER_PAGE = 20  # below this we assume the page is a scanned image


def handle_input(source_type: InputType, source_ref: str) -> RawDocument:
    """Dispatch to the right handler and return a normalized RawDocument.

    source_ref is a file path for pdf/csv, a URL for url, and the raw
    text itself for text.
    """
    if source_type == "pdf":
        return _handle_pdf(source_ref)
    if source_type == "csv":
        return _handle_csv(source_ref)
    if source_type == "text":
        return _handle_text(source_ref)
    if source_type == "url":
        return _handle_url(source_ref)
    raise ValueError(f"Unsupported source_type: {source_type}")


def _handle_pdf(path: str) -> RawDocument:
    import pdfplumber

    text_parts: list[str] = []
    tables: list[list[list[str]]] = []
    ocr_pages = 0

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""

            if len(page_text.strip()) < OCR_MIN_CHARS_PER_PAGE:
                ocr_text = _ocr_page(page)
                if ocr_text:
                    page_text = ocr_text
                    ocr_pages += 1

            text_parts.append(page_text)

            for table in page.extract_tables() or []:
                cleaned = [[cell if cell is not None else "" for cell in row] for row in table]
                if cleaned:
                    tables.append(cleaned)

    return RawDocument(
        source_type="pdf",
        source_ref=path,
        raw_text="\n\n".join(text_parts).strip(),
        tables=tables,
        metadata={"page_count": len(text_parts), "ocr_pages": ocr_pages},
    )


def _ocr_page(page) -> str:
    """Best-effort OCR fallback for scanned/image-only PDF pages.

    Requires the tesseract binary to be installed on the host. If it's
    missing we degrade gracefully to an empty string rather than crashing
    the whole pipeline on one bad page.
    """
    try:
        import pytesseract

        tesseract_cmd = os.getenv("TESSERACT_CMD")
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

        image = page.to_image(resolution=300).original
        return pytesseract.image_to_string(image)
    except Exception:
        return ""


def _handle_csv(path: str) -> RawDocument:
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        rows = [row for row in reader]

    table = rows
    text = "\n".join(", ".join(row) for row in rows)

    return RawDocument(
        source_type="csv",
        source_ref=path,
        raw_text=text,
        tables=[table] if table else [],
        metadata={"row_count": len(rows)},
    )


def _handle_text(text: str) -> RawDocument:
    return RawDocument(
        source_type="text",
        source_ref="inline",
        raw_text=text.strip(),
        tables=[],
        metadata={},
    )


_MAX_URL_REDIRECTS = 5


def _handle_url(url: str) -> RawDocument:
    """Fetch `url` for ingestion.

    `url` is client-supplied (POST /api/ingest, input_type=url), so this is
    an SSRF surface exactly like fetch_manufacturer_page's — same guard
    (_is_unsafe_target), same manual one-hop-at-a-time redirect handling so a
    same-origin-looking URL can't 302 into a private/metadata address after
    the initial check passes.
    """
    if _is_unsafe_target(url):
        raise ValueError("URL refused: not a public http(s) host")

    current_url = url
    for _ in range(_MAX_URL_REDIRECTS):
        resp = requests.get(
            current_url,
            timeout=20,
            headers={"User-Agent": "Nuvilog/0.1"},
            allow_redirects=False,
        )
        if resp.is_redirect:
            next_url = resp.headers.get("Location")
            if not next_url:
                raise ValueError("Redirect with no Location header")
            current_url = urljoin(current_url, next_url)
            if _is_unsafe_target(current_url):
                raise ValueError("Redirect target refused: not a public http(s) host")
            continue
        resp.raise_for_status()
        break
    else:
        raise ValueError(f"Too many redirects (> {_MAX_URL_REDIRECTS})")

    soup = BeautifulSoup(resp.text, "lxml")
    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())

    tables: list[list[list[str]]] = []
    for html_table in soup.find_all("table"):
        rows = []
        for tr in html_table.find_all("tr"):
            cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
            if cells:
                rows.append(cells)
        if rows:
            tables.append(rows)

    return RawDocument(
        source_type="url",
        source_ref=url,
        raw_text=text,
        tables=tables,
        metadata={"status_code": resp.status_code},
    )
