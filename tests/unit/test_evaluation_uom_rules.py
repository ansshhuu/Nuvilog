"""Step 3: the two new Tier 2 checks must pass against the real ground truth.

Passing here proves the rules match what's actually in the 2 known rows, not
just that they're internally consistent with each other.
"""
from __future__ import annotations

import copy

from pipeline.delivery_format import load_worked_examples
from pipeline.evaluation import evaluate_row


def test_number_unit_spacing_check_passes_on_both_known_rows():
    for i, example in enumerate(load_worked_examples()):
        result = evaluate_row(copy.deepcopy(example), expected=example, row_id=f"row-{i}")
        spacing_checks = [c for c in result.tier(2) if c.check_id == "uom.number_unit_spacing"]
        assert len(spacing_checks) == 1
        assert spacing_checks[0].status == "pass", spacing_checks[0].reason


def test_compound_dimension_uom_blank_check_passes_on_both_known_rows():
    for i, example in enumerate(load_worked_examples()):
        result = evaluate_row(copy.deepcopy(example), expected=example, row_id=f"row-{i}")
        compound_checks = [c for c in result.tier(2) if c.check_id == "uom.compound_dimension_uom_blank"]
        assert len(compound_checks) == 1
        assert compound_checks[0].status == "pass", compound_checks[0].reason


def test_spacing_check_catches_injected_violation():
    example = load_worked_examples()[0]
    broken = copy.deepcopy(example)
    broken["LONG_DESC1"] = broken["LONG_DESC1"].replace("120 V", "120V")
    result = evaluate_row(broken, expected=example, row_id="broken-spacing")
    spacing_check = next(c for c in result.tier(2) if c.check_id == "uom.number_unit_spacing")
    assert spacing_check.status == "fail"


def test_compound_uom_check_catches_injected_violation():
    example = load_worked_examples()[0]
    broken = copy.deepcopy(example)
    # ATTRIBUTE_VALUE 8 ("Size") is a real compound value in row 0; fill its UOM.
    broken["ATTRIBUTE_UOM 8"] = "in"
    result = evaluate_row(broken, expected=example, row_id="broken-compound-uom")
    compound_check = next(c for c in result.tier(2) if c.check_id == "uom.compound_dimension_uom_blank")
    assert compound_check.status == "fail"
