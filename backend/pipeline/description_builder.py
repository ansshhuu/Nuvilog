"""
Step 6: description builder — generate the description formats for the 10
dishwasher rows using the confirmed rules from inferred_rules.py plus the
2 known-good rows, and an LLM call constrained to real per-row data only.

SCOPE: 5 formats, not the 6 in delivery_format's "descriptions" group.

    fmt.group("descriptions").fields == (
        "MOBILE_DESC", "INVOICE_DESC", "SHORT_DESC", "LONG_DESC1",
        "RETAIL_DESC", "MARKETING_DESCRIPTION",
    )

RETAIL_DESC is deliberately out of scope for this module (see
`DESCRIPTION_FIELDS` below) — it was not requested and skipping it is
free: it is NOT a zero-evidence column (both worked examples populate it),
so leaving it blank on generated rows costs nothing on the tier 3 honesty
check, it just means one fewer format is attempted here.

CONSTRUCTION RULES, AND THEIR CONFIDENCE
  INVOICE_DESC   — high confidence on shape (<=40 chars, all-caps, no
                   number/unit spacing — see invoice_desc.max_len_40 and
                   invoice_desc.uppercase in inferred_rules.py, reused
                   here rather than re-derived). LOW confidence on the
                   abbreviation vocabulary itself (SST, BLTLN, ...) — that
                   table does not exist on disk, so the LLM's compressed
                   abbreviations for the 8 thin rows are a best-effort
                   guess, not a confirmed match to house style.
  MOBILE_DESC    — length band is recomputed from the 2 examples at
                   runtime (see `_mobile_length_bounds`), not hand-typed,
                   and logged as holding or not holding against the
                   brief's 60-80 claim. Lead/structure stays LOW
                   confidence: inferred_rules.mobile_desc.comma_list
                   already flags the 2 examples as disagreeing on
                   structure (row 0 leads with MANUFACTURER_NAME, row 1
                   doesn't), and nothing new was learned here to justify
                   upgrading that.
  SHORT_DESC     — MEDIUM: short_desc.brand_first is checked, delimiter
                   style is not (rows disagree: space vs comma).
  LONG_DESC1     — MEDIUM: long_desc.assembly_order's Additional
                   Information suffix is checked; the mid-string ordering
                   is eyeballed and the 2 rows disagree on where the
                   "With" clause goes.
  MARKETING_DESCRIPTION — LOW, functionally unbuildable. n=1 (row 0 is
                   blank). Row 1's real text ("Load more and run less
                   with our quietest and largest capacity dishwasher...")
                   describes a 3rd Rack and adjustable 2nd Rack that
                   appear NOWHERE in the attribute scaffold or any input
                   column — this is external marketing copy, the same
                   kind of external-lookup content that
                   manufacturer_normalizer.py refused to fabricate for
                   MANUFACTURER_NAME/BRAND_NAME. Generation here is
                   restricted to a plain sentence built only from trusted
                   attribute values; it will not and cannot reproduce the
                   real marketing prose.

GENERATION APPROACH
  One LLM call per row (pipeline.llm_client.LLMClient), prompted with
  ONLY the fields verified for that specific row:
    * the 2 known rows: BRAND_NAME/MANUFACTURER_NAME plus every populated
      ATTRIBUTE_VALUE 1-15, pulled straight from that row's own worked
      example — this is real, row-specific ground truth, not an
      inference, the same trust level dishwasher_schema.py uses to
      self-test itself.
    * the other 8 rows: Mfg_Part_Num and Part_Desc only. No
      MANUFACTURER_NAME/BRAND_NAME (manufacturer_normalizer.py proved
      those aren't derivable) and no attribute VALUES (dishwasher_schema.py
      proved those aren't in the input either) — just the label scaffold,
      which the prompt is told is unknown, not omitted.
  This mirrors enrichment.py's exclusion-filter principle exactly: a
  field with no real value is never passed into the prompt, so the model
  cannot dress it up into prose.

  Post-generation, every concrete number in the output is checked against
  the same trusted-field set that was actually sent to the model (see
  `find_invented_numbers`) — constrained prompting is a request, not a
  guarantee, so this is verified rather than assumed. The same check is
  wired into pipeline.evaluation as tier-3 rule
  "description.no_invented_numbers" so it runs on every generated row,
  not only rows this module produces directly.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Literal, Optional

from pipeline.delivery_format import DeliveryFormat, load_delivery_format, load_worked_examples
from pipeline.dishwasher_schema import DISHWASHER_ATTRIBUTE_SCAFFOLD, is_dishwasher
from pipeline.inferred_rules import RULES_BY_ID
from pipeline.llm_client import LLMClient
from pipeline.uom_normalizer import UNIT_REGISTRY, add_unit_spacing

Confidence = Literal["high", "medium", "low"]

# The 5 formats this module builds. A strict subset of
# load_delivery_format().group("descriptions").fields — RETAIL_DESC is the
# one field in that group left out, see module docstring.
DESCRIPTION_FIELDS: tuple[str, ...] = (
    "INVOICE_DESC",
    "MOBILE_DESC",
    "SHORT_DESC",
    "LONG_DESC1",
    "MARKETING_DESCRIPTION",
)


def _assert_fields_are_real(fmt: DeliveryFormat) -> None:
    """Fail loudly if DESCRIPTION_FIELDS ever drifts from the actual header."""
    group_fields = set(fmt.group("descriptions").fields)
    unknown = set(DESCRIPTION_FIELDS) - group_fields
    if unknown:
        raise RuntimeError(
            f"DESCRIPTION_FIELDS names columns not in the delivery format's "
            f"'descriptions' group: {sorted(unknown)}. The header changed — "
            f"re-check delivery_format.py before trusting this module."
        )


@dataclass(frozen=True)
class FormatSpec:
    """One description format's construction rule, with its own confidence."""

    field: str
    confidence: Confidence
    rule: str
    evidence: str
    max_len: Optional[int] = None
    min_len: Optional[int] = None
    uppercase: bool = False
    compress_units: bool = False  # strip the space between a number and a known unit
    ends_with_additional_info: bool = False


def _mobile_length_bounds(examples: list[dict[str, str]]) -> tuple[Optional[int], Optional[int], bool]:
    """Recompute MOBILE_DESC's length band from the examples, not hand-typed.

    Returns (min_len, max_len, brief_60_80_holds). brief_60_80_holds is
    False if either example falls outside 60-80, or if there's no
    evidence at all.
    """
    lengths = [len(v) for r in examples if (v := r.get("MOBILE_DESC", "").strip())]
    if not lengths:
        return None, None, False
    lo, hi = min(lengths), max(lengths)
    return lo, hi, (60 <= lo and hi <= 80)


def build_format_specs(examples: Optional[list[dict[str, str]]] = None) -> dict[str, FormatSpec]:
    """Derive the 5 FormatSpecs from inferred_rules.py plus the worked examples.

    Nothing here upgrades a rule's confidence beyond what inferred_rules.py
    already assigned it — this function only reuses that confidence and
    adds the length arithmetic inferred_rules.py doesn't compute itself.
    """
    examples = examples if examples is not None else load_worked_examples()
    invoice_len_rule = RULES_BY_ID["invoice_desc.max_len_40"]
    invoice_case_rule = RULES_BY_ID["invoice_desc.uppercase"]
    mobile_rule = RULES_BY_ID["mobile_desc.comma_list"]
    short_rule = RULES_BY_ID["short_desc.brand_first"]
    long_rule = RULES_BY_ID["long_desc.assembly_order"]

    mobile_lo, mobile_hi, brief_holds = _mobile_length_bounds(examples)
    mobile_note = (
        f"Observed lengths {mobile_lo}-{mobile_hi} chars; brief's 60-80 claim "
        f"{'holds' if brief_holds else 'does NOT hold'} against both examples."
        if mobile_lo is not None
        else "No MOBILE_DESC evidence in the examples at all."
    )

    return {
        "INVOICE_DESC": FormatSpec(
            field="INVOICE_DESC",
            confidence="high",
            rule=f"{invoice_len_rule.rule} {invoice_case_rule.rule}",
            evidence=f"{invoice_len_rule.evidence} | {invoice_case_rule.evidence}",
            max_len=40,
            uppercase=True,
            compress_units=True,
        ),
        "MOBILE_DESC": FormatSpec(
            field="MOBILE_DESC",
            confidence="low",
            rule=mobile_rule.rule + f" ({mobile_note})",
            evidence=mobile_rule.evidence,
            min_len=mobile_lo,
            max_len=mobile_hi,
        ),
        "SHORT_DESC": FormatSpec(
            field="SHORT_DESC",
            confidence="medium",
            rule=short_rule.rule,
            evidence=short_rule.evidence,
        ),
        "LONG_DESC1": FormatSpec(
            field="LONG_DESC1",
            confidence="medium",
            rule=long_rule.rule,
            evidence=long_rule.evidence,
            ends_with_additional_info=True,
        ),
        "MARKETING_DESCRIPTION": FormatSpec(
            field="MARKETING_DESCRIPTION",
            confidence="low",
            rule=(
                "No construction pattern is derivable. n=1 (only 1 of 2 examples "
                "populates this field), and that example's content (specific "
                "features like '3rd Rack') isn't present in any input column or "
                "the attribute scaffold — it's external marketing copy. "
                "Generation is restricted to trusted attribute values only and "
                "will not reproduce real marketing prose."
            ),
            evidence="Row 0 MARKETING_DESCRIPTION is blank; row 1 is 214 chars of "
            "free prose referencing specs absent from ATTRIBUTE_VALUE 1-15.",
        ),
    }


# --------------------------------------------------------------------------
# Trusted-field extraction — the exclusion-filter principle from
# enrichment.py, applied here: only real values for THIS row are ever
# handed to the prompt.
# --------------------------------------------------------------------------

def trusted_fields_for_row(
    mfg_part_num: str, part_desc: str, expected: Optional[dict[str, str]] = None
) -> dict[str, str]:
    """The fields safe to pass into the description prompt for one row.

    `expected` is the worked-example row for this Mfg_Part_Num, if this is
    one of the 2 known rows — real ground truth for this specific row, not
    an inference. None for the other 8, which get nothing beyond the raw
    input columns: no manufacturer_normalizer output either, since
    'vendor code present, actual manufacturer unresolved' is precisely
    *not* a value a description should assert as fact.
    """
    fields: dict[str, str] = {"Mfg_Part_Num": mfg_part_num, "Part_Desc": part_desc}
    if expected is None:
        return fields

    for col in ("BRAND_NAME", "MANUFACTURER_NAME"):
        value = (expected.get(col) or "").strip()
        if value:
            fields[col] = value

    for attr in DISHWASHER_ATTRIBUTE_SCAFFOLD:
        value = (expected.get(f"ATTRIBUTE_VALUE {attr.index}") or "").strip()
        if value:
            fields[attr.label] = value

    return fields


# --------------------------------------------------------------------------
# Prompting.
# --------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a product-data copywriter for a home-appliance catalog.

You are given a set of VERIFIED fields for one dishwasher, and a construction
rule for each of 5 description formats. Every field you are given is real,
confirmed data for THIS product. You have no other information about this
product — no specs, materials, or features beyond what is listed.

Hard rules, no exceptions:
- Never state a number, material, feature, or spec that is not present in the
  VERIFIED FIELDS you were given. If a format's rule wants something you were
  not given (e.g. a Series name, when none was supplied), leave that part out
  rather than inventing a plausible-sounding value.
- If very few fields were supplied, the resulting descriptions should be
  short and generic. That is correct, not a failure to fix by padding.
- INVOICE_DESC only: return it in the shape described (all-caps, compressed).
  Every other format: normal mixed-case prose.
- Respect each format's max_len / min_len when given — write to fit, don't
  rely on truncation.

Respond with ONLY a JSON object:
{"INVOICE_DESC": "...", "MOBILE_DESC": "...", "SHORT_DESC": "...", "LONG_DESC1": "...", "MARKETING_DESCRIPTION": "..."}
Use an empty string for any format you cannot honestly produce from the given fields."""


def _build_user_prompt(fields: dict[str, str], specs: dict[str, FormatSpec]) -> str:
    rules_text = "\n".join(
        f"- {name} (confidence: {spec.confidence}): {spec.rule}"
        + (f" [max {spec.max_len} chars]" if spec.max_len else "")
        + (f" [min {spec.min_len} chars]" if spec.min_len else "")
        for name, spec in specs.items()
    )
    return (
        f"VERIFIED FIELDS FOR THIS PRODUCT:\n{json.dumps(fields, ensure_ascii=False, indent=2)}\n\n"
        f"FORMAT RULES:\n{rules_text}"
    )


# --------------------------------------------------------------------------
# Post-processing: enforce the mechanical parts of each rule so the LLM's
# prose doesn't have to get formatting exactly right on its own.
# --------------------------------------------------------------------------

_UNITS_BY_LEN_DESC = sorted(UNIT_REGISTRY, key=len, reverse=True)
_COMPRESS_RE = re.compile(
    r"(\d)\s+(" + "|".join(re.escape(u) for u in _UNITS_BY_LEN_DESC) + r")(?![A-Za-z])"
)


def _compress_number_unit_spacing(value: str) -> str:
    """Inverse of uom_normalizer.add_unit_spacing — '120 V' -> '120V'.

    INVOICE_DESC confirms the opposite spacing convention from every other
    field (inferred_rules.uom.number_unit_spacing), so this stays local to
    invoice formatting rather than living in uom_normalizer, which owns the
    add-a-space direction used everywhere else.
    """
    return _COMPRESS_RE.sub(lambda m: m.group(1) + m.group(2), value)


def _postprocess(field_name: str, value: str, spec: FormatSpec) -> str:
    value = (value or "").strip()
    if not value:
        return value
    if spec.uppercase:
        value = value.upper()
    if spec.compress_units:
        value = _compress_number_unit_spacing(value)
    else:
        value = add_unit_spacing(value)
    if spec.max_len and len(value) > spec.max_len:
        value = value[: spec.max_len].rstrip()
    return value


# --------------------------------------------------------------------------
# Factual-consistency check — every number in the generated text must trace
# back to a number that was actually in the trusted fields sent to the
# prompt. Exposed standalone (used by generate_descriptions below) and also
# wired into pipeline.evaluation as a tier-3 check, see
# `find_invented_numbers_on_row` there.
# --------------------------------------------------------------------------

_NUMBER_TOKEN_RE = re.compile(r"\d+(?:-\d+/\d+)?(?:\.\d+)?")


def _numbers_in(text: str) -> set[str]:
    return set(_NUMBER_TOKEN_RE.findall(text or ""))


def find_invented_numbers(
    generated: dict[str, str], trusted_fields: dict[str, str]
) -> dict[str, list[str]]:
    """Numbers in each generated description not present in any trusted field.

    Returns {field_name: [invented_number, ...]} for fields with a
    violation; empty dict if everything traces back cleanly. Comparison is
    literal-token, not numeric-value, on purpose: a description writing
    "50" when the only trusted number is "50-1/4" is still asserting a
    dimension nobody gave it, even though 50 < 50.25.
    """
    allowed = set()
    for value in trusted_fields.values():
        allowed |= _numbers_in(value)

    violations: dict[str, list[str]] = {}
    for field_name in DESCRIPTION_FIELDS:
        text = generated.get(field_name, "")
        invented = sorted(_numbers_in(text) - allowed)
        if invented:
            violations[field_name] = invented
    return violations


def generate_descriptions(
    mfg_part_num: str,
    part_desc: str,
    expected: Optional[dict[str, str]] = None,
    llm: Optional[LLMClient] = None,
    specs: Optional[dict[str, FormatSpec]] = None,
) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Generate the 5 description fields for one dishwasher row.

    Returns (descriptions, invented_number_violations). The violations dict
    is the same shape as find_invented_numbers() — check it before trusting
    the output; this function does not silently drop or fix a violation, it
    surfaces it for the caller (evaluate_row's tier-3 check does the same
    thing independently on the assembled output row).
    """
    llm = llm or LLMClient()
    specs = specs or build_format_specs()
    trusted = trusted_fields_for_row(mfg_part_num, part_desc, expected)

    response = llm.complete_json(SYSTEM_PROMPT, _build_user_prompt(trusted, specs))

    descriptions = {
        field_name: _postprocess(field_name, response.get(field_name, ""), specs[field_name])
        for field_name in DESCRIPTION_FIELDS
    }
    violations = find_invented_numbers(descriptions, trusted)
    return descriptions, violations
