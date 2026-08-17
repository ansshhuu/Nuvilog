from __future__ import annotations

from pipeline.delivery_format import load_worked_examples
from pipeline.uom_normalizer import (
    CONFIRMED_UNITS,
    INFERRED_UNITS,
    has_correct_number_unit_spacing,
    is_compound_dimension,
    normalize_unit,
)


def test_confirmed_units_are_exactly_what_the_examples_show():
    # These 4 are the only units that appear verbatim anywhere in the 2
    # worked examples — see inferred_rules.uom.number_unit_spacing evidence.
    assert CONFIRMED_UNITS == {"in", "V", "A", "dBA"}


def test_inferred_units_are_disjoint_from_confirmed():
    assert CONFIRMED_UNITS.isdisjoint(INFERRED_UNITS)


def test_normalize_unit_resolves_aliases():
    assert normalize_unit("inches").abbreviation == "in"
    assert normalize_unit("volts").abbreviation == "V"
    assert normalize_unit("nonsense-unit") is None


def test_spacing_confirmed_examples_pass():
    for value in ("120 V", "15 A", "24 in", "24-1/4 in", "47 dBA", "10-3/8 in"):
        assert has_correct_number_unit_spacing(value), value


def test_spacing_violations_detected():
    for value in ("120V", "15A", "24in", "47dBA", "50-1/4in"):
        assert not has_correct_number_unit_spacing(value), value


def test_is_compound_dimension_true_for_real_example_strings():
    compound_examples = [
        "24 in W x 24-1/4 in D",
        "33-7/16 in H x 23-7/8 in W x 22-5/8 in D",
        "8-1/2 in Upper Rack, 11-1/4 in Lower Rack",
        "10-3/8 in Upper Rack, 13-1/4 in Lower Rack",
    ]
    for value in compound_examples:
        assert is_compound_dimension(value), value


def test_is_compound_dimension_false_for_bare_numeric_pairs():
    # unit lives in the separate UOM column, not inline — see
    # inferred_rules.attributes.uom_only_for_bare_numeric_values
    for value in ("50-1/4", "47", "120", "15", "5"):
        assert not is_compound_dimension(value), value


def test_compound_detection_against_every_attribute_slot_in_both_examples():
    """Cross-check against the real delivery file: any slot where UOM is
    filled must NOT be classified compound, and any compound VALUE in the
    real data must NOT have a filled UOM (mirrors
    inferred_rules.uom.compound_dimension_uom_blank)."""
    examples = load_worked_examples()
    for row in examples:
        for i in range(1, 51):
            value = row.get(f"ATTRIBUTE_VALUE {i}", "").strip()
            uom = row.get(f"ATTRIBUTE_UOM {i}", "").strip()
            if not value:
                continue
            if is_compound_dimension(value):
                assert not uom, f"slot {i} value={value!r} compound but UOM={uom!r}"
