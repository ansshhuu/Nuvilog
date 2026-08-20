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
import re
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
from pipeline.dishwasher_schema import DISHWASHER_ATTRIBUTE_SCAFFOLD
from pipeline.enrichment import enrich
from pipeline.extractor import extract_fields
from pipeline.inferred_rules import NOT_BUILT
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


# ---------------------------------------------------------------------------
# Evaluation report — read-only, no DB, no LLM.
# ---------------------------------------------------------------------------

# Structural constants derived from the pipeline implementation:
#   Tier 2 = 11 inferred rules (dishwasher_schema.py, all rows, always pass).
#   Tier 3 total differs by 1 between known and unknown rows because the
#   description honesty check only scores the generated descriptions, and the
#   description generator produces slightly different outputs per known state —
#   this is reflected in step6_7_report.md (176/176 known, 177/177 unknown).
#   Tier 1 is only meaningful for is_known=True rows (252 columns with ground
#   truth); for all others the md says "n/a".
_TIER2_TOTAL = 11
_TIER1_TOTAL = 252
_TIER3_TOTAL_KNOWN = 176
_TIER3_TOTAL_UNKNOWN = 177

_REPORTS_DIR = Path(__file__).resolve().parent / "reports"

# Regex to parse a table row from step8_report.md:
#   | MPN | desc_before -> desc_after | attr_before -> attr_after | t1_before -> t1_after | ... |
_STEP8_ROW_RE = re.compile(
    r"\|\s*(\w+)\s*\|"
    r"\s*([\d/]+)\s*->\s*([\d/]+)\s*\|"
    r"\s*([\d/]+)\s*->\s*([\d/]+)\s*\|"
    r"\s*([\d/]+)\s*->\s*([\d/]+)\s*\|"
    r"\s*([\d/]+)\s*->\s*([\d/]+)\s*\|"
    r"\s*([\d/]+)\s*->\s*([\d/]+)\s*\|",
)

# Row-count pattern inside a NOT_BUILT reason string.
# Matches "10 real range rows", "8 real rows", "3 real rows", etc.
# {0,2} so zero intervening category words (washer/microwave/freezer/cooktop
# reasons say "8 real rows (e.g. …)") is also captured.
_ROW_COUNT_RE = re.compile(r"(\d+)\s+real\s+(?:\w+\s+){0,2}rows?")


def _not_built_entry(name: str, reason: str) -> dict:
    """Convert one NOT_BUILT (name, reason) tuple to a display-ready dict.

    Short label: strip known boilerplate suffixes from the name and uppercase.
    Detail line: either "N rows, no ground truth" (when a row count is found
    in the reason) or "requires paid API" (for the search-based enrichment
    entry), or None when neither applies.
    """
    label = (
        name.upper()
        # Strip the repeated suffix patterns so only the subject remains.
        .replace(" ATTRIBUTE SCAFFOLD", "")
        .replace(" (LAUNDRY)", "")
        .replace(" NORMALIZATION TABLE", "")
        .replace(" CONVERSION TABLE", "")
        .replace(" / CONSTRAINED VOCABULARY", "")
        .replace(" FOR ROWS WITHOUT A KNOWN URL", "")
        # The manufacturer entry has an extremely long suffix — trim to subject.
        .replace(" AGAINST A MASTER LIST", "")
        .strip()
    )

    count_m = _ROW_COUNT_RE.search(reason)
    if count_m:
        return {"label": label, "detail": f"{count_m.group(1)} rows, no ground truth"}

    if "paid" in reason.lower() or "search" in name.lower():
        return {"label": "SEARCH-BASED ENRICHMENT", "detail": "requires paid API"}

    return {"label": label, "detail": None}


@app.get("/api/evaluation-report")
def get_evaluation_report() -> dict:
    """Read-only evaluation report.

    Derives structured Tier 1/2/3 scores from ``step6_7_report.json`` using
    the structural constants above (no separate JSON breakdown exists — the
    file only has combined pass/fail totals, so we back-calculate per tier).

    Before/after comparison data comes from ``step8_report.md`` (no JSON twin
    exists) parsed with a regex that matches the markdown table rows.

    NOT_BUILT entries come directly from ``pipeline.inferred_rules.NOT_BUILT``
    so the list stays in sync whenever a backend entry is added or removed.
    """
    # --- Tier scores ----------------------------------------------------------
    step67_path = _REPORTS_DIR / "step6_7_report.json"
    raw_rows: list[dict] = json.loads(step67_path.read_text(encoding="utf-8"))

    rows = []
    for row in raw_rows:
        is_known: bool = row["is_known"]
        counts: dict = row["counts"]
        tier3_failures: list = row.get("tier3_failures", [])

        tier3_total = _TIER3_TOTAL_KNOWN if is_known else _TIER3_TOTAL_UNKNOWN
        tier3_pass = tier3_total - len(tier3_failures)
        tier2_pass = _TIER2_TOTAL

        if is_known:
            # Back-calculate Tier 1 from total pass − Tier 2 pass − Tier 3 pass.
            # This is valid because all three tiers are non-overlapping.
            tier1_pass = counts["pass"] - tier2_pass - tier3_pass
            tier1: dict | None = {"score": tier1_pass, "total": _TIER1_TOTAL}
        else:
            tier1 = None  # N/A for rows without ground truth

        rows.append(
            {
                "mpn": row["mpn"],
                "is_known": is_known,
                "tier1": tier1,
                "tier2": {"score": tier2_pass, "total": _TIER2_TOTAL},
                "tier3": {
                    "score": tier3_pass,
                    "total": tier3_total,
                    "fabrication_violations": len(tier3_failures),
                },
            }
        )

    # --- Before/after comparison (step8_report.md) ----------------------------
    step8_text = (_REPORTS_DIR / "step8_report.md").read_text(encoding="utf-8")
    comparison: dict[str, dict] = {}
    for m in _STEP8_ROW_RE.finditer(step8_text):
        mpn_key = m.group(1)
        comparison[mpn_key] = {
            "descriptions_nonempty": {"baseline": m.group(2), "enriched": m.group(3)},
            "attributes_verified": {"baseline": m.group(4), "enriched": m.group(5)},
            "tier1_score": {"baseline": m.group(6), "enriched": m.group(7)},
        }

    # --- NOT_BUILT from inferred_rules ----------------------------------------
    from pipeline.inferred_rules import NOT_BUILT  # local import avoids circular issues

    not_built = [_not_built_entry(name, reason) for name, reason in NOT_BUILT]

    return {"rows": rows, "comparison": comparison, "not_built": not_built}




# ---------------------------------------------------------------------------
# Description formats — read-only, reads pipeline CSV output.
# ---------------------------------------------------------------------------

_OUTPUT_DIR = Path(__file__).resolve().parent / "output"
_DELIVERY_CSV = _OUTPUT_DIR / "dishwasher_delivery_rows.csv"

# Confidence level → field status word + colour token understood by the UI.
_CONFIDENCE_TO_STATUS = {
    "high": "verbatim",
    "medium": "inferred",
    "low": "unverified",
}

# Source fields that feed each description format, with their likely status.
# These are derived from description_builder.trusted_fields_for_row() logic:
# BRAND_NAME/MANUFACTURER_NAME only exist for is_known rows; the 8 thin rows
# only have Mfg_Part_Num and Part_Desc as trusted inputs.
_FORMAT_SOURCE_FIELDS: dict[str, list[tuple[str, str]]] = {
    "INVOICE_DESC": [
        ("Mfg_Part_Num", "high"),
        ("Part_Desc", "high"),
    ],
    "MOBILE_DESC": [
        ("BRAND_NAME", "high"),
        ("MANUFACTURER_NAME", "medium"),
        ("Mfg_Part_Num", "high"),
        ("Part_Desc", "high"),
    ],
    "SHORT_DESC": [
        ("BRAND_NAME", "high"),
        ("Mfg_Part_Num", "high"),
        ("Part_Desc", "high"),
    ],
    "LONG_DESC1": [
        ("BRAND_NAME", "high"),
        ("Part_Desc", "high"),
        ("ATTRIBUTE_VALUE 1", "medium"),
        ("ATTRIBUTE_VALUE 3", "medium"),
        ("ATTRIBUTE_VALUE 15", "medium"),
    ],
    "MARKETING_DESCRIPTION": [
        ("BRAND_NAME", "high"),
        ("Part_Desc", "medium"),
        ("ATTRIBUTE_VALUE 1", "low"),
    ],
}

# The char-limit pairs (min, max) for each format. Derived from
# description_builder.FormatSpec / build_format_specs():
#   INVOICE_DESC max=40, MOBILE_DESC observed 60-80, SHORT_DESC no strict limit,
#   LONG_DESC1 60-80 from brief, MARKETING_DESCRIPTION ~100-150.
# The UI shows "0 / LIMIT" as specified.
_FORMAT_LIMITS: dict[str, tuple[int | None, int | None]] = {
    "INVOICE_DESC": (None, 40),
    "MOBILE_DESC": (60, 80),
    "SHORT_DESC": (None, 80),
    "LONG_DESC1": (60, 80),
    "MARKETING_DESCRIPTION": (100, 150),
}


def _limit_display(field_name: str) -> str:
    """Return the limit string shown in the badge, e.g. '40', '60-80', '100-150'."""
    lo, hi = _FORMAT_LIMITS.get(field_name, (None, None))
    if lo is not None and hi is not None:
        return f"{lo}-{hi}"
    if hi is not None:
        return str(hi)
    if lo is not None:
        return f"{lo}+"
    return "—"


def _source_fields_for_row(
    field_name: str, row: dict[str, str], is_known: bool
) -> list[dict]:
    """
    Return the source-field confidence list for this format and row.

    For is_known rows all declared source fields may be present.
    For unknown rows, only Mfg_Part_Num and Part_Desc are trusted inputs
    (description_builder.trusted_fields_for_row returns only those for
    expected=None rows). The returned status reflects what is actually in
    the row, not what the format ideally wants.
    """
    base = _FORMAT_SOURCE_FIELDS.get(field_name, [])
    result = []
    for src_field, base_confidence in base:
        # Whether this field actually has a value in this row.
        value = row.get(src_field, "").strip()
        if not is_known and src_field not in ("Mfg_Part_Num", "Part_Desc"):
            # Unknown rows: only the 2 raw input columns are trusted.
            status = "unverified"
        elif value:
            status = _CONFIDENCE_TO_STATUS.get(base_confidence, "unverified")
        else:
            status = "unverified"
        result.append({"field": src_field, "status": status})
    return result


def _format_rule_payload(field_name: str, specs: dict) -> dict:
    """Build the generation-rule payload for the right-panel from a FormatSpec."""
    spec = specs.get(field_name)
    if spec is None:
        return {}

    lo, hi = _FORMAT_LIMITS.get(field_name, (None, None))
    limit_str = _limit_display(field_name)

    # Derive worked example from the known rows' actual generated text.
    # (The CSV row for PDSH4816AF is index 1 in the data, which has real values.)

    casing = "ALL CAPS" if spec.uppercase else "Title Case / Mixed"
    rule_text = spec.rule
    confidence = spec.confidence  # "high" | "medium" | "low"

    # Only HIGH-confidence rules are presented as authoritative per spec.
    is_authoritative = confidence == "high"

    return {
        "field": field_name,
        "confidence": confidence,
        "is_authoritative": is_authoritative,
        "char_limit": limit_str,
        "char_min": lo,
        "char_max": hi,
        "casing": casing,
        "rule": rule_text,
        "evidence": spec.evidence,
    }


@app.get("/api/description-formats")
def get_description_formats(record: int = 0) -> dict:
    """
    Per-row description format view.

    Reads from backend/output/dishwasher_delivery_rows.csv (10 rows, real
    pipeline output). `record` is 0-indexed. Returns the 5 description fields
    for that row, with char counts, generation rules from build_format_specs(),
    and source-field confidence.

    REGENERATE ALL has no real backend action — this endpoint intentionally
    does not trigger a re-run (that would need an LLM call, rate limiting,
    and the same careful exclusion-filter guard as description_builder.py).
    The UI disables that button with an honest tooltip.
    """
    import csv as csv_module
    from pipeline.description_builder import DESCRIPTION_FIELDS, build_format_specs

    if not _DELIVERY_CSV.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                "Pipeline output not found. Run the dishwasher pipeline first "
                "to generate backend/output/dishwasher_delivery_rows.csv."
            ),
        )

    with _DELIVERY_CSV.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv_module.DictReader(fh)
        rows = list(reader)

    if not rows:
        raise HTTPException(status_code=503, detail="Pipeline output CSV is empty.")

    total = len(rows)
    if record < 0 or record >= total:
        raise HTTPException(
            status_code=400,
            detail=f"record must be 0–{total - 1}; got {record}.",
        )

    row = rows[record]
    mpn = (row.get("Mfg_Part_Num") or "").strip()
    part_desc = (row.get("Part_Desc") or "").strip()

    # is_known: only the 2 rows with real MANUFACTURER_NAME have full ground truth.
    is_known = bool((row.get("MANUFACTURER_NAME") or "").strip())

    # Category is always DISHWASHER for all 10 rows in this file.
    category = "DISHWASHER"

    # Build format specs from the real backend rules (not hand-typed).
    specs = build_format_specs()

    # Assemble the 5-format cards.
    formats = []
    for field_name in DESCRIPTION_FIELDS:
        text = (row.get(field_name) or "").strip()
        generated = bool(text)
        char_count = len(text)
        lo, hi = _FORMAT_LIMITS.get(field_name, (None, None))
        within_limit = True
        if generated:
            if hi is not None and char_count > hi:
                within_limit = False
            if lo is not None and char_count < lo:
                within_limit = False

        # Reason string: pulled from the real spec evidence/rule when not generated.
        not_generated_reason: str | None = None
        if not generated:
            spec = specs.get(field_name)
            if spec:
                # Mirror description_builder.py's logic: thin rows lack BRAND_NAME,
                # so only formats that can run from Mfg_Part_Num+Part_Desc ever get
                # content. The spec's evidence describes exactly why — surface that.
                if not is_known:
                    not_generated_reason = (
                        "insufficient verified source data "
                        "(no BRAND_NAME recovered)"
                    )
                else:
                    not_generated_reason = f"rule confidence too low: {spec.evidence}"

        formats.append(
            {
                "field": field_name,
                "text": text if generated else None,
                "generated": generated,
                "char_count": char_count,
                "char_limit": _limit_display(field_name),
                "char_min": lo,
                "char_max": hi,
                "within_limit": within_limit,
                "not_generated_reason": not_generated_reason,
                "source_fields": _source_fields_for_row(field_name, row, is_known),
                "rule": _format_rule_payload(field_name, specs),
            }
        )

    return {
        "record": record,
        "total": total,
        "mpn": mpn,
        "part_desc": part_desc,
        "is_known": is_known,
        "category": category,
        "formats": formats,
    }


@app.get("/api/manufacturer-enrichment")
def get_manufacturer_enrichment(record: int = 0) -> dict:
    """
    Mock endpoint for Manufacturer Enrichment screen proof of concept.
    Returns deterministic results for the two known rows (PDSH4816AF and WDTS7024RZ)
    and an unattempted state for all others.
    """
    import csv as csv_module
    import datetime

    if not _DELIVERY_CSV.exists():
        raise HTTPException(
            status_code=503,
            detail="Pipeline output not found. Run the dishwasher pipeline first.",
        )

    with _DELIVERY_CSV.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv_module.DictReader(fh)
        rows = list(reader)

    if not rows:
        raise HTTPException(status_code=503, detail="Pipeline output CSV is empty.")

    total = len(rows)
    if record < 0 or record >= total:
        raise HTTPException(
            status_code=400,
            detail=f"record must be 0–{total - 1}; got {record}.",
        )

    row = rows[record]
    mpn = (row.get("Mfg_Part_Num") or "").strip()
    
    from pipeline.dishwasher_schema import DISHWASHER_ATTRIBUTE_SCAFFOLD
    
    fields = []
    
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if mpn == "PDSH4816AF":
        status = "timeout"
        url = "https://www.frigidaire.com/en/p/kitchen/dishwashers/built-in-dishwashers/PDSH4816AF"
        error = "Source unreachable — request timed out after 10s"
        page_text_excerpt = None
        for attr in DISHWASHER_ATTRIBUTE_SCAFFOLD:
            fields.append({
                "field_name": attr.label,
                "value": None,
                "confidence": "unverified",
                "snippet": None,
            })
    elif mpn == "WDTS7024RZ":
        status = "success"
        url = "https://learnwhirlpool.com/product/wdts7024rz"
        error = None
        page_text_excerpt = "Load more and run less with our quietest and largest capacity dishwasher. The Eco Series WDTS7024RZ brings advanced cleaning... 24 in W x 24-1/4 in D size. Sound level is 41 dBA..."
        
        verified_fields = {
            "Series": {"value": "Eco Series", "snippet": "The Eco Series WDTS7024RZ brings advanced cleaning..."},
            "Size": {"value": "24 in W x 24-1/4 in D", "snippet": "24 in W x 24-1/4 in D size."},
            "Sound Level": {"value": "41", "snippet": "Sound level is 41 dBA..."},
            "Additional Information": {"value": "Load more and run less with our quietest and largest capacity dishwasher.", "snippet": "Load more and run less with our quietest and largest capacity dishwasher."},
        }
        
        for attr in DISHWASHER_ATTRIBUTE_SCAFFOLD:
            if attr.label in verified_fields:
                val = verified_fields[attr.label]
                fields.append({
                    "field_name": attr.label,
                    "value": val["value"],
                    "confidence": "verbatim",
                    "snippet": val["snippet"],
                })
            else:
                fields.append({
                    "field_name": attr.label,
                    "value": None,
                    "confidence": "unverified",
                    "snippet": None,
                })
    else:
        status = "not_attempted"
        url = None
        error = None
        page_text_excerpt = None
        for attr in DISHWASHER_ATTRIBUTE_SCAFFOLD:
            fields.append({
                "field_name": attr.label,
                "value": None,
                "confidence": "unverified",
                "snippet": None,
            })
            
    return {
        "record": record,
        "total": total,
        "mpn": mpn,
        "status": status,
        "url": url,
        "timestamp": timestamp,
        "page_text_excerpt": page_text_excerpt,
        "error": error,
        "fields": fields,
    }


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


@app.get("/api/dishwasher-schema")
def get_dishwasher_schema() -> dict:
    """The real 15-slot dishwasher scaffold from pipeline/dishwasher_schema.py,
    plus the 5 other-appliance sub-types confirmed NOT_BUILT (pipeline/
    inferred_rules.py) rather than guessed from Part_Desc text.

    The scaffold has no `type`, `required`, or `valid_range` concept — those
    are schema_registry.py/FieldDef ideas, and dishwasher_schema.py's
    DishwasherAttribute dataclass simply doesn't carry them. Only `unit`
    (`typical_uom`, null for free-text labels) and `evidence` (the note each
    slot's UOM/format was confirmed against) are real fields on it — this
    endpoint returns exactly that, nothing invented to fill the other columns.
    """
    fields = [
        {
            "index": attr.index,
            "label": attr.label,
            "unit": attr.typical_uom,
            "evidence": attr.evidence,
        }
        for attr in DISHWASHER_ATTRIBUTE_SCAFFOLD
    ]

    not_built = []
    for name, reason in NOT_BUILT:
        if not name.endswith("attribute scaffold") or name == "dishwasher attribute scaffold":
            continue
        match = re.search(r"(\d+) real", reason)
        not_built.append({
            "sub_type": name.removesuffix(" attribute scaffold"),
            "row_count": int(match.group(1)) if match else None,
            "reason": reason,
        })

    return {
        "category": "DISHWASHER",
        "display_name": "Dishwasher",
        "description": "The only sub-type with ground-truth evidence behind its attribute scaffold.",
        "fields": fields,
        "not_built": not_built,
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
        # None for rows written before the column existed — passed through as
        # null rather than defaulted to [], so the client can tell "unknown"
        # from "no conflicting values".
        "mentions": row.get("mentions"),
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
                    # Null on rows written before the column existed; see
                    # _flag_payload for why that is passed through as-is.
                    "mentions": f.mentions,
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
