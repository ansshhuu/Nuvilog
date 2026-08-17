"""
Step 3: UOM abbreviation registry + spacing/compound-value rules.

Two different kinds of claims live in this module, and they get different
treatment on purpose:

  * Number-unit spacing ("24 in", not "24in") is CONFIRMED — both worked
    examples do it consistently everywhere except INVOICE_DESC, which is a
    separately-confirmed compressed all-caps format (see
    inferred_rules.invoice_desc.uppercase) and is deliberately excluded here.

  * The UOM *abbreviation choices themselves* are house style, and no UOM
    master file exists (see inferred_rules.NOT_BUILT). Only `in`, `V`, `A`,
    `dBA` were actually seen in the 2 examples — those are CONFIRMED.
    Everything else in UNIT_REGISTRY (mm, lb, kg, W, Hz, ...) is a
    reasonable engineering-standard guess, marked INFERRED so downstream
    code/UI can distinguish "this is what the delivery format actually
    wants" from "this is our best guess because nothing tells us otherwise."

Fraction handling itself (the math) lives in fraction_converter.py and needs
no confidence tier — this module only owns the unit-abbreviation and
formatting layer built on top of it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Optional

UnitConfidence = Literal["confirmed", "inferred"]


@dataclass(frozen=True)
class UnitDef:
    abbreviation: str
    confidence: UnitConfidence
    evidence: str
    aliases: tuple[str, ...] = ()


# Canonical abbreviation -> UnitDef. Order doesn't matter for lookup but is
# kept confirmed-first for readability.
UNIT_REGISTRY: dict[str, UnitDef] = {
    # --- CONFIRMED: seen verbatim in the 2 worked examples ---
    "in": UnitDef(
        "in", "confirmed",
        "ATTRIBUTE_UOM 9/10 (row 0) and 9 (row 1), plus inline in LONG_DESC1 and "
        "ATTRIBUTE_VALUE 8/9/10/11 in both rows.",
        aliases=("inch", "inches", '"'),
    ),
    "V": UnitDef(
        "V", "confirmed",
        "ATTRIBUTE_UOM 4 in both rows; inline in LONG_DESC1 ('120 V').",
        aliases=("volt", "volts", "v"),
    ),
    "A": UnitDef(
        "A", "confirmed",
        "ATTRIBUTE_UOM 5 in both rows; inline in LONG_DESC1 ('15 A', '10 A').",
        aliases=("amp", "amps", "ampere", "amperes"),
    ),
    "dBA": UnitDef(
        "dBA", "confirmed",
        "ATTRIBUTE_UOM 12 in both rows; inline in LONG_DESC1 and ITEM_FEATURES_3 ('41 dBA').",
        aliases=("dba",),
    ),
    # --- INFERRED: standard engineering abbreviation, NOT seen in either example ---
    "ft": UnitDef("ft", "inferred", "Standard abbreviation for feet; not present in either worked example.",
                  aliases=("foot", "feet")),
    "mm": UnitDef("mm", "inferred", "Standard abbreviation for millimeters; not present in either worked example.",
                  aliases=("millimeter", "millimeters", "millimetre")),
    "cm": UnitDef("cm", "inferred", "Standard abbreviation for centimeters; not present in either worked example.",
                  aliases=("centimeter", "centimeters")),
    "lb": UnitDef("lb", "inferred", "Standard abbreviation for pounds; not present in either worked example.",
                  aliases=("pound", "pounds", "lbs")),
    "oz": UnitDef("oz", "inferred", "Standard abbreviation for ounces; not present in either worked example.",
                  aliases=("ounce", "ounces")),
    "kg": UnitDef("kg", "inferred", "Standard abbreviation for kilograms; not present in either worked example.",
                  aliases=("kilogram", "kilograms")),
    "g": UnitDef("g", "inferred", "Standard abbreviation for grams; not present in either worked example.",
                 aliases=("gram", "grams")),
    "W": UnitDef("W", "inferred", "Standard abbreviation for watts; not present in either worked example.",
                 aliases=("watt", "watts")),
    "Hz": UnitDef("Hz", "inferred", "Standard abbreviation for hertz; not present in either worked example.",
                  aliases=("hz", "hertz")),
    "psi": UnitDef("psi", "inferred", "Standard abbreviation for pounds per square inch; not present in either worked example.",
                   aliases=()),
    "gal": UnitDef("gal", "inferred", "Standard abbreviation for gallons; not present in either worked example.",
                   aliases=("gallon", "gallons")),
    "qt": UnitDef("qt", "inferred", "Standard abbreviation for quarts; not present in either worked example.",
                  aliases=("quart", "quarts")),
    "L": UnitDef("L", "inferred", "Standard abbreviation for liters; not present in either worked example.",
                 aliases=("liter", "liters", "litre", "litres")),
    "mL": UnitDef("mL", "inferred", "Standard abbreviation for milliliters; not present in either worked example.",
                  aliases=("ml", "milliliter", "milliliters")),
}

CONFIRMED_UNITS: frozenset[str] = frozenset(
    abbr for abbr, u in UNIT_REGISTRY.items() if u.confidence == "confirmed"
)
INFERRED_UNITS: frozenset[str] = frozenset(
    abbr for abbr, u in UNIT_REGISTRY.items() if u.confidence == "inferred"
)

# Fields where compressed/no-space formatting is a separately-confirmed,
# deliberately different convention (see inferred_rules.invoice_desc.uppercase).
SPACING_RULE_EXEMPT_FIELDS: frozenset[str] = frozenset({"INVOICE_DESC"})

_ALIAS_TO_CANONICAL: dict[str, str] = {}
for _abbr, _unit in UNIT_REGISTRY.items():
    _ALIAS_TO_CANONICAL[_abbr.lower()] = _abbr
    for _alias in _unit.aliases:
        _ALIAS_TO_CANONICAL[_alias.lower()] = _abbr


def normalize_unit(raw: str) -> Optional[UnitDef]:
    """Case-insensitive lookup of a unit string (or known alias) -> its UnitDef.

    None if the string isn't a known unit at all — this never guesses a unit
    that wasn't asked for.
    """
    canonical = _ALIAS_TO_CANONICAL.get(raw.strip().lower())
    if canonical is None:
        return None
    return UNIT_REGISTRY[canonical]


# Longest-first so "dBA" is tried before "A" (avoids matching the "A" inside "dBA").
_UNITS_BY_LENGTH_DESC = sorted(UNIT_REGISTRY, key=len, reverse=True)
_UNIT_ALTERNATION = "|".join(re.escape(u) for u in _UNITS_BY_LENGTH_DESC)

# A digit (possibly the end of a fraction like "1/4") immediately followed by
# a known unit with no whitespace between them, and not itself the start of a
# longer word (so "24in" is a violation but "inch" and "24 inches" are not
# mangled into a false positive via the alias table — aliases aren't checked
# here, only canonical abbreviations, since those are what the delivery
# format is expected to emit).
_SPACING_VIOLATION_RE = re.compile(rf"\d(?:{_UNIT_ALTERNATION})(?![A-Za-z])")


def find_spacing_violations(value: str) -> list[str]:
    """Substrings where a number and a known unit abbreviation touch with no space."""
    if not value:
        return []
    return list(_SPACING_VIOLATION_RE.findall(value))


def has_correct_number_unit_spacing(value: str) -> bool:
    return not find_spacing_violations(value)


def _insert_space(match: re.Match) -> str:
    matched_text = match.group(0)
    for unit in _UNITS_BY_LENGTH_DESC:
        if matched_text.endswith(unit):
            return matched_text[: -len(unit)] + " " + unit
    return matched_text  # pragma: no cover - matched_text always ends in a registry unit by construction


def add_unit_spacing(value: str) -> str:
    """Insert a space wherever a number touches a known unit with none. Idempotent."""
    if not value:
        return value
    return _SPACING_VIOLATION_RE.sub(_insert_space, value)


# --------------------------------------------------------------------------
# Compound-dimension detection.
#
# CRITICAL constraint carried over from step 1
# (inferred_rules.attributes.uom_only_for_bare_numeric_values): when a
# value is a compound dimension string like "24 in W x 24-1/4 in D", the
# units stay INLINE in the value and ATTRIBUTE_UOM is left blank. Only a
# bare single number ("50-1/4") gets its unit pulled out into the paired
# UOM column. This function decides which case a value is, so callers never
# try to extract "the" unit out of a multi-number, multi-unit string.
# --------------------------------------------------------------------------

_NUMERIC_TOKEN_RE = re.compile(r"\d+(?:-\d+/\d+)?(?:\.\d+)?")
_UNIT_TOKEN_RE = re.compile(rf"(?<![A-Za-z]){_UNIT_ALTERNATION}(?![A-Za-z])")
_X_CONNECTOR_RE = re.compile(r"\s[xX]\s")
_DIM_LETTER_RE = re.compile(rf"(?:{_UNIT_ALTERNATION})\s+[WDHL]\b")


def is_compound_dimension(value: str) -> bool:
    """True if `value` bundles more than one measurement into a single string.

    Signals (any one is sufficient):
      * more than one numeric token (e.g. "24" and "24-1/4")
      * more than one unit mention (e.g. "in" appearing twice)
      * an " x " connector between dimensions
      * a unit immediately followed by a dimension-axis letter (W/D/H/L),
        e.g. "in W", "in D" — the labelled-axis style seen in the examples
    A bare value like "50-1/4" (no inline unit at all — its unit lives in
    the separate ATTRIBUTE_UOM column) has zero numeric tokens beyond the
    one number and no unit mentions, so it correctly returns False.
    """
    value = value.strip()
    if not value:
        return False
    numeric_tokens = _NUMERIC_TOKEN_RE.findall(value)
    unit_tokens = _UNIT_TOKEN_RE.findall(value)
    return (
        len(numeric_tokens) >= 2
        or len(unit_tokens) >= 2
        or bool(_X_CONNECTOR_RE.search(value))
        or bool(_DIM_LETTER_RE.search(value))
    )
