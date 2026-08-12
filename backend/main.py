"""
Nuvilog FastAPI app.

Currently wires stage 1 (input handler) -> stage 3 (schema registry,
used to know what to extract) -> stage 2 (extraction) -> stage 4
(confidence engine) end-to-end, and persists the result. Contradiction
detection, enrichment, and batch mode are stubbed in their own modules
and not yet called from here — see pipeline/contradiction_detector.py etc.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from models.db import Product, ProductField, get_db, init_db
from models.db import SupabaseSession as Session
from pipeline.confidence_engine import score_fields
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
    (confidence engine) on one product and persist the scored fields."""
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

    product = Product(
        raw_input_type=input_type,
        raw_input_ref=raw_doc.source_ref,
        category=category,
        status="scored",
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
    db.commit()

    return {
        "product_id": product.id,
        "category": category,
        "raw_text_preview": raw_doc.raw_text[:500],
        "table_count": len(raw_doc.tables),
        "fields": [f.model_dump() for f in scored],
    }


@app.get("/api/products/{product_id}")
def get_product(product_id: str, db: Session = Depends(get_db)) -> dict:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    return {
        "id": product.id,
        "category": product.category,
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
