"""
Nuvilog FastAPI app.

Currently wires stage 1 (input handler) -> stage 3 (schema registry,
used to know what to extract) -> stage 2 (extraction) -> stage 4
(confidence engine) -> stage 5 (contradiction detection) -> stage 6
(enrichment) end-to-end, and persists the result. Batch mode is stubbed
in its own module and not yet called from here — see
pipeline/batch_runner.py.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from models.db import Product, ProductField, ValidationFlag, get_db, init_db
from models.db import SupabaseSession as Session
from pipeline.confidence_engine import score_fields
from pipeline.contradiction_detector import detect_contradictions
from pipeline.enrichment import enrich
from pipeline.extractor import extract_fields
from pipeline.input_handler import handle_input
from pipeline.llm_client import LLMClient
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

    product = Product(
        raw_input_type=input_type,
        raw_input_ref=raw_doc.source_ref,
        category=category,
        status="scored",
        description=enrichment.description if enrichment else None,
    )
    db.add(product)
    db.flush()  # assigns product.id

    for f in scored:
        db.add(
            ProductField(
                product_id=product.id,
                field_name=f.field_name,
                value=f.value,
                source_snippet=f.source_snippet,
                confidence_level=f.confidence_level,
                evidence_type=f.evidence_type,
                inference_chain=f.inference_chain,
                is_ai_generated=f.is_ai_generated,
            )
        )

    # Enrichment's own values go into the same table under the same trust
    # labels as everything else — unverified, AI-generated, no evidence. There
    # is deliberately no "generated by enrichment, trust it" shortcut.
    for enriched in enrichment.filled_fields if enrichment else []:
        db.add(
            ProductField(
                product_id=product.id,
                field_name=enriched.field_name,
                value=enriched.value,
                source_snippet=None,
                confidence_level=enriched.confidence_level,
                evidence_type="none",
                inference_chain=None,
                is_ai_generated=enriched.is_ai_generated,
            )
        )

    for flag in flags:
        db.add(
            ValidationFlag(
                product_id=product.id,
                field_name=flag.field_name,
                issue_type=flag.issue_type,
                message=flag.message,
            )
        )
    db.commit()

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
        suffix = Path(file.filename or "").suffix or f".{input_type}"
        dest = Path(tempfile.mkstemp(dir=UPLOAD_DIR, suffix=suffix)[1])
        with open(dest, "wb") as out:
            shutil.copyfileobj(file.file, out)
        return str(dest)

    raise HTTPException(status_code=400, detail=f"Unsupported input_type: {input_type}")
