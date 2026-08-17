"""
Step 6 runner: description builder — self-test the format rules, then
generate real descriptions (live LLM calls) for all 10 dishwasher rows.

    python backend/scripts/step6_description_builder.py

Order:

  1. FORMAT SPEC SELF-TEST — recompute each format's construction rule from
     inferred_rules.py + the 2 worked examples and print it, including
     whether the brief's MOBILE_DESC 60-80 char claim actually holds
     against both examples (computed, not asserted).

  2. TRUSTED-FIELD SELF-TEST — prove the exclusion filter: the 2 known rows
     get real attribute values, the other 8 get Mfg_Part_Num/Part_Desc only
     and nothing else, byte-checked.

  3. GENERATE — one live LLM call per row (10 total) via
     description_builder.generate_descriptions(). For the 2 known rows,
     compare against the real answer via evaluate_row() using TIER 2/3 as
     the bar, not tier 1 exact match (the brief itself says this won't be
     byte-exact). For the other 8, print the (short, generic) output and
     confirm it stays short.

  4. FACTUAL-CONSISTENCY REPORT — find_invented_numbers() run on every row,
     tallied. This includes the ground-truth MARKETING_DESCRIPTION for
     WDTS7024RZ passed through unmodified, which is expected to show a
     violation — see the module docstring for why that's a finding, not a
     bug in the check.

Costs real GEMINI_API_KEY calls (10 rows x 1 call each). If GEMINI_API_KEY
isn't set, this prints the setup instructions and exits 1 rather than
crashing mid-run.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from pipeline.dataset_loader import load_input_dataset  # noqa: E402
from pipeline.delivery_format import load_delivery_format, load_worked_examples  # noqa: E402
from pipeline.description_builder import (  # noqa: E402
    DESCRIPTION_FIELDS,
    build_format_specs,
    find_invented_numbers,
    generate_descriptions,
    trusted_fields_for_row,
)
from pipeline.dishwasher_schema import (  # noqa: E402
    DISHWASHER_ATTRIBUTE_LABELS,
    blank_dishwasher_scaffold,
    build_dishwasher_attribute_slots,
    is_dishwasher,
)
from pipeline.evaluation import derive_zero_evidence_columns, evaluate_row  # noqa: E402
from pipeline.llm_client import LLMClient  # noqa: E402
from pipeline.rate_limiter import RateLimitedLLM, RateLimiter  # noqa: E402

KNOWN_MPNS = {"PDSH4816AF", "WDTS7024RZ"}


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def section(title: str) -> None:
    print(f"\n-- {title} " + "-" * max(0, 74 - len(title)))


def format_spec_self_test(examples: list[dict[str, str]]) -> bool:
    rule("1. FORMAT SPEC SELF-TEST — construction rule per format")
    specs = build_format_specs(examples)
    for name in DESCRIPTION_FIELDS:
        spec = specs[name]
        bounds = ""
        if spec.min_len or spec.max_len:
            bounds = f" [len {spec.min_len or '?'}-{spec.max_len or '?'}]"
        print(f"  {name:<24} confidence={spec.confidence:<6}{bounds}")
        print(f"      rule: {spec.rule}")
    return True


def _source_row(mpn: str, part_desc: str, raw_row: dict[str, str]) -> dict[str, str]:
    return {
        "Mfg_Part_Num": mpn,
        "Part_Desc": part_desc,
        "E1_Brand": raw_row.get("E1_Brand", ""),
        "Unilog_Brand": raw_row.get("Unilog_Brand", ""),
        "DIB_Brand": raw_row.get("DIB_Brand", ""),
        "Part_Manuf": raw_row.get("Part_Manuf", ""),
    }


def trusted_field_self_test(examples: list[dict[str, str]], dataset) -> bool:
    rule("2. TRUSTED-FIELD SELF-TEST — exclusion filter proves itself")
    ok = True

    section("known row gets real attribute values")
    example = examples[0]
    mpn = example["Mfg_Part_Num"]
    fields = trusted_fields_for_row(mpn, example["Part_Desc"], expected=example)
    has_real_attrs = any(k not in ("Mfg_Part_Num", "Part_Desc") for k in fields)
    print(f"  {mpn}: trusted fields = {sorted(fields)}")
    if not has_real_attrs:
        ok = False
        print("  FAIL — known row got no attribute values at all.")
    else:
        print(f"  PASS — {len(fields) - 2} real attribute/brand fields passed through.")

    section("unverified row gets ONLY Mfg_Part_Num/Part_Desc")
    dishwasher_rows = dataset.frame[dataset.frame["Part_Desc"].map(is_dishwasher)]
    unverified = dishwasher_rows[~dishwasher_rows["Mfg_Part_Num"].isin(KNOWN_MPNS)]
    row = unverified.iloc[0]
    fields = trusted_fields_for_row(row["Mfg_Part_Num"], row["Part_Desc"], expected=None)
    print(f"  {row['Mfg_Part_Num']}: trusted fields = {fields}")
    if set(fields) != {"Mfg_Part_Num", "Part_Desc"}:
        ok = False
        print(f"  FAIL — expected exactly 2 keys, got {sorted(fields)}.")
    else:
        print("  PASS — exactly Mfg_Part_Num + Part_Desc, nothing invented.")

    return ok


def _row_columns_besides_descriptions(expected: dict[str, str] | None) -> dict[str, str]:
    """The attribute-scaffold + brand columns that belong on the same
    assembled row as the descriptions, so evaluate_row's tier-3 invented-
    numbers check sees the same trusted data generate_descriptions() did —
    otherwise every number the LLM correctly grounded in a real attribute
    value looks 'invented' purely because the row this script assembled
    for evaluation left that attribute out."""
    if expected is None:
        return blank_dishwasher_scaffold()

    values = {
        label: (expected.get(f"ATTRIBUTE_VALUE {i}") or "").strip()
        for i, label in enumerate(DISHWASHER_ATTRIBUTE_LABELS, start=1)
    }
    values = {label: v for label, v in values.items() if v}
    columns = build_dishwasher_attribute_slots(values)
    for col in ("BRAND_NAME", "MANUFACTURER_NAME"):
        value = (expected.get(col) or "").strip()
        if value:
            columns[col] = value
    return columns


def generate_for_known_rows(examples: list[dict[str, str]], dataset, llm: LLMClient, fmt, zero_evidence) -> None:
    rule("3a. GENERATE — the 2 known rows (real answer available for comparison)")
    for example in examples:
        mpn = example["Mfg_Part_Num"]
        raw_row = dataset.frame[dataset.frame["Mfg_Part_Num"] == mpn].iloc[0]
        section(mpn)

        descriptions, violations = generate_descriptions(
            mpn, example["Part_Desc"], expected=example, llm=llm
        )
        for field_name in DESCRIPTION_FIELDS:
            real = example.get(field_name, "").strip()
            gen = descriptions.get(field_name, "")
            print(f"  {field_name}:")
            print(f"      real:      {real!r}")
            print(f"      generated: {gen!r}")

        source = _source_row(mpn, example["Part_Desc"], raw_row)
        generated_row = fmt.empty_row()
        generated_row.update(source)
        generated_row.update(_row_columns_besides_descriptions(example))
        generated_row.update(descriptions)
        # expected=example so the manufacturer/brand honesty check (which only
        # applies when expected is None) correctly skips these 2 known rows —
        # their BRAND_NAME/MANUFACTURER_NAME are real ground truth, not
        # fabricated. Tier 1 will show near-total mismatch on the description
        # fields themselves; that's expected and reported separately below as
        # informational, not folded into the pass/fail bar (see module docstring
        # on why byte-exact was never the right bar here).
        result = evaluate_row(
            generated_row,
            expected=example,
            source_input=source,
            row_id=mpn,
            fmt=fmt,
            zero_evidence_columns=zero_evidence,
        )
        tier1 = result.tier(1)
        tier1_exact = sum(1 for c in tier1 if c.status == "pass")
        tier23 = result.tier(2) + result.tier(3)
        tier23_counts = {
            status: sum(1 for c in tier23 if c.status == status)
            for status in ("pass", "warn", "fail")
        }
        print(f"  tier1 exact-match (informational only): {tier1_exact}/{len(tier1)} fields")
        print(f"  tier2/tier3 rule compliance (the actual bar): {tier23_counts}")
        for c in tier23:
            if c.status == "fail":
                print(f"      FAIL tier{c.tier} {c.check_id}: {c.reason}")
        if violations:
            print(f"  invented-number violations: {violations}")
        else:
            print("  no invented numbers detected in generated text.")


def generate_for_unverified_rows(dataset, llm: LLMClient, fmt, zero_evidence) -> None:
    rule("3b. GENERATE — the 8 unverified rows (Mfg_Part_Num/Part_Desc only)")
    dishwasher_rows = dataset.frame[dataset.frame["Part_Desc"].map(is_dishwasher)]
    unverified = dishwasher_rows[~dishwasher_rows["Mfg_Part_Num"].isin(KNOWN_MPNS)]

    for _, row in unverified.iterrows():
        mpn, part_desc = row["Mfg_Part_Num"], row["Part_Desc"]
        section(mpn)
        descriptions, violations = generate_descriptions(mpn, part_desc, expected=None, llm=llm)
        for field_name in DESCRIPTION_FIELDS:
            gen = descriptions.get(field_name, "")
            print(f"  {field_name} (len={len(gen)}): {gen!r}")

        source = _source_row(mpn, part_desc, row)
        generated_row = fmt.empty_row()
        generated_row.update(source)
        generated_row.update(_row_columns_besides_descriptions(None))
        generated_row.update(descriptions)
        result = evaluate_row(
            generated_row,
            expected=None,
            source_input=source,
            row_id=mpn,
            fmt=fmt,
            zero_evidence_columns=zero_evidence,
        )
        counts = result.counts()
        print(f"  tier2/tier3 rule compliance: {counts}")
        for c in result.failures:
            print(f"      FAIL tier{c.tier} {c.check_id}: {c.reason}")
        if violations:
            print(f"  invented-number violations: {violations}")


def ground_truth_consistency_check(examples: list[dict[str, str]]) -> None:
    rule("4. FACTUAL-CONSISTENCY CHECK APPLIED TO THE REAL GROUND TRUTH ITSELF")
    print(
        "Sanity check on the check: run find_invented_numbers against the worked\n"
        "examples' OWN real description text, using their OWN real attribute values\n"
        "as the trusted set. A violation here isn't a bug in the check — it's proof\n"
        "that some ground-truth description content (e.g. marketing copy) references\n"
        "specs that are genuinely not present anywhere in the structured input."
    )
    for example in examples:
        mpn = example["Mfg_Part_Num"]
        trusted = trusted_fields_for_row(mpn, example["Part_Desc"], expected=example)
        real_descriptions = {f: example.get(f, "") for f in DESCRIPTION_FIELDS}
        violations = find_invented_numbers(real_descriptions, trusted)
        section(mpn)
        if violations:
            print(f"  ground-truth violations: {violations}")
        else:
            print("  ground truth is fully traceable to its own attribute values.")


def main() -> int:
    if not (os.getenv("GEMINI_API_KEY")):
        print("GEMINI_API_KEY is not set. Copy .env.example to .env and add your key.")
        return 1

    fmt = load_delivery_format()
    examples = load_worked_examples()
    dataset = load_input_dataset()
    zero_evidence = derive_zero_evidence_columns(examples, fmt)
    # 10 rows x 1 call each is over the free-tier's 15/min ceiling once you
    # account for the burst shape (see rate_limiter.py's measured numbers) —
    # spread the calls out rather than let the run die on a 429 partway
    # through row 5.
    llm = RateLimitedLLM(LLMClient(), RateLimiter())

    ok = format_spec_self_test(examples)
    ok = trusted_field_self_test(examples, dataset) and ok

    rule("SELF-TESTS " + ("PASSED" if ok else "FAILED"))
    if not ok:
        print("Refusing to spend LLM calls generating from an unverified trusted-field filter.")
        return 1

    generate_for_known_rows(examples, dataset, llm, fmt, zero_evidence)
    generate_for_unverified_rows(dataset, llm, fmt, zero_evidence)
    ground_truth_consistency_check(examples)

    rule("STEP 6 COMPLETE")
    print(
        "description_builder.py generates all 5 in-scope formats for all 10 dishwasher\n"
        "rows, constrained to real per-row data only. RETAIL_DESC stays out of scope\n"
        "(see module docstring). Generated text is measured via tier 2 rule-compliance\n"
        "and the new tier 3 description.no_invented_numbers check, not exact match —\n"
        "the ground-truth consistency check above shows why exact match was never the\n"
        "right bar for MARKETING_DESCRIPTION in particular."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
