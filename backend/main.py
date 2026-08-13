"""
Nuvilog FastAPI app.

Wires stage 1 (input handler) -> stage 3 (schema registry, used to know
what to extract) -> stage 2 (extraction) -> stage 4 (confidence engine)
-> stage 5 (contradiction detection) -> stage 6 (enrichment) end-to-end,
and persists the result — once per product on `POST /api/ingest`, and
over N products on `POST /api/ingest/batch` (stage 7), which loops the
very same path via pipeline/batch_runner.py.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from models.db import Product, get_db, init_db
from models.db import SupabaseSession as Session
from pipeline.batch_runner import BatchItem, run_batch_async, summarize
from pipeline.confidence_engine import score_fields
from pipeline.contradiction_detector import detect_contradictions
from pipeline.enrichment import enrich
from pipeline.extractor import extract_fields
from pipeline.input_handler import handle_input
from pipeline.llm_client import LLMClient
from pipeline.persistence import persist_product
from pipeline.schema_registry import registry
from pipeline.types import ExtractionResult, InputType, RawDocument

app = FastAPI(title="Nuvilog", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path(__file__).resolve().parent / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Ceiling on one synchronous batch request — see ingest_batch's docstring for
# why the endpoint waits rather than handing back a batch_id.
#
# 25 is derived, not picked: the provider rate limit sets how long a batch
# takes, at roughly `2 * items / rate_per_minute` minutes, because each item
# spends two LLM calls. At the free tier's 15/min that puts 25 items at about
# 3.7 minutes — already long for a held-open HTTP request, and the point past
# which the async job path in the README becomes the honest answer. Measured:
# 20 items took 165s. On a paid key, raise NUVILOG_GEMINI_RPM and this
# together; they only make sense in proportion.
MAX_BATCH_ITEMS = 25

# How findings rank when they are shown to a reviewer.
#
# "The source says something different" is a stronger signal than "the source
# says nothing at all": a contradiction points at a specific line to go read,
# while an unverified value only means the evidence check found nothing. A
# field can carry both — a fabricated value that the source explicitly
# contradicts is scored `unverified` by stage 4 *and* flagged `contradiction`
# by stage 5 — and in that case the contradiction is the headline.
#
# Anything surfacing findings should order by this, including the review UI
# when it gets built. Both endpoints below already do.
SEVERITY_ORDER = {"contradiction": 0, "out_of_range": 1, "unverified": 2}


def _rank(issue_type: str) -> int:
    return SEVERITY_ORDER.get(issue_type, len(SEVERITY_ORDER))


def _review_findings(scored_fields, flags) -> list[dict]:
    """Everything a reviewer should look at, most severe first.

    Merges the two sources a reviewer cares about — stage 5's validation flags
    and stage 4's unverified fields — into one ranked list, so the client
    doesn't have to re-derive the precedence and get it wrong.

    Sorting is stable, so findings of equal severity keep the order they came
    in (schema field order for both inputs).
    """
    findings = [
        {
            "field_name": flag.field_name,
            "issue_type": flag.issue_type,
            "message": flag.message,
        }
        for flag in flags
    ]

    findings += [
        {
            "field_name": field.field_name,
            "issue_type": "unverified",
            "message": (
                f"'{field.field_name}' has no support anywhere in the source — "
                "AI-suggested, not fact."
            ),
        }
        for field in scored_fields
        if field.confidence_level == "unverified"
    ]

    return sorted(findings, key=lambda finding: _rank(finding["issue_type"]))


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/categories")
def list_categories() -> dict:
    schemas = registry.all_schemas()
    return {
        category: {
            "display_name": s.display_name,
            "description": s.description,
            "fields": [f.model_dump() for f in s.fields],
        }
        for category, s in schemas.items()
    }


@app.post("/api/ingest")
async def ingest(
    category: str = Form(...),
    input_type: InputType = Form(...),
    text_content: Optional[str] = Form(None),
    url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
) -> dict:
    """Run stage 1 (input handler) + stage 2 (extraction) + stage 4
    (confidence engine) + stage 5 (contradiction detection) on one product
    and persist the scored fields and any validation flags."""
    try:
        schema = registry.get(category)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    source_ref = _resolve_source_ref(input_type, text_content, url, file)

    try:
        raw_doc: RawDocument = handle_input(input_type, source_ref)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Input handling failed: {e}")

    if not raw_doc.raw_text.strip():
        raise HTTPException(status_code=422, detail="No extractable text found in input.")

    try:
        extraction: ExtractionResult = extract_fields(raw_doc, schema, LLMClient())
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Extraction failed: {e}")

    scored = score_fields(extraction, raw_doc)
    flags = detect_contradictions(scored, raw_doc, schema)

    # Stage 6 is the last stage before the response, and the only one that is
    # allowed to fail without failing the request: extraction produces the data
    # a reviewer needs, enrichment only produces copy on top of it. A 502 here
    # would throw away a complete scored field set over a missing paragraph, so
    # the error is reported alongside the result instead of replacing it.
    enrichment = None
    enrichment_error = None
    try:
        enrichment = enrich(scored, schema, LLMClient(), flags)
    except Exception as e:
        enrichment_error = f"Enrichment failed: {e}"

    # Shared with the batch runner on purpose: a product ingested in a batch
    # has to land in the database identically to one ingested on its own.
    product = persist_product(
        db,
        input_type=input_type,
        source_ref=raw_doc.source_ref,
        category=category,
        scored=scored,
        flags=flags,
        enrichment=enrichment,
    )

    enriched_fields = list(enrichment.filled_fields) if enrichment else []

    return {
        "product_id": product.id,
        "category": category,
        "description": enrichment.description if enrichment else None,
        "enrichment_error": enrichment_error,
        "raw_text_preview": raw_doc.raw_text[:500],
        "table_count": len(raw_doc.tables),
        "fields": [f.model_dump() for f in scored],
        "enriched_fields": [f.model_dump() for f in enriched_fields],
        "flags": sorted(
            (f.model_dump() for f in flags), key=lambda flag: _rank(flag["issue_type"])
        ),
        # Gap-filled fields are listed here too. They are stored as unverified
        # like any other unsupported value, so GET /api/products/{id} surfaces
        # them as findings when it re-derives this from the database — the two
        # endpoints have to agree on what a reviewer is being shown.
        "review_findings": _review_findings(scored + enriched_fields, flags),
    }


@app.post("/api/ingest/batch")
async def ingest_batch(
    category: Optional[str] = Form(None),
    items: Optional[str] = Form(None),
    files: list[UploadFile] = File(default=[]),
    concurrency: Optional[int] = Form(None),
) -> dict:
    """Stage 7: run the same stages 1-6 path over N inputs.

    Synchronous — the client waits for the whole batch and gets every result
    in one response. See the README for why, in short: at the scale this is
    built for (dozens of items, ~4 in flight) the wait is a minute or two, and
    a batch_id + polling endpoint would add a job table, a status endpoint and
    a way to lose results to a restart in exchange for nothing a demo needs.

    Two ways to supply inputs, usable together so one batch can mix formats:
      * `files` — uploaded pdf/csv, typed from the filename extension, all
        ingested under the form-level `category`.
      * `items` — a JSON array of {"source_type", "source_ref", "category"},
        for text and url inputs. `category` may be omitted per item and falls
        back to the form-level one.

    Same posture as the single ingest: unknown categories are rejected with a
    400 before any LLM call is made. Per-item failures are not 4xx/5xx — they
    come back inside the summary, because the other items succeeded.
    """
    batch_items: list[BatchItem] = []

    for item in _parse_batch_items(items, category):
        batch_items.append(item)

    for upload in files or []:
        suffix = Path(upload.filename or "").suffix.lower()
        input_type = {".pdf": "pdf", ".csv": "csv"}.get(suffix)
        if input_type is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type for batch upload: {upload.filename!r} (expected .pdf or .csv)",
            )
        if not category:
            raise HTTPException(
                status_code=400, detail="category is required when uploading files"
            )
        batch_items.append(
            BatchItem(
                source_type=input_type,
                source_ref=_save_upload(upload, input_type),
                category=category,
            )
        )

    if not batch_items:
        raise HTTPException(status_code=400, detail="No inputs supplied: provide files, items, or both.")

    # A cap, not a queue. Without one a single request could hold a worker for
    # hours; the error names the limit so the client can split the batch. Not a
    # request parameter on purpose — a limit a caller can raise is not a limit.
    if len(batch_items) > MAX_BATCH_ITEMS:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Batch of {len(batch_items)} exceeds the limit of "
                f"{MAX_BATCH_ITEMS} items per request."
            ),
        )

    for item in batch_items:
        try:
            registry.get(item.category)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    results = await run_batch_async(
        batch_items, concurrency=concurrency, llm_factory=LLMClient
    )
    summary = summarize(results, concurrency)

    return {
        "total": summary.total,
        "succeeded": summary.succeeded,
        "failed": summary.failed,
        # Echoed so a client can see what bound was actually applied, whether
        # it came from the request, the environment, or the default.
        "concurrency": summary.concurrency,
        # Fetch full detail for any of these via GET /api/products/{id}.
        "product_ids": summary.product_ids,
        "results": [r.model_dump() for r in results],
    }


def _parse_batch_items(items: Optional[str], default_category: Optional[str]) -> list[BatchItem]:
    if not items:
        return []

    try:
        parsed = json.loads(items)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"items is not valid JSON: {e}")

    if not isinstance(parsed, list):
        raise HTTPException(status_code=400, detail="items must be a JSON array of objects.")

    batch_items: list[BatchItem] = []
    for index, entry in enumerate(parsed):
        if not isinstance(entry, dict):
            raise HTTPException(status_code=400, detail=f"items[{index}] must be an object.")

        item_category = entry.get("category") or default_category
        if not item_category:
            raise HTTPException(
                status_code=400,
                detail=f"items[{index}] has no category, and no form-level category was given.",
            )

        source_type = entry.get("source_type")
        # File paths are deliberately not accepted here: `items` is client-
        # supplied, and letting it name a server path would read arbitrary
        # files off the host. Uploads go through `files`.
        if source_type not in ("text", "url"):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"items[{index}].source_type must be 'text' or 'url' "
                    "(upload pdf/csv inputs through `files` instead)."
                ),
            )

        source_ref = entry.get("source_ref")
        if not source_ref or not str(source_ref).strip():
            raise HTTPException(status_code=400, detail=f"items[{index}].source_ref is required.")

        batch_items.append(
            BatchItem(
                source_type=source_type,
                source_ref=str(source_ref),
                category=item_category,
            )
        )

    return batch_items


def _field_payload(row: dict) -> dict:
    return {
        "field_name": row.get("field_name"),
        "value": row.get("value"),
        "confidence_level": row.get("confidence_level"),
        "evidence_type": row.get("evidence_type"),
        "source_snippet": row.get("source_snippet"),
        "inference_chain": row.get("inference_chain"),
        "is_ai_generated": row.get("is_ai_generated", False),
    }


def _flag_payload(row: dict) -> dict:
    return {
        "field_name": row.get("field_name"),
        "issue_type": row.get("issue_type"),
        "message": row.get("message"),
    }


@app.get("/api/products")
def list_products(limit: int = 200, db: Session = Depends(get_db)) -> dict:
    """Every product with its fields and flags, newest first.

    Carries the full field and flag rows rather than a precomputed per-product
    tally. The review UI already derives a field's status from
    `confidence_level` plus any contradiction flag, and that precedence is
    subtle enough (see SEVERITY_ORDER) that having a second implementation of
    it — one for the list, one for the detail view — is how the two end up
    disagreeing about the same product. One derivation, fed from both.

    One round trip: PostgREST embeds the child tables via the foreign keys
    declared in supabase/schema.sql, so this does not fan out per product.
    """
    response = (
        db.client.table("products")
        .select("*, product_fields(*), validation_flags(*)")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )

    products = []
    for row in response.data or []:
        fields = [_field_payload(f) for f in row.get("product_fields") or []]
        flags = [_flag_payload(f) for f in row.get("validation_flags") or []]
        products.append(
            {
                "id": row.get("id"),
                "category": row.get("category"),
                "description": row.get("description"),
                "raw_input_type": row.get("raw_input_type"),
                "raw_input_ref": row.get("raw_input_ref"),
                "status": row.get("status"),
                "created_at": row.get("created_at"),
                "fields": fields,
                "flags": sorted(flags, key=lambda flag: _rank(flag["issue_type"])),
            }
        )

    return {"products": products, "total": len(products)}


@app.post("/api/products/{product_id}/approve")
def approve_product(product_id: str, db: Session = Depends(get_db)) -> dict:
    """Mark a reviewed product as approved.

    The only status transition the UI can make today. `status` is a plain
    varchar with no CHECK constraint, so this deliberately writes one fixed
    literal rather than accepting a status from the client — an endpoint that
    took an arbitrary string would let a typo become a new status nothing
    downstream recognises.

    Idempotent: approving an already-approved product succeeds and returns the
    same state, so a double-click is not an error.
    """
    updated = db.update(Product, product_id, status="approved")
    if updated is None:
        raise HTTPException(status_code=404, detail="Product not found")

    return {
        "id": updated.id,
        "status": updated.status,
    }


@app.post("/api/products/{product_id}/mark-for-review")
def mark_product_for_review(product_id: str, db: Session = Depends(get_db)) -> dict:
    """Flag a product as needing another look.

    Same shape and same reasoning as approve_product above: one fixed literal,
    not a client-supplied status. The two are the only transitions the UI can
    make, and they are mutually exclusive — writing either simply overwrites
    the other, so a product marked for review can later be approved and vice
    versa without a state machine in between.
    """
    updated = db.update(Product, product_id, status="needs_review")
    if updated is None:
        raise HTTPException(status_code=404, detail="Product not found")

    return {
        "id": updated.id,
        "status": updated.status,
    }


@app.get("/api/products/{product_id}")
def get_product(product_id: str, db: Session = Depends(get_db)) -> dict:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    return {
        "id": product.id,
        "category": product.category,
        "description": product.description,
        "raw_input_type": product.raw_input_type,
        "raw_input_ref": product.raw_input_ref,
        "status": product.status,
        "created_at": product.created_at.isoformat() if product.created_at else None,
        "fields": [
            {
                "field_name": f.field_name,
                "value": f.value,
                "confidence_level": f.confidence_level,
                "evidence_type": f.evidence_type,
                "source_snippet": f.source_snippet,
                "inference_chain": f.inference_chain,
                "is_ai_generated": f.is_ai_generated,
            }
            for f in product.fields
        ],
        "flags": sorted(
            (
                {
                    "field_name": f.field_name,
                    "issue_type": f.issue_type,
                    "message": f.message,
                }
                for f in product.flags
            ),
            key=lambda flag: _rank(flag["issue_type"]),
        ),
        "review_findings": _review_findings(product.fields, product.flags),
    }


def _resolve_source_ref(
    input_type: InputType,
    text_content: Optional[str],
    url: Optional[str],
    file: Optional[UploadFile],
) -> str:
    if input_type == "text":
        if not text_content:
            raise HTTPException(status_code=400, detail="text_content is required for input_type=text")
        return text_content

    if input_type == "url":
        if not url:
            raise HTTPException(status_code=400, detail="url is required for input_type=url")
        return url

    if input_type in ("pdf", "csv"):
        if not file:
            raise HTTPException(status_code=400, detail=f"file is required for input_type={input_type}")
        return _save_upload(file, input_type)

    raise HTTPException(status_code=400, detail=f"Unsupported input_type: {input_type}")


def _save_upload(file: UploadFile, input_type: InputType) -> str:
    """Copy an upload into UPLOAD_DIR and return its path.

    Stage 1 reads pdf/csv from a path, so the bytes have to land on disk
    first. Shared by the single and batch endpoints so uploads from either
    are stored the same way.
    """
    suffix = Path(file.filename or "").suffix or f".{input_type}"
    # mkstemp hands back an open descriptor as well as a path. Writing through
    # that descriptor rather than reopening the path closes it — a leaked one
    # keeps the file locked on Windows, and a batch leaks one per upload.
    handle, dest = tempfile.mkstemp(dir=UPLOAD_DIR, suffix=suffix)
    with os.fdopen(handle, "wb") as out:
        shutil.copyfileobj(file.file, out)
    return dest
