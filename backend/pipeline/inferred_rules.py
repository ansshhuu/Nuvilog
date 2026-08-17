"""
Step 1: pattern rules read off the worked examples.

READ THIS BEFORE TRUSTING ANYTHING IN THIS FILE.

Every rule below is INFERRED from exactly 2 worked example rows in
`Unihack_ Expected Output - Delivery Format.csv`. There is no official spec
on disk: no content-guidelines document, no UOM master, no fraction table,
no manufacturer/brand master list, no LOV files. Those were described in the
brief but never distributed as files.

Two rows is not a sample. A pattern that holds in both rows is a hypothesis
with n=2; a pattern seen in one row is barely that. Each rule therefore
carries an explicit `confidence` and the `evidence` it was read from, and
nothing here should be presented to a judge as a confirmed specification.

The measurable claims (character limits, casing, separators) are re-checked
against the examples at runtime by `verify_rules()` — see
`backend/scripts/step1_data_prep.py`. Rules that cannot be machine-checked
from 2 rows are marked `checkable=False` and stay honest guesses.

NOT BUILT — and deliberately so:
  Manufacturer/brand fuzzy matching against a master list. There is no master
  list to match against, so a matcher would be a no-op wearing a costume.
  See NOT_BUILT at the bottom of this module.

STEP 4 UPDATE: the investigation into whether MANUFACTURER_NAME/BRAND_NAME
are recoverable from the input row is now closed — they are not. See
`manufacturer.not_derivable_from_part_manuf` below and
`pipeline/manufacturer_normalizer.py`, which builds the honest
canonicalization step (vendor-name clustering + a per-row "unresolved"
confidence flag) instead of a fake transformation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Literal, Optional

from pipeline.dishwasher_schema import DISHWASHER_ATTRIBUTE_LABELS, is_dishwasher
from pipeline.uom_normalizer import (
    SPACING_RULE_EXEMPT_FIELDS,
    has_correct_number_unit_spacing,
    is_compound_dimension,
)

Confidence = Literal["low", "medium", "high"]

INFERENCE_BASIS = (
    "Inferred from 2 worked example rows. Not verified against an official spec — "
    "no spec, LOV, UOM or brand master file exists on disk."
)


@dataclass(frozen=True)
class InferredRule:
    """One pattern read off the worked examples."""

    id: str
    field: str
    rule: str
    evidence: str
    confidence: Confidence
    # Machine-checkable rules carry a predicate run over the example rows.
    check: Optional[Callable[[list[dict[str, str]]], bool]] = None
    note: str = ""

    @property
    def checkable(self) -> bool:
        return self.check is not None

    @property
    def basis(self) -> str:
        return INFERENCE_BASIS


# --------------------------------------------------------------------------
# Check predicates. Each runs over the list of worked example rows.
# --------------------------------------------------------------------------

def _nonempty(rows: list[dict[str, str]], field: str) -> list[str]:
    return [r[field] for r in rows if r.get(field, "").strip()]


def _check_invoice_len(rows: list[dict[str, str]]) -> bool:
    return all(len(v) <= 40 for v in _nonempty(rows, "INVOICE_DESC"))


def _check_invoice_upper(rows: list[dict[str, str]]) -> bool:
    values = _nonempty(rows, "INVOICE_DESC")
    return bool(values) and all(v == v.upper() for v in values)


def _check_other_descs_not_upper(rows: list[dict[str, str]]) -> bool:
    fields = ("MOBILE_DESC", "SHORT_DESC", "LONG_DESC1", "RETAIL_DESC")
    return all(v != v.upper() for f in fields for v in _nonempty(rows, f))


def _check_classpath_separator(rows: list[dict[str, str]]) -> bool:
    values = _nonempty(rows, "Classpath")
    return bool(values) and all(
        ">" in v and " > " not in v and len(v.split(">")) == 3 for v in values
    )


def _check_uom_only_for_bare_numbers(rows: list[dict[str, str]]) -> bool:
    """Where ATTRIBUTE_UOM is filled, the paired VALUE is a bare number."""
    bare = re.compile(r"^\d+(-\d+/\d+)?(\.\d+)?$")
    for row in rows:
        for i in range(1, 51):
            uom = row.get(f"ATTRIBUTE_UOM {i}", "").strip()
            value = row.get(f"ATTRIBUTE_VALUE {i}", "").strip()
            if uom and not bare.match(value):
                return False
    return True


def _check_label_scaffold_identical(rows: list[dict[str, str]]) -> bool:
    """Both examples are dishwashers and both emit the same label sequence."""
    sequences = [
        tuple(row.get(f"ATTRIBUTE_LABEL {i}", "").strip() for i in range(1, 51))
        for row in rows
    ]
    return len(set(sequences)) == 1


def _check_labels_without_values(rows: list[dict[str, str]]) -> bool:
    """At least one label is emitted with an empty value — the scaffold stays."""
    for row in rows:
        for i in range(1, 51):
            if row.get(f"ATTRIBUTE_LABEL {i}", "").strip() and not row.get(
                f"ATTRIBUTE_VALUE {i}", ""
            ).strip():
                return True
    return False


def _check_no_gaps_in_attribute_slots(rows: list[dict[str, str]]) -> bool:
    """Filled label slots are contiguous from 1 — no holes then a late slot."""
    for row in rows:
        filled = [
            i for i in range(1, 51) if row.get(f"ATTRIBUTE_LABEL {i}", "").strip()
        ]
        if filled and filled != list(range(1, len(filled) + 1)):
            return False
    return True


def _check_fraction_style(rows: list[dict[str, str]]) -> bool:
    """Fractions are ASCII `whole-num/den`, never unicode vulgar fractions."""
    unicode_fractions = re.compile(r"[¼-¾⅐-⅞]")
    ascii_fraction = re.compile(r"\d+-\d+/\d+")
    joined = " ".join(v for row in rows for v in row.values())
    return bool(ascii_fraction.search(joined)) and not unicode_fractions.search(joined)


def _check_passthrough_placeholders_preserved(rows: list[dict[str, str]]) -> bool:
    """The sentinel brand strings survive verbatim into the output row."""
    return all(
        row.get("E1_Brand", "").strip() == "-- Unbranded --"
        and row.get("Unilog_Brand", "").strip() == "-- No Unilog Brand --"
        and row.get("DIB_Brand", "").strip() == "-- No DIB Brand --"
        for row in rows
    )


def _check_brand_has_symbol(rows: list[dict[str, str]]) -> bool:
    return all("®" in v or "™" in v for v in _nonempty(rows, "BRAND_NAME"))


def _check_approvals_pipe_delimited(rows: list[dict[str, str]]) -> bool:
    values = _nonempty(rows, "Standard/Approvals")
    if not values:
        return False
    for v in values:
        parts = [p.strip() for p in v.split("|")]
        if len(parts) < 2 or parts != sorted(parts, key=str.lower):
            return False
    return True


def _check_asset_filename_pattern(rows: list[dict[str, str]]) -> bool:
    """Assets are `<BrandToken>_<MPN>[_suffix].<ext>` with no ® in the token."""
    for row in rows:
        mpn = row.get("MANUFACTURER_PART_NUMBER", "").strip()
        image = row.get("Product Image", "").strip()
        if not (mpn and image):
            continue
        if not image.endswith(".jpg") or f"_{mpn}." not in image:
            return False
        if "®" in image:
            return False
    return True


def _check_long_desc_additional_info_suffix(rows: list[dict[str, str]]) -> bool:
    """LONG_DESC1 ends with the Additional Information attribute, verbatim."""
    for row in rows:
        long_desc = row.get("LONG_DESC1", "").strip()
        extra = row.get("ATTRIBUTE_VALUE 15", "").strip()
        if not (long_desc and extra):
            continue
        if not long_desc.endswith(f"Additional Information: {extra}"):
            return False
    return True


def _check_short_desc_starts_with_brand(rows: list[dict[str, str]]) -> bool:
    for row in rows:
        brand = row.get("BRAND_NAME", "").strip()
        short = row.get("SHORT_DESC", "").strip()
        if brand and short and not short.startswith(brand):
            return False
    return True


def _check_number_unit_spacing(rows: list[dict[str, str]]) -> bool:
    for row in rows:
        for field_name, value in row.items():
            if field_name in SPACING_RULE_EXEMPT_FIELDS or not value:
                continue
            if not has_correct_number_unit_spacing(value):
                return False
    return True


def _check_dishwasher_scaffold_matches_known_rows(rows: list[dict[str, str]]) -> bool:
    """Both known rows are dishwashers; their ATTRIBUTE_LABEL 1-15 must equal
    DISHWASHER_ATTRIBUTE_SCAFFOLD exactly, in order, with nothing beyond slot 15."""
    dishwasher_rows = [r for r in rows if is_dishwasher(r.get("Part_Desc", ""))]
    if not dishwasher_rows:
        return False
    for row in dishwasher_rows:
        actual = tuple(row.get(f"ATTRIBUTE_LABEL {i}", "").strip() for i in range(1, 16))
        if actual != DISHWASHER_ATTRIBUTE_LABELS:
            return False
        if any(row.get(f"ATTRIBUTE_LABEL {i}", "").strip() for i in range(16, 51)):
            return False
    return True


def _check_manufacturer_not_derivable_from_part_manuf(rows: list[dict[str, str]]) -> bool:
    """Same Part_Manuf, different MANUFACTURER_NAME -> no function Part_Manuf -> MANUFACTURER_NAME exists.

    This check only proves what it can from n=2: if the 2 known rows ever
    stop sharing a Part_Manuf value, this predicate can't say anything and
    should be re-derived rather than trusted blindly.
    """
    manuf_values = {row.get("Part_Manuf", "").strip() for row in rows}
    mfr_names = {row.get("MANUFACTURER_NAME", "").strip() for row in rows}
    if len(manuf_values) != 1:
        return False
    return len(mfr_names) > 1


def _check_compound_dimension_uom_blank(rows: list[dict[str, str]]) -> bool:
    for row in rows:
        for i in range(1, 51):
            value = row.get(f"ATTRIBUTE_VALUE {i}", "").strip()
            uom = row.get(f"ATTRIBUTE_UOM {i}", "").strip()
            if value and is_compound_dimension(value) and uom:
                return False
    return True


# --------------------------------------------------------------------------
# The rules.
# --------------------------------------------------------------------------

RULES: tuple[InferredRule, ...] = (
    InferredRule(
        id="invoice_desc.max_len_40",
        field="INVOICE_DESC",
        rule="INVOICE_DESC is at most 40 characters.",
        evidence="Example lengths: 38 and 39 — both just under 40, consistent with the brief's stated limit.",
        confidence="high",
        check=_check_invoice_len,
        note="The only rule here that the brief also states in text; the examples corroborate it.",
    ),
    InferredRule(
        id="invoice_desc.uppercase",
        field="INVOICE_DESC",
        rule="INVOICE_DESC is fully uppercase and uses compressed abbreviations (SST, BLTLN, DBA, IN).",
        evidence="'DISHWASHER LEG 5 SST 120V 15A 50-1/4IN' / 'DISHWASHER BLTLN SST SST 120V 10A 41DBA'.",
        confidence="high",
        check=_check_invoice_upper,
        note="The abbreviation vocabulary itself is NOT derivable — SST/BLTLN come from a table we do not have.",
    ),
    InferredRule(
        id="descriptions.title_case",
        field="MOBILE_DESC / SHORT_DESC / LONG_DESC1 / RETAIL_DESC",
        rule="All non-invoice descriptions are mixed case, not uppercase.",
        evidence="Every other description field in both examples contains lowercase characters.",
        confidence="medium",
        check=_check_other_descs_not_upper,
    ),
    InferredRule(
        id="classpath.gt_separator",
        field="Classpath",
        rule="Classpath is 3 levels joined by '>' with no surrounding spaces.",
        evidence="'Appliances & Consumer Electronics>Kitchen Appliances>Built-In Dishwashers' in both rows.",
        confidence="medium",
        check=_check_classpath_separator,
        note="Depth of 3 is n=2 evidence from a single category; other categories may be deeper or shallower.",
    ),
    InferredRule(
        id="classpath.differs_from_dept_class_fine",
        field="Classpath vs Dept/Class/Fine",
        rule="Classpath is a separate vocabulary from the Dept/Class/Fine hierarchy — not a join of those three.",
        evidence="Dept/Class/Fine = 'Appliances / Large Appliances / Dishwashers' but Classpath = 'Appliances & Consumer Electronics>Kitchen Appliances>Built-In Dishwashers'.",
        confidence="high",
        note="Important: do not generate Classpath by concatenating Dept>Class>Fine. The mapping between them is not recoverable from 2 rows.",
    ),
    InferredRule(
        id="attributes.label_scaffold_is_category_template",
        field="ATTRIBUTE_LABEL 1..50",
        rule="Attribute labels are a fixed per-category template emitted in a fixed order, independent of the item.",
        evidence="Both examples emit exactly the same 15 labels in the same order (Series, Model, Number of Wash Cycles, ... Additional Information).",
        confidence="medium",
        check=_check_label_scaffold_identical,
        note="Both examples are dishwashers, so this shows the template is stable *within* a category. It says nothing about how templates differ *across* categories — that is exactly what the missing LOV file would have told us.",
    ),
    InferredRule(
        id="attributes.labels_kept_when_value_unknown",
        field="ATTRIBUTE_LABEL / ATTRIBUTE_VALUE",
        rule="A label stays populated even when its value is unknown; the VALUE cell is left blank rather than the slot being dropped.",
        evidence="Both rows emit 'Model', 'Plug Type', 'Color' labels with empty values; row 1 emits 'Maximum Height' with no value.",
        confidence="medium",
        check=_check_labels_without_values,
    ),
    InferredRule(
        id="attributes.slots_contiguous",
        field="ATTRIBUTE_LABEL 1..50",
        rule="Filled slots run contiguously from slot 1; unused slots are all trailing.",
        evidence="Both rows fill slots 1-15 and leave 16-50 entirely blank.",
        confidence="medium",
        check=_check_no_gaps_in_attribute_slots,
    ),
    InferredRule(
        id="attributes.uom_only_for_bare_numeric_values",
        field="ATTRIBUTE_UOM 1..50",
        rule="ATTRIBUTE_UOM is populated only when the paired VALUE is a bare number; composite values keep their units inline and leave UOM blank.",
        evidence="'Depth With Door Open' = '50-1/4' + UOM 'in', but 'Size' = '24 in W x 24-1/4 in D' with UOM blank; 'Minimum Height' = '8-1/2 in Upper Rack, 11-1/4 in Lower Rack' with UOM blank.",
        confidence="medium",
        check=_check_uom_only_for_bare_numbers,
        note="The permitted UOM vocabulary (in, V, A, dBA) is NOT derivable — the UOM master file does not exist. Observed values only.",
    ),
    InferredRule(
        id="formatting.ascii_fractions",
        field="all",
        rule="Fractional measurements are written ASCII as 'whole-numerator/denominator' (50-1/4, 33-7/16, 8-1/2); no unicode vulgar fractions.",
        evidence="Every fraction in both rows uses this form; no ¼/½/¾ characters appear anywhere.",
        confidence="medium",
        check=_check_fraction_style,
        note="Denominators observed: 2, 4, 8, 16. The brief's fraction-conversion table is not on disk, so rounding/precision rules are unknown.",
    ),
    InferredRule(
        id="brand.registered_symbol_retained",
        field="BRAND_NAME",
        rule="BRAND_NAME carries the ® symbol.",
        evidence="'FRIGIDAIRE®' and 'Whirlpool®'.",
        confidence="medium",
        check=_check_brand_has_symbol,
        note="Casing is inconsistent across the two examples (all-caps vs title case), so brand casing is NOT inferable.",
    ),
    InferredRule(
        id="passthrough.placeholders_preserved",
        field="E1_Brand / Unilog_Brand / DIB_Brand",
        rule="The input sentinel strings are echoed to the output verbatim — they are cleaned for reasoning, never for delivery.",
        evidence="Both output rows carry '-- Unbranded --', '-- No Unilog Brand --', '-- No DIB Brand --' unchanged.",
        confidence="high",
        check=_check_passthrough_placeholders_preserved,
    ),
    InferredRule(
        id="approvals.pipe_delimited_sorted",
        field="Standard/Approvals",
        rule="Multiple approvals are pipe-delimited with no spaces around the pipe, in alphabetical order.",
        evidence="'ASSE 1006|CEE Tier 2 Qualified|cUL Listed|ENERGY STAR Certified|NSF Certified|UL Listed' (row 0). Row 1 is empty.",
        confidence="low",
        check=_check_approvals_pipe_delimited,
        note="n=1 — only one example row populates this field.",
    ),
    InferredRule(
        id="long_desc.assembly_order",
        field="LONG_DESC1",
        rule="LONG_DESC1 = BRAND + Product Name + 'With' clause + Series, then attribute values in template order, ending with 'Additional Information: <ATTRIBUTE_VALUE 15>'.",
        evidence="Row 0 and row 1 both terminate with the verbatim ATTRIBUTE_VALUE 15 text after the literal prefix 'Additional Information: '.",
        confidence="medium",
        check=_check_long_desc_additional_info_suffix,
        note="The mid-string ordering is eyeballed from 2 rows and the two rows do not agree on where the 'With' clause sits — row 0 puts it before Series, row 1 omits it entirely.",
    ),
    InferredRule(
        id="short_desc.brand_first",
        field="SHORT_DESC",
        rule="SHORT_DESC opens with BRAND_NAME, then Series, then MPN, then Product Name, then differentiating attributes.",
        evidence="'FRIGIDAIRE® Professional Series PDSH4816AF Dishwasher ...' / 'Whirlpool® Eco Series WDTS7024RZ Dishwasher, ...'.",
        confidence="medium",
        check=_check_short_desc_starts_with_brand,
        note="Delimiters differ between the rows (row 0 is space-separated, row 1 uses commas), so punctuation is not inferable.",
    ),
    InferredRule(
        id="retail_desc.no_brand",
        field="RETAIL_DESC",
        rule="RETAIL_DESC omits the brand and opens with Series + Product Name, comma-separated.",
        evidence="'Professional Series Dishwasher, Leg Mounting, 5-Wash Cycle, Stainless Steel' / 'Eco Series Dishwasher, Built-in Mounting, Stainless Steel, Stainless Steel'.",
        confidence="medium",
        note="Row 1 repeats 'Stainless Steel' (Material and Color both), suggesting no dedupe step.",
    ),
    InferredRule(
        id="mobile_desc.comma_list",
        field="MOBILE_DESC",
        rule="MOBILE_DESC is a short comma-separated list: brand, Product Name, Series, MPN, and optionally mounting.",
        evidence="'Rheem Manufacturing FRIGIDAIRE, Dishwasher, Professional Series, PDSH4816AF' / 'Whirlpool, Dishwasher, Eco Series, WDTS7024RZ, Built-in Mounting'.",
        confidence="low",
        note="The two rows disagree: row 0 leads with MANUFACTURER_NAME + brand and has no ®; row 1 leads with brand alone. Lengths 75 and 64 give no usable limit.",
    ),
    InferredRule(
        id="assets.filename_convention",
        field="Product Image / Alternate Image N / Specification Sheet",
        rule="Asset filenames are '<BrandToken>_<MANUFACTURER_PART_NUMBER>[_suffix].<ext>', brand token stripped of ®.",
        evidence="'FRIGIDAIRE_PDSH4816AF.jpg', 'FRIGIDAIRE_PDSH4816AF_1.jpg', 'Whirlpool_WDTS7024RZ_Specification_Sheet.pdf'.",
        confidence="medium",
        check=_check_asset_filename_pattern,
        note="These are filenames, not URLs — the assets themselves are not shipped. How a brand token with spaces is written is unknown.",
    ),
    InferredRule(
        id="item_features.marketing_only",
        field="ITEM_FEATURES_1..20",
        rule="ITEM_FEATURES are short marketing bullets, populated only when MARKETING_DESCRIPTION is also populated.",
        evidence="Row 1 has 11 features and a MARKETING_DESCRIPTION; row 0 has neither.",
        confidence="low",
        note="n=1 for the populated case. The correlation may be coincidence — both simply reflect whether marketing copy was found on the manufacturer site.",
    ),
    InferredRule(
        id="metadata.actual_image_flag",
        field="Actual Image (Yes/No)",
        rule="'Yes' when a real product image was sourced.",
        evidence="Both rows are 'Yes' and both have a Product Image.",
        confidence="low",
        note="No negative example exists, so the 'No' case is pure assumption.",
    ),
    InferredRule(
        id="coverage.blank_blocks_have_no_evidence",
        field="physical / commerce / metadata groups",
        rule="LENGTH..VOLUME, UPC/EAN/GTIN, UNSPSC, List Price, Selling Qty/UOM, Country Of Origin and Discontinued are blank in BOTH examples.",
        evidence="Direct observation — those 30+ columns are empty in the delivery file.",
        confidence="high",
        note="This means we have ZERO formatting evidence for a third of the delivery format. Do not invent conventions for these fields and present them as matched to the target.",
    ),
    InferredRule(
        id="uom.number_unit_spacing",
        field="all fields except INVOICE_DESC",
        rule="A number and its unit abbreviation are always separated by a space "
             "('24 in', not '24in'), everywhere except INVOICE_DESC.",
        evidence="'120 V', '15 A', '24 in', '24-1/4 in', '47 dBA', '10-3/8 in' all appear "
                 "with a space in LONG_DESC1/ATTRIBUTE_VALUE across both rows; zero "
                 "no-space occurrences found outside INVOICE_DESC.",
        confidence="high",
        check=_check_number_unit_spacing,
        note="This is pure math/typography, not a fabricated rule — this is a strictly "
             "different (and more confident) claim than the UOM abbreviation choices "
             "themselves, see uom_normalizer.UNIT_REGISTRY confirmed/inferred split. "
             "INVOICE_DESC is excluded because it confirms the OPPOSITE convention "
             "(see invoice_desc.uppercase) — '120V', '15A', '50-1/4IN' have no spaces there.",
    ),
    InferredRule(
        id="uom.compound_dimension_uom_blank",
        field="ATTRIBUTE_UOM 1..50",
        rule="When ATTRIBUTE_VALUE is a compound dimension string (multiple numbers/units, "
             "an 'x' connector, or axis letters like W/D/H), ATTRIBUTE_UOM stays blank — "
             "the unit(s) stay inline in the value instead of being pulled into the UOM column.",
        evidence="'Size' = '24 in W x 24-1/4 in D' with UOM blank; 'Minimum Height' = "
                 "'8-1/2 in Upper Rack, 11-1/4 in Lower Rack' with UOM blank, in both rows.",
        confidence="high",
        check=_check_compound_dimension_uom_blank,
        note="Deliberately one-directional. The converse ('bare numeric implies UOM is "
             "filled') does NOT hold in the ground truth — row 0's 'Number of Wash Cycles' "
             "= '5' with UOM blank, because a count isn't a unit of measurement. Asserting "
             "the converse would fail against the very examples it's meant to match.",
    ),
    InferredRule(
        id="attributes.dishwasher_scaffold_15_labels",
        field="ATTRIBUTE_LABEL 1..15",
        rule="For dishwashers specifically, ATTRIBUTE_LABEL 1-15 is the fixed sequence "
             "Series, Model, Number of Wash Cycles, Voltage Rating, Amperage Rating, "
             "Mounting Type, Plug Type, Size, Depth With Door Open, Minimum Height, "
             "Maximum Height, Sound Level, Material, Color, Additional Information — "
             "nothing beyond slot 15 is used.",
        evidence="Byte-identical label sequence in both known rows (PDSH4816AF, WDTS7024RZ), "
                 "both dishwashers; slots 16-50 blank in both.",
        confidence="high",
        check=_check_dishwasher_scaffold_matches_known_rows,
        note="Scoped to dishwashers ONLY — see pipeline/dishwasher_schema.py for the full "
             "scaffold with per-label UOM evidence, and the NOT_BUILT entries below for the "
             "5 other appliance sub-types found in the data (range, washer, microwave, "
             "freezer, cooktop) that have real rows but zero scaffold evidence. This rule "
             "supersedes the more general attributes.label_scaffold_is_category_template for "
             "dishwashers specifically; that rule's n=2-both-dishwashers caveat is exactly "
             "why this one doesn't get generalized further.",
    ),
    InferredRule(
        id="manufacturer.not_derivable_from_part_manuf",
        field="MANUFACTURER_NAME / BRAND_NAME",
        rule="MANUFACTURER_NAME and BRAND_NAME cannot be derived from Part_Manuf, or from any "
             "other input column — both known rows share the identical Part_Manuf value yet "
             "resolve to two different manufacturers and brands.",
        evidence="Both rows: Part_Manuf='Appliance Dealers Cooperative (APPDE)'. Row 0: "
                 "MANUFACTURER_NAME='Rheem Manufacturing', BRAND_NAME='FRIGIDAIRE®'. "
                 "Row 1: MANUFACTURER_NAME='Whirlpool Corporation', BRAND_NAME='Whirlpool®'. "
                 "E1_Brand/Unilog_Brand/DIB_Brand are sentinel-empty in both rows too.",
        confidence="high",
        check=_check_manufacturer_not_derivable_from_part_manuf,
        note="This is the reason pipeline.manufacturer_normalizer never emits a "
             "MANUFACTURER_NAME/BRAND_NAME value. It emits a per-row confidence flag "
             "('vendor code present, actual manufacturer unresolved') instead. Resolving "
             "these fields for the other 998 rows requires external product lookup — out "
             "of scope for in-row cleaning, and not something to fake.",
    ),
    InferredRule(
        id="data_quality.example_manufacturer_is_wrong",
        field="MANUFACTURER_NAME",
        rule="Row 0 lists MANUFACTURER_NAME 'Rheem Manufacturing' for a FRIGIDAIRE dishwasher — an error in the worked example itself.",
        evidence="Row 0: BRAND_NAME 'FRIGIDAIRE®', MFR URL frigidaire.com, MANUFACTURER_NAME 'Rheem Manufacturing'.",
        confidence="high",
        note="Flagged so we don't reverse-engineer a manufacturer-vs-brand rule out of what is most likely a copy-paste mistake. Row 1 is internally consistent (Whirlpool Corporation / Whirlpool®).",
    ),
)

RULES_BY_ID: dict[str, InferredRule] = {r.id: r for r in RULES}


# --------------------------------------------------------------------------
# Runtime verification of the checkable rules.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class RuleCheck:
    rule: InferredRule
    passed: Optional[bool]  # None = not machine-checkable

    @property
    def status(self) -> str:
        if self.passed is None:
            return "UNCHECKED"
        return "HOLDS" if self.passed else "VIOLATED"


def verify_rules(example_rows: list[dict[str, str]]) -> list[RuleCheck]:
    """Re-derive every checkable rule from the worked examples.

    'HOLDS' means the pattern is consistent with 2 rows. It does not mean the
    rule is correct.
    """
    checks = []
    for rule in RULES:
        if rule.check is None:
            checks.append(RuleCheck(rule=rule, passed=None))
        else:
            checks.append(RuleCheck(rule=rule, passed=bool(rule.check(example_rows))))
    return checks


# --------------------------------------------------------------------------
# Explicitly cancelled work.
# --------------------------------------------------------------------------

NOT_BUILT: tuple[tuple[str, str], ...] = (
    (
        "manufacturer/brand fuzzy matcher against a master list",
        "Still cancelled, and permanently so. Matching Part_Manuf or the brand columns "
        "against a manufacturer master list requires that master list; it does not "
        "exist on disk and the organizer confirmed it will not be distributed. Confirmed "
        "separately (see manufacturer.not_derivable_from_part_manuf above): even if Part_Manuf "
        "were matched against something, it wouldn't help — the 2 known rows share an "
        "identical Part_Manuf and still resolve to different manufacturers, so Part_Manuf "
        "is not a manufacturer signal at all, it's Unilog's own vendor/distributor field. "
        "What WAS built instead (pipeline/manufacturer_normalizer.py): the 'Name (CODE)' "
        "vendor-code parse (959/1000 rows), within-dataset clustering of the 76 distinct "
        "vendor names for spelling/punctuation consolidation (real result: 0 of 76 turn out "
        "to be duplicates of each other — each already carries a unique code), and a per-row "
        "'vendor code present, actual manufacturer unresolved' confidence flag. It never "
        "emits a MANUFACTURER_NAME or BRAND_NAME value.",
    ),
    (
        "range attribute scaffold",
        "10 real range rows exist in the 1000-row sample (e.g. 'PS960YPFS 30\" GE Electric "
        "Range SS - Display Only') but zero of them have a known-correct delivery-format "
        "answer. The confirmed dishwasher scaffold (attributes.dishwasher_scaffold_15_labels) "
        "does not transfer — 'Number of Wash Cycles' and 'Depth With Door Open' don't apply "
        "to a range. Guessing a range-specific label set from Part_Desc text alone would be "
        "exactly the kind of fabrication this project keeps refusing to do.",
    ),
    (
        "washer (laundry) attribute scaffold",
        "8 real rows (e.g. 'FF7011WN Speed Queen Washer Wh'), zero ground-truth answers. "
        "Same reasoning as range attribute scaffold above.",
    ),
    (
        "microwave attribute scaffold",
        "8 real rows (e.g. 'MSER2090S LG Microwave SS'), zero ground-truth answers. "
        "Same reasoning as range attribute scaffold above.",
    ),
    (
        "freezer attribute scaffold",
        "3 real rows (e.g. 'EUF17CDBW Element 17CF Freezer - Upright'), zero ground-truth "
        "answers. Same reasoning as range attribute scaffold above.",
    ),
    (
        "cooktop attribute scaffold",
        "2 real rows (e.g. 'PEP9030DTBB 30\" GE Cooktop Bk'), zero ground-truth answers. "
        "Same reasoning as range attribute scaffold above.",
    ),
    (
        "UOM normalization table",
        "No UOM master file exists. Only the UOMs observed in the 2 examples "
        "(in, V, A, dBA) are known to be valid; any wider vocabulary would be invented.",
    ),
    (
        "fraction conversion table",
        "No fraction table exists. The ASCII fraction style is observable "
        "(see formatting.ascii_fractions) but rounding and denominator rules are not.",
    ),
    (
        "attribute LOV / constrained vocabulary",
        "No LOV files exist. The attribute label template is observable for one "
        "category (dishwashers) from 2 rows; permitted values per label are not.",
    ),
)
