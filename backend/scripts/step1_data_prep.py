"""
Step 1 runner: load the real data, print what's actually there.

    python backend/scripts/step1_data_prep.py

Prints, in order:
  1. the cleaned input dataset (shape, columns, placeholder report, samples)
  2. the parsed 252-column delivery format, grouped
  3. the inferred rules, each re-checked against the 2 worked examples

Nothing here writes files or calls an LLM. It exists so we can eyeball the
real data shape before building anything on top of it.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pandas as pd  # noqa: E402

from pipeline.dataset_loader import load_input_dataset, placeholder_report  # noqa: E402
from pipeline.delivery_format import (  # noqa: E402
    load_delivery_format,
    load_worked_examples,
)
from pipeline.inferred_rules import (  # noqa: E402
    INFERENCE_BASIS,
    NOT_BUILT,
    verify_rules,
)


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def section(title: str) -> None:
    print(f"\n-- {title} " + "-" * max(0, 74 - len(title)))


def show_input() -> None:
    rule("1. INPUT DATASET")
    dataset = load_input_dataset()
    frame = dataset.frame

    print(f"source      : {dataset.source_path.name}")
    print(f"shape       : {frame.shape[0]} rows x {len(dataset.raw_columns)} original columns")
    print(f"raw columns : {', '.join(dataset.raw_columns)}")
    derived = [c for c in frame.columns if c not in dataset.raw_columns]
    print(f"derived     : {', '.join(derived)}")

    section("placeholder stripping")
    print(placeholder_report(dataset).to_string(index=False))
    print(
        "\nSentinels are nulled in the *_clean columns only. The originals are kept "
        "because the delivery format echoes them back verbatim."
    )

    section("sample rows (cleaned view)")
    view = frame[
        ["Mfg_Part_Num", "Part_Desc", "brand_resolved", "manuf_name", "manuf_code"]
    ].head(8)
    with pd.option_context("display.max_colwidth", 46, "display.width", 200):
        print(view.to_string(index=False))

    section("brand coverage after cleaning")
    resolved = int(frame["brand_resolved"].notna().sum())
    print(f"rows with any real brand : {resolved} / {len(frame)}")
    print(f"rows with no brand at all: {len(frame) - resolved}")
    print("\ntop resolved brands:")
    print(frame["brand_resolved"].value_counts().head(8).to_string())

    section("Part_Manuf (the one reliable manufacturer signal)")
    print(f"distinct manufacturers: {frame['manuf_name'].nunique()}")
    print(f"rows with a vendor code parsed: {int(frame['manuf_code'].notna().sum())} / {len(frame)}")
    print(frame[["manuf_name", "manuf_code"]].drop_duplicates().head(8).to_string(index=False))


def show_delivery_format() -> None:
    rule("2. DELIVERY FORMAT (252 columns, parsed)")
    fmt = load_delivery_format()

    print(f"source : {fmt.source_path.name}")
    print(f"columns: {len(fmt.columns)}")
    print(f"groups : {len(fmt.groups)}\n")

    header = f"{'group':<24}{'cols':>5}  description"
    print(header)
    print("-" * 78)
    for name, count, description in fmt.summary():
        print(f"{name:<24}{count:>5}  {description}")
    print("-" * 78)
    print(f"{'TOTAL':<24}{sum(len(g) for g in fmt.groups.values()):>5}")

    section("repeating structures (parsed, not flat)")
    print(f"attribute triplets : {len(fmt.attribute_slots)} slots x 3 columns")
    first = fmt.attribute_slots[0]
    print(f"  slot 1 -> {first.label_column} / {first.value_column} / {first.uom_column}")
    print(f"item feature slots : {len(fmt.item_feature_columns)}")
    print(f"measure pairs      : {', '.join(f'{p.value_column}+{p.uom_column}' for p in fmt.measure_pairs)}")

    section("non-repeating group contents")
    for name in ("identity", "classification", "manufacturer_brand", "descriptions",
                 "description_components", "commerce", "metadata"):
        group = fmt.group(name)
        print(f"{name:<24}: {', '.join(group.fields)}")

    section("digital assets")
    assets = fmt.group("digital_assets").fields
    for i in range(0, len(assets), 4):
        print("  " + ", ".join(assets[i:i + 4]))


def show_inferred_rules() -> None:
    rule("3. INFERRED RULES (from 2 worked examples — NOT a spec)")
    examples = load_worked_examples()
    print(f"worked example rows available: {len(examples)}")
    print(f"basis: {INFERENCE_BASIS}\n")

    checks = verify_rules(examples)
    holds = sum(1 for c in checks if c.passed is True)
    violated = [c for c in checks if c.passed is False]
    unchecked = sum(1 for c in checks if c.passed is None)
    print(f"{len(checks)} rules — {holds} machine-checked and consistent, "
          f"{len(violated)} violated, {unchecked} not machine-checkable\n")

    for check in checks:
        r = check.rule
        print(f"[{check.status:<9}] [{r.confidence:<6}] {r.id}")
        print(f"              field   : {r.field}")
        print(f"              rule    : {r.rule}")
        print(f"              evidence: {r.evidence}")
        if r.note:
            print(f"              caveat  : {r.note}")
        print()

    if violated:
        print("VIOLATED rules mean the stated pattern does not hold in the examples "
              "— fix the rule, don't fix the data.\n")

    section("NOT BUILT (no reference file exists)")
    for name, reason in NOT_BUILT:
        print(f"* {name}\n  {reason}\n")


def main() -> None:
    show_input()
    show_delivery_format()
    show_inferred_rules()
    rule("STEP 1 COMPLETE")
    print(
        "Cleaned input, grouped 252-column schema and inferred-rule reference are\n"
        "importable from backend/pipeline/{dataset_loader,delivery_format,inferred_rules}.py.\n"
        "Every rule above is a hypothesis with n=2. Treat it that way downstream."
    )


if __name__ == "__main__":
    main()
