"""
Step 5 runner: dishwasher category schema — self-test against both known
rows before generalizing to the other 8 dishwasher rows with no answer key.

    python backend/scripts/step5_dishwasher_schema.py

Order matters here and is deliberate:

  1. RECONSTRUCTION SELF-TEST — feed each known row's own label->value pairs
     back through build_dishwasher_attribute_slots() and require a
     byte-for-byte match against that row's real ATTRIBUTE_LABEL/VALUE/UOM
     1-15 columns. If the schema can't reproduce the 2 rows it was read off
     of, it's wrong and nothing past this point should be trusted.

  2. HARNESS WIRING SELF-TEST — evaluate_row()'s new
     attributes.dishwasher_scaffold_15_labels check must pass both known
     rows and catch two deliberately introduced breaks (wrong label order,
     a label beyond slot 15).

  3. GENERALIZE, HONESTLY — apply the scaffold (labels only, values BLANK)
     to the other 8 dishwasher rows that have no known answer. This is the
     only thing that generalizes: the label positions, not the values. No
     Series/Voltage/Amperage/etc. is invented for these 8 rows.

  4. SCOPE REPORT — print what this explicitly does NOT cover (the 5 other
     appliance sub-types), pointing at the NOT_BUILT entries added to
     inferred_rules.py for range/washer/microwave/freezer/cooktop.

If either self-test fails, the script exits non-zero.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from pipeline.dataset_loader import load_input_dataset  # noqa: E402
from pipeline.delivery_format import load_worked_examples  # noqa: E402
from pipeline.dishwasher_schema import (  # noqa: E402
    DISHWASHER_ATTRIBUTE_LABELS,
    blank_dishwasher_scaffold,
    build_dishwasher_attribute_slots,
    is_dishwasher,
)
from pipeline.evaluation import evaluate_row  # noqa: E402
from pipeline.inferred_rules import NOT_BUILT  # noqa: E402


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def section(title: str) -> None:
    print(f"\n-- {title} " + "-" * max(0, 74 - len(title)))


def _extract_label_values(row: dict[str, str]) -> dict[str, str]:
    """Pull {label: value} for slots 1-15 straight off a known row."""
    values = {}
    for i in range(1, 16):
        label = row.get(f"ATTRIBUTE_LABEL {i}", "").strip()
        value = row.get(f"ATTRIBUTE_VALUE {i}", "").strip()
        if label:
            values[label] = value
    return values


def reconstruction_self_test(examples: list[dict[str, str]]) -> bool:
    rule("1. RECONSTRUCTION SELF-TEST — rebuild both known rows from their own values")
    ok = True

    for row in examples:
        mpn = row["Mfg_Part_Num"]
        section(mpn)
        label_values = _extract_label_values(row)
        rebuilt = build_dishwasher_attribute_slots(label_values)

        mismatches = []
        for i in range(1, 16):
            for role, col_fmt in (("LABEL", "ATTRIBUTE_LABEL {}"), ("VALUE", "ATTRIBUTE_VALUE {}"), ("UOM", "ATTRIBUTE_UOM {}")):
                col = col_fmt.format(i)
                expected = row.get(col, "").strip()
                actual = rebuilt.get(col, "").strip()
                if expected != actual:
                    mismatches.append((col, expected, actual))

        if mismatches:
            ok = False
            print(f"  FAIL — {len(mismatches)} slot mismatch(es):")
            for col, expected, actual in mismatches:
                print(f"    {col}: expected={expected!r} rebuilt={actual!r}")
        else:
            print("  PASS — all 15 LABEL/VALUE/UOM triplets reproduced byte-for-byte.")

    return ok


def harness_wiring_self_test(examples: list[dict[str, str]]) -> bool:
    rule("2. HARNESS WIRING SELF-TEST — evaluate_row()'s dishwasher scaffold check")
    ok = True

    def _source(row: dict[str, str]) -> dict[str, str]:
        return {c: row.get(c, "") for c in ("Mfg_Part_Num", "Part_Desc", "E1_Brand", "Unilog_Brand", "DIB_Brand", "Part_Manuf")}

    section("(a) both known rows must pass as-is")
    for example in examples:
        generated = copy.deepcopy(example)
        result = evaluate_row(generated, expected=example, source_input=_source(example), row_id=example["Mfg_Part_Num"])
        check = next(c for c in result.tier(2) if c.check_id == "attributes.dishwasher_scaffold_15_labels")
        passed = check.status == "pass"
        print(f"  {'PASS' if passed else 'FAIL'} — {example['Mfg_Part_Num']}: {check.status} ({check.reason})")
        if not passed:
            ok = False

    section("(b) wrong label order must be caught")
    broken = copy.deepcopy(examples[0])
    broken["ATTRIBUTE_LABEL 1"], broken["ATTRIBUTE_LABEL 2"] = broken["ATTRIBUTE_LABEL 2"], broken["ATTRIBUTE_LABEL 1"]
    result = evaluate_row(broken, expected=None, source_input=_source(examples[0]), row_id="self-test-wrong-order")
    check = next(c for c in result.tier(2) if c.check_id == "attributes.dishwasher_scaffold_15_labels")
    caught = check.status == "fail"
    print(f"  {'PASS' if caught else 'FAIL'} — swapped ATTRIBUTE_LABEL 1/2 caught: {check.status}")
    if not caught:
        ok = False

    section("(c) a label beyond slot 15 must be caught")
    broken2 = copy.deepcopy(examples[0])
    broken2["ATTRIBUTE_LABEL 16"] = "Made Up Label"
    result = evaluate_row(broken2, expected=None, source_input=_source(examples[0]), row_id="self-test-extra-slot")
    check = next(c for c in result.tier(2) if c.check_id == "attributes.dishwasher_scaffold_15_labels")
    caught = check.status == "fail"
    print(f"  {'PASS' if caught else 'FAIL'} — label at slot 16 caught: {check.status}")
    if not caught:
        ok = False

    section("(d) non-dishwasher rows must be skipped, not flagged")
    non_dw_source = {"Mfg_Part_Num": "X", "Part_Desc": "30\" GE Electric Range SS", "E1_Brand": "", "Unilog_Brand": "", "DIB_Brand": "", "Part_Manuf": ""}
    empty_generated = {f"ATTRIBUTE_LABEL {i}": "" for i in range(1, 51)}
    empty_generated.update({f"ATTRIBUTE_VALUE {i}": "" for i in range(1, 51)})
    empty_generated.update({f"ATTRIBUTE_UOM {i}": "" for i in range(1, 51)})
    result = evaluate_row(empty_generated, expected=None, source_input=non_dw_source, row_id="self-test-non-dishwasher")
    check = next(c for c in result.tier(2) if c.check_id == "attributes.dishwasher_scaffold_15_labels")
    skipped = check.status == "pass" and "not applicable" in check.reason
    print(f"  {'PASS' if skipped else 'FAIL'} — a range row is not held to the dishwasher scaffold")
    if not skipped:
        ok = False

    return ok


def show_generalization(dataset) -> None:
    rule("3. GENERALIZE, HONESTLY — the other 8 dishwasher rows (no known answer)")

    dishwasher_rows = dataset.frame[dataset.frame["Part_Desc"].map(is_dishwasher)]
    known = {"PDSH4816AF", "WDTS7024RZ"}
    unverified = dishwasher_rows[~dishwasher_rows["Mfg_Part_Num"].isin(known)]

    print(f"dishwasher rows total: {len(dishwasher_rows)} (2 known + {len(unverified)} unverified)\n")

    blank = blank_dishwasher_scaffold()
    section("what gets applied to each unverified row")
    print(
        "The 15-label scaffold, values BLANK — labels stay populated per "
        "inferred_rules.attributes.labels_kept_when_value_unknown, values are not guessed."
    )
    for i in range(1, 16):
        label = blank[f"ATTRIBUTE_LABEL {i}"]
        print(f"  {i:>2}. {label}")

    section("rows this applies to")
    for _, row in unverified.iterrows():
        print(f"  {row['Mfg_Part_Num']:<15} {row['Part_Desc']}")

    print(
        "\nNo Series/Voltage/Amperage/Size/etc. VALUE is populated for these 8 rows — that "
        "data isn't in the 6-column input and sourcing it needs external lookup, same "
        "constraint documented in manufacturer_normalizer.py for MANUFACTURER_NAME/BRAND_NAME."
    )


def show_scope_boundary() -> None:
    rule("4. SCOPE BOUNDARY — what this step explicitly does not cover")
    for name, reason in NOT_BUILT:
        if "attribute scaffold" in name and name != "attribute LOV / constrained vocabulary":
            print(f"* {name}\n  {reason}\n")


def main() -> int:
    examples = load_worked_examples()
    dataset = load_input_dataset()

    ok = reconstruction_self_test(examples)
    ok = harness_wiring_self_test(examples) and ok

    rule("SELF-TESTS " + ("PASSED" if ok else "FAILED"))
    if not ok:
        print("Refusing to print the generalization/scope sections from an unverified schema.")
        return 1

    show_generalization(dataset)
    show_scope_boundary()

    rule("STEP 5 COMPLETE")
    print(
        "pipeline/dishwasher_schema.py is self-tested against both known rows and wired "
        "into pipeline/evaluation.py as attributes.dishwasher_scaffold_15_labels. It covers "
        "10 real dishwasher rows (2 verified, 8 structural-only). Range/washer/microwave/"
        "freezer/cooktop (31 more real rows) remain NOT_BUILT in inferred_rules.py — real "
        "data, zero scaffold evidence."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
