"""
Step 3: fraction <-> decimal conversion.

This module is pure arithmetic, not a house-style guess — a 64th is a 64th
regardless of what any delivery format says, so unlike inferred_rules.py
nothing here carries a confidence tier. The only thing "confirmed from the
examples" is the *string format* fractions are written in (see the
compound-form functions at the bottom); the math itself needs no evidence.

The fraction table is generated, not hand-typed: 63 numerator/64 pairs,
reduced to lowest terms. Hand-copying 63 pairs is exactly the kind of thing
that silently drifts by one typo — generating them from n/64 for
n in 1..63 is self-verifying and impossible to get subtly wrong.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional

DENOMINATOR_GRID = 64


def _build_fraction_table(grid: int = DENOMINATOR_GRID) -> dict[str, Fraction]:
    """Every n/grid for n in 1..grid-1, reduced to lowest terms, as fraction-string -> Fraction."""
    table: dict[str, Fraction] = {}
    for n in range(1, grid):
        frac = Fraction(n, grid)  # Fraction auto-reduces (1/2 not 32/64, 3/8 not 24/64, ...)
        key = f"{frac.numerator}/{frac.denominator}"
        table.setdefault(key, frac)
    return table


# fraction-string ("1/2", "3/8", ...) -> Fraction, already reduced.
FRACTION_TABLE: dict[str, Fraction] = _build_fraction_table()

# The reverse lookup: exact decimal value -> canonical reduced fraction string.
# Keyed on the Fraction itself (exact), not a float, so lookup is exact too.
_DECIMAL_TO_FRACTION: dict[Fraction, str] = {v: k for k, v in FRACTION_TABLE.items()}

_SIMPLE_FRACTION_RE = re.compile(r"^(\d+)/(\d+)$")
# "24-1/4" -> whole=24, num=1, den=4. Matches both examples' compound style exactly.
_COMPOUND_RE = re.compile(r"^(?P<whole>\d+)-(?P<num>\d+)/(?P<den>\d+)$")


def fraction_to_decimal(frac: str) -> Optional[float]:
    """'1/2' -> 0.5. Any string outside FRACTION_TABLE (e.g. '1/3') returns None.

    Only fractions that land exactly on the 1/64 grid are meaningful here —
    silently rounding '1/3' to '21/64' would fabricate precision nobody
    measured, which is exactly what this module exists to avoid.
    """
    frac = frac.strip()
    match = _SIMPLE_FRACTION_RE.match(frac)
    if not match:
        return None
    num, den = int(match.group(1)), int(match.group(2))
    if den == 0:
        return None
    value = Fraction(num, den)
    if value.denominator > DENOMINATOR_GRID or DENOMINATOR_GRID % value.denominator != 0:
        return None  # not representable on the 64ths grid (e.g. 1/3, 1/7)
    return float(value)


def decimal_to_fraction(value: float) -> Optional[str]:
    """0.5 -> '1/2'. A decimal that isn't exactly on the 1/64 grid returns None.

    Uses Fraction.limit_denominator to snap to the nearest exact grid point,
    then verifies round-trip equality before accepting it — so a value like
    0.333... (not on the grid) is rejected rather than silently reported as
    the nearest wrong 64th.
    """
    as_fraction = Fraction(value).limit_denominator(DENOMINATOR_GRID)
    if float(as_fraction) != value:
        return None
    if as_fraction.denominator == 1:
        return None  # whole numbers aren't fractions; caller should format separately
    return _DECIMAL_TO_FRACTION.get(as_fraction)


@dataclass(frozen=True)
class CompoundValue:
    """A parsed 'whole-num/den' value, e.g. 24-1/4 -> whole=24, fraction='1/4'."""

    whole: int
    fraction: str
    decimal: float

    def __str__(self) -> str:
        return f"{self.whole}-{self.fraction}"


def parse_compound(value: str) -> Optional[CompoundValue]:
    """Parse the hyphenated whole+fraction form seen in both worked examples: '24-1/4'.

    Returns None for anything that isn't exactly that shape, or whose fractional
    part isn't on the 64ths grid — this never guesses.
    """
    value = value.strip()
    match = _COMPOUND_RE.match(value)
    if not match:
        return None
    whole = int(match.group("whole"))
    frac_str = f"{match.group('num')}/{match.group('den')}"
    frac_decimal = fraction_to_decimal(frac_str)
    if frac_decimal is None:
        return None
    # Re-derive the canonical reduced form so '24-2/8' normalizes to '24-1/4'.
    canonical_frac = decimal_to_fraction(frac_decimal)
    if canonical_frac is None:  # pragma: no cover - frac_decimal already validated on-grid
        return None
    return CompoundValue(whole=whole, fraction=canonical_frac, decimal=whole + frac_decimal)


def format_compound(whole: int, decimal_fraction: float) -> Optional[str]:
    """Inverse of parse_compound: (24, 0.25) -> '24-1/4'. None if not on the 64ths grid."""
    if decimal_fraction == 0:
        return str(whole)
    frac_str = decimal_to_fraction(decimal_fraction)
    if frac_str is None:
        return None
    return f"{whole}-{frac_str}"


def compound_to_decimal(value: str) -> Optional[float]:
    """'24-1/4' -> 24.25. Falls back to a plain float/int string. None if unparseable."""
    compound = parse_compound(value)
    if compound is not None:
        return compound.decimal
    try:
        return float(value.strip())
    except ValueError:
        return None
