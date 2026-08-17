from __future__ import annotations

import pytest

from pipeline.fraction_converter import (
    DENOMINATOR_GRID,
    FRACTION_TABLE,
    compound_to_decimal,
    decimal_to_fraction,
    format_compound,
    fraction_to_decimal,
    parse_compound,
)


def test_fraction_table_has_63_reduced_entries():
    assert len(FRACTION_TABLE) == DENOMINATOR_GRID - 1
    # generated, reduced form — not the raw n/64 for reducible n
    assert "1/2" in FRACTION_TABLE
    assert "32/64" not in FRACTION_TABLE
    assert "1/4" in FRACTION_TABLE
    assert "16/64" not in FRACTION_TABLE
    assert "3/8" in FRACTION_TABLE
    assert "24/64" not in FRACTION_TABLE


@pytest.mark.parametrize("frac_str", sorted(FRACTION_TABLE))
def test_every_64th_round_trips(frac_str):
    decimal = fraction_to_decimal(frac_str)
    assert decimal is not None
    assert decimal_to_fraction(decimal) == frac_str


def test_non_64th_grid_decimal_returns_none():
    assert decimal_to_fraction(0.333) is None
    assert decimal_to_fraction(1 / 3) is None


def test_non_64th_grid_fraction_returns_none():
    assert fraction_to_decimal("1/3") is None
    assert fraction_to_decimal("1/7") is None


def test_compound_hyphenated_form_matches_worked_examples():
    assert compound_to_decimal("24-1/4") == 24.25
    assert compound_to_decimal("50-1/4") == 50.25
    assert compound_to_decimal("33-7/16") == pytest.approx(33 + 7 / 16)


def test_compound_reverse_direction():
    assert format_compound(24, 0.25) == "24-1/4"
    assert format_compound(50, 0.25) == "50-1/4"


def test_parse_compound_rejects_non_matching_shape():
    assert parse_compound("1/3") is None
    assert parse_compound("24") is None
    assert parse_compound("not a number") is None


def test_parse_compound_normalizes_to_lowest_terms():
    # 2/8 should normalize to 1/4 through the same reduced table
    parsed = parse_compound("24-2/8")
    assert parsed is not None
    assert parsed.fraction == "1/4"
    assert parsed.decimal == 24.25
