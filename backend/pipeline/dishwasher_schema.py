"""
Step 5: dishwasher category schema.

SCOPE, AND WHY IT'S NARROW ON PURPOSE.

The step 5 pre-check searched all 1000 input rows for Faucets and Fittings
(the categories the original brief pointed at) and found zero real rows for
either. What the data actually contains, in the appliance family the 2 known
ground-truth rows (PDSH4816AF, WDTS7024RZ) belong to, is a MIXED bag of 41
rows: 10 dishwashers, 10 ranges, 8 washers, 8 microwaves, 3 freezers, 2
cooktops. Both known rows are dishwashers, so dishwasher is the only
sub-type where the ATTRIBUTE_LABEL scaffold (inferred_rules.
attributes.label_scaffold_is_category_template) has any ground-truth
evidence behind it at all. The other 5 sub-types are real rows with zero
scaffold evidence — see the NOT_BUILT entries in inferred_rules.py. Do not
extend DISHWASHER_ATTRIBUTE_SCAFFOLD to them from Part_Desc text guessing;
that is exactly the kind of fabrication this project keeps refusing to do.

WHAT THIS MODULE DOES vs DOES NOT DO.

It defines the confirmed 15-slot label scaffold (order, names, and the 4
UOM abbreviations that were identical across both known rows), and a
function that lays a dict of {label: value} onto ATTRIBUTE_LABEL/VALUE/UOM
1-15 in the correct order. It is self-tested by reconstructing both known
rows' attribute slots byte-for-byte from their own label->value pairs.

It does NOT supply attribute VALUES for the other 8 dishwasher rows
(KDFM404KPS, PDT715SYVFS, LDPH5554D, PDD415PYYFS, KDTS424SBE, KDTS324SPS,
KDPS624SJP, KDTS624SBE). Their Series/Voltage/Amperage/Size/etc. are not
present anywhere in the 6-column input — sourcing them requires the same
kind of external product lookup that manufacturer_normalizer.py refused to
fake for MANUFACTURER_NAME/BRAND_NAME. What generalizes to those 8 rows
from this module is structural only: the label scaffold itself, populated
with blank values, per inferred_rules.attributes.labels_kept_when_value_
unknown ("a label stays populated even when its value is unknown").
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

_BARE_NUMERIC_RE = re.compile(r"^\d+(-\d+/\d+)?(\.\d+)?$")


@dataclass(frozen=True)
class DishwasherAttribute:
    """One confirmed slot in the dishwasher ATTRIBUTE_LABEL 1-15 scaffold."""

    index: int
    label: str
    # The UOM abbreviation, ONLY when it was identical across both known
    # rows whenever the value was populated. None means either no UOM
    # applies (free text, or a bare count that isn't a unit of measurement)
    # or the two rows disagreed on format — see `evidence`.
    typical_uom: Optional[str]
    evidence: str


# Read directly off both worked example rows (see
# backend/scripts/step5_dishwasher_schema.py section 1 for the raw dump).
# Order is the confirmed scaffold order — do not reorder.
DISHWASHER_ATTRIBUTE_SCAFFOLD: tuple[DishwasherAttribute, ...] = (
    DishwasherAttribute(1, "Series", None,
                         "Row0='Professional Series', Row1='Eco Series' — free text, no unit."),
    DishwasherAttribute(2, "Model", None,
                         "Blank in both rows — label present, value never observed."),
    DishwasherAttribute(3, "Number of Wash Cycles", None,
                         "Row0='5', Row1='' — a bare count, not a unit of measurement "
                         "(see uom_normalizer.is_compound_dimension note on 'Number of Wash Cycles')."),
    DishwasherAttribute(4, "Voltage Rating", "V",
                         "'120' + UOM 'V' in both rows."),
    DishwasherAttribute(5, "Amperage Rating", "A",
                         "'15' (row0) / '10' (row1) + UOM 'A' in both rows."),
    DishwasherAttribute(6, "Mounting Type", None,
                         "Row0='Leg', Row1='Built-in' — free text, no unit."),
    DishwasherAttribute(7, "Plug Type", None,
                         "Blank in both rows — label present, value never observed."),
    DishwasherAttribute(8, "Size", None,
                         "Compound dimension string in both rows ('24 in W x 24-1/4 in D' / "
                         "'33-7/16 in H x 23-7/8 in W x 22-5/8 in D') — UOM stays blank per "
                         "inferred_rules.uom.compound_dimension_uom_blank."),
    DishwasherAttribute(9, "Depth With Door Open", "in",
                         "'50-1/4' (row0) / '50-3/16' (row1) + UOM 'in' in both rows."),
    DishwasherAttribute(10, "Minimum Height", "in",
                         "Row0 is a compound multi-value string (UOM correctly blank per the "
                         "compound rule); row1 is bare '33-7/16' + UOM 'in' — the one bare-"
                         "numeric occurrence of this label carries 'in', consistent with every "
                         "other height/depth measurement in the scaffold."),
    DishwasherAttribute(11, "Maximum Height", None,
                         "Row0 is a compound multi-value string (UOM blank); row1 leaves it "
                         "entirely blank. n=1 for the populated case."),
    DishwasherAttribute(12, "Sound Level", "dBA",
                         "'47' (row0) / '41' (row1) + UOM 'dBA' in both rows."),
    DishwasherAttribute(13, "Material", None,
                         "'Stainless Steel' in both rows — only value observed so far, not a "
                         "confirmed constrained vocabulary."),
    DishwasherAttribute(14, "Color", None,
                         "Row0 blank, row1='Stainless Steel' — free text, no unit."),
    DishwasherAttribute(15, "Additional Information", None,
                         "Free text; terminates LONG_DESC1 per inferred_rules."
                         "long_desc.assembly_order."),
)

DISHWASHER_ATTRIBUTE_LABELS: tuple[str, ...] = tuple(a.label for a in DISHWASHER_ATTRIBUTE_SCAFFOLD)
_LABEL_TO_ATTRIBUTE: dict[str, DishwasherAttribute] = {a.label: a for a in DISHWASHER_ATTRIBUTE_SCAFFOLD}

MAX_SLOT = 50  # delivery format reserves slots 1-50; dishwashers confirmed to use only 1-15.


def is_dishwasher(part_desc: str) -> bool:
    """Keyword match used ONLY to scope checks — not a classifier, not a claim of precision."""
    return bool(re.search(r"\bdishwasher\b", part_desc or "", re.IGNORECASE))


def _is_bare_numeric(value: str) -> bool:
    return bool(_BARE_NUMERIC_RE.match(value.strip()))


def build_dishwasher_attribute_slots(values: dict[str, str]) -> dict[str, str]:
    """Lay {label: value} onto ATTRIBUTE_LABEL/VALUE/UOM 1..15 in scaffold order.

    `values` keys must be a subset of DISHWASHER_ATTRIBUTE_LABELS; unknown
    keys are a caller bug and raise. Missing labels are treated as blank —
    per attributes.labels_kept_when_value_unknown the label is still
    emitted, just with an empty value.

    UOM is populated only for the 4 labels with a `typical_uom` AND only
    when the supplied value is bare numeric — a compound value (e.g. a
    multi-dimension Size or Minimum Height string) leaves UOM blank, same
    rule as uom_normalizer.is_compound_dimension enforces elsewhere. This
    function does not decide "is this compound" beyond the bare-numeric
    check; it trusts the caller to pass the value in the same string form
    the delivery format expects.

    Returns only the 45 ATTRIBUTE_* keys for slots 1-15 (LABEL/VALUE/UOM
    each) — merge into a fmt.empty_row() dict, don't use this as a
    complete row on its own.
    """
    unknown_keys = set(values) - set(DISHWASHER_ATTRIBUTE_LABELS)
    if unknown_keys:
        raise ValueError(
            f"build_dishwasher_attribute_slots got label(s) outside the confirmed "
            f"15-slot dishwasher scaffold: {sorted(unknown_keys)}"
        )

    out: dict[str, str] = {}
    for attr in DISHWASHER_ATTRIBUTE_SCAFFOLD:
        label_col = f"ATTRIBUTE_LABEL {attr.index}"
        value_col = f"ATTRIBUTE_VALUE {attr.index}"
        uom_col = f"ATTRIBUTE_UOM {attr.index}"

        value = values.get(attr.label, "")
        out[label_col] = attr.label
        out[value_col] = value
        if attr.typical_uom and value and _is_bare_numeric(value):
            out[uom_col] = attr.typical_uom
        else:
            out[uom_col] = ""
    return out


def blank_dishwasher_scaffold() -> dict[str, str]:
    """The scaffold with every value left blank — the honest default for a
    dishwasher row whose attribute values were never sourced (the other 8
    unverified dishwasher rows fall here; see module docstring)."""
    return build_dishwasher_attribute_slots({})
