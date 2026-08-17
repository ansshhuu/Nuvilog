"""
Step 6/7 Section B: full single-row orchestration.

    process_row(input_row) -> dict[str, str]   # a full 252-column delivery row

This is composition, not new logic. Every decision below is made by a
module that already exists; this file's only job is calling them in the
right order and laying their outputs into the right columns. Nothing here
re-implements a sentinel table, a regex, a confidence rule, or a prompt.

CRITICAL DESIGN CHOICE: process_row takes ONLY the raw 6-column input row.
It is never handed the worked-example ground truth, even for the 2 rows
where that ground truth happens to exist. A production pipeline never has
oracle access to the answer at inference time, and the 2 known rows are
not special inputs — they are just 2 of the 1000 rows that happen to have
a graded answer sitting next to them in a different file. Giving
process_row a secret `expected=` back door would make this file lie about
what the pipeline can actually do. (Contrast with the step 6 exploration
scripts, `step6_description_builder.py` / `step7_full_pipeline.py`, which
DO read the known answer for those 2 rows on purpose — they exist to show
"here is what we could generate if this specific row's real attributes
were available," a different and clearly-labeled question. This module
answers "what does the pipeline itself produce," which is the honest
baseline everything else should be measured against.)

One direct consequence, stated up front rather than discovered later: for
the 2 known dishwasher rows, process_row's output will NOT match the real
answer on Series/Voltage/MANUFACTURER_NAME/etc. — those values came from
an external product lookup (see manufacturer_normalizer.py and
dishwasher_schema.py's docstrings), which this pipeline does not and
cannot perform from a 6-column input row alone. That gap is the honest
measurement Section C's report is built to show, not a bug to paper over.

PIPELINE STAGES, IN ORDER, AND WHERE EACH ONE ALREADY LIVES

  1. load/clean
     Sentinel-null the brand columns and split Part_Manuf, reusing
     dataset_loader's exact placeholder set and vendor-code regex (see
     `_clean_single_row` below) rather than re-deriving them for one row.

  2. UOM/fraction normalize
     There is nothing to normalize yet at this point for ANY row, known or
     not: no numeric attribute VALUE exists until stage 4, and stage 4
     only ever produces a blank scaffold here (see stage 4 below — this
     pipeline has no source of real attribute values). The normalization
     that does run — uom_normalizer.add_unit_spacing /
     compress_number_unit_spacing on generated prose, plus
     fraction_converter's format if any bare fraction shows up in
     generated text — happens inside stage 5's post-processing
     (description_builder._postprocess), which is where real numbers
     first exist in this pipeline. Listed here as its own stage per the
     brief; implemented where the data it acts on is actually produced.

  3. manufacturer/brand resolve
     manufacturer_normalizer.resolve_manufacturer(input_row) — honest
     per-row confidence flag ('vendor code present, actual manufacturer
     unresolved' / 'no vendor data'). Never emits MANUFACTURER_NAME or
     BRAND_NAME; see that module for why no function from this input to
     those fields exists.

  4. dishwasher scaffold apply
     dishwasher_schema.blank_dishwasher_scaffold() for any row matching
     is_dishwasher(Part_Desc) — labels populated, values blank, because
     this pipeline has no external-lookup step for Series/Voltage/etc
     (dishwasher_schema.py proved those aren't in the 6-column input for
     any row, known or not). Non-dishwasher rows get no attribute slots
     at all — the confirmed scaffold is scoped to dishwashers only.

  5. 5-format description generation
     description_builder.generate_descriptions(mpn, part_desc,
     expected=None, llm=...) — constrained to exactly what steps 3-4 left
     populated, which for every row here is just Mfg_Part_Num/Part_Desc
     (manufacturer/brand and attribute values are blank per steps 3-4).

  6. assemble
     Lay source passthrough (raw, unmodified — sentinels included, per
     delivery_format's own docstring on that group) + the stage 3/4/5
     outputs into fmt.empty_row(). Every column no stage in this pipeline
     produces stays at empty_row()'s default blank — the tier-3 honesty
     check in evaluation.py is what verifies that blank is actually
     correct for the zero-evidence columns, not an assumption made here.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from pipeline.dataset_loader import BRAND_COLUMNS, _MANUF_CODE_RE, _null_placeholders
from pipeline.delivery_format import DeliveryFormat, load_delivery_format
from pipeline.description_builder import generate_descriptions
from pipeline.dishwasher_schema import blank_dishwasher_scaffold, is_dishwasher
from pipeline.llm_client import LLMClient
from pipeline.manufacturer_normalizer import resolve_manufacturer

RAW_INPUT_COLUMNS = ("Mfg_Part_Num", "Part_Desc", "E1_Brand", "Unilog_Brand", "DIB_Brand", "Part_Manuf")


def _clean_single_row(input_row: dict[str, str]) -> dict[str, Optional[str]]:
    """Stage 1: the same sentinel-nulling dataset_loader.load_input_dataset()
    applies to the full 1000-row frame, run on a length-1 frame instead so a
    single row can go through it without reading the CSV.

    Reuses dataset_loader's private helpers directly (its placeholder set
    and vendor-code regex) rather than copying them — those constants are
    the single source of truth for what counts as an empty brand value.
    """
    frame = pd.DataFrame([{col: input_row.get(col, "") or "" for col in BRAND_COLUMNS}])
    cleaned: dict[str, Optional[str]] = {}
    for col in BRAND_COLUMNS:
        value = _null_placeholders(frame[col].astype("string")).iloc[0]
        cleaned[f"{col}_clean"] = None if pd.isna(value) else str(value)

    manuf_raw = (input_row.get("Part_Manuf") or "").strip()
    match = _MANUF_CODE_RE.match(manuf_raw)
    if match:
        cleaned["manuf_name"] = match.group("name").strip() or None
        cleaned["manuf_code"] = match.group("code").strip()
    else:
        cleaned["manuf_name"] = manuf_raw or None
        cleaned["manuf_code"] = None
    return cleaned


def process_row(
    input_row: dict[str, str],
    llm: Optional[LLMClient] = None,
    fmt: Optional[DeliveryFormat] = None,
) -> dict[str, str]:
    """Run one raw 6-column input row through every built stage and return
    the assembled 252-column delivery-format row. See module docstring for
    the stage-by-stage breakdown and why no ground truth ever enters here.
    """
    fmt = fmt or load_delivery_format()
    llm = llm or LLMClient()

    mfg_part_num = (input_row.get("Mfg_Part_Num") or "").strip()
    part_desc = (input_row.get("Part_Desc") or "").strip()

    # Stage 1: load/clean. Sentinel-nulled brand values are meant for
    # downstream *decisions* (is this brand column real or a placeholder),
    # not for the output row — delivery_format's passthrough contract wants
    # the raw values verbatim, which stage 6 uses instead. Run here so it's
    # a real, verified step rather than a stage that exists only in the
    # docstring; honestly, no stage below currently branches on its result,
    # because none of stages 3-5 consult E1/Unilog/DIB_Brand at all
    # (manufacturer_normalizer works off raw Part_Manuf directly).
    _clean_single_row(input_row)  # run for real, result intentionally unused here

    # Stage 2: UOM/fraction normalize — see module docstring; nothing to
    # normalize yet, real numbers first appear in stage 5's output.

    # Stage 3: manufacturer/brand resolve. Its confidence label
    # ('vendor code present, actual manufacturer unresolved' / 'no vendor
    # data') is metadata about the row, not a delivery-format column value
    # — resolve_manufacturer() never emits MANUFACTURER_NAME/BRAND_NAME, so
    # there is nothing from this stage to write into `row` in stage 6.
    # Callers that want the label call resolve_manufacturer(input_row)
    # again directly (pure, no side effects, cheap) — see
    # step6_7_full_run.py's report for exactly that.
    resolve_manufacturer(input_row)  # run for real, result intentionally unused here

    # Stage 4: dishwasher scaffold apply.
    dishwasher = is_dishwasher(part_desc)
    attribute_columns = blank_dishwasher_scaffold() if dishwasher else {}

    # Stage 5: 5-format description generation. expected=None always — see
    # module docstring for why this file never reads the worked examples.
    descriptions, _invented_number_violations = generate_descriptions(
        mfg_part_num, part_desc, expected=None, llm=llm
    )

    # Stage 6: assemble.
    row = fmt.empty_row()
    for col in RAW_INPUT_COLUMNS:
        row[col] = input_row.get(col, "") or ""
    row.update(attribute_columns)
    row.update(descriptions)
    # MANUFACTURER_NAME / BRAND_NAME deliberately NOT set: vendor_resolution
    # (stage 3) never carries a value for them, by design — see
    # manufacturer_normalizer.py. Its confidence label is available to
    # callers that want to report it (vendor_resolution.confidence_label)
    # but is metadata about the row, not a delivery-format column value.
    return row
