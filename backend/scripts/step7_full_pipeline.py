"""
Step 7: full pipeline — assemble a complete 252-column delivery-format row
for all 10 real dishwasher rows using every step built so far, score each
one, and write a real report (not a console-only summary).

    python backend/scripts/step7_full_pipeline.py

WHAT GETS ASSEMBLED PER ROW, AND FROM WHERE

  source_passthrough
      dataset_loader's raw 6 input columns, verbatim. Real for all 10 rows.

  ATTRIBUTE_LABEL/VALUE/UOM 1-15
      dishwasher_schema.py. Real values for the 2 known rows (pulled from
      that row's own worked example — genuine ground truth, not an
      inference). Labels-only, values blank for the other 8 — per
      inferred_rules.attributes.labels_kept_when_value_unknown, the label
      scaffold generalizes, the values do not (dishwasher_schema.py's own
      docstring is explicit about this boundary).

  MANUFACTURER_NAME / BRAND_NAME
      Real ground truth for the 2 known rows only. For the other 8,
      manufacturer_normalizer.resolve_manufacturer() supplies a per-row
      confidence label ("vendor code present, actual manufacturer
      unresolved" / "no vendor data") that is printed in this report, but
      is NEVER written into the MANUFACTURER_NAME/BRAND_NAME columns —
      that module proved those fields aren't derivable from the input at
      all (see its docstring), so a blank column is the honest output.

  INVOICE_DESC / MOBILE_DESC / SHORT_DESC / LONG_DESC1 / MARKETING_DESCRIPTION
      description_builder.py, one live LLM call per row, constrained to
      exactly the trusted fields above.

  everything else (Classpath, commerce, physical, digital_assets, ...)
      Left blank. No module in this codebase builds them — see
      inferred_rules.NOT_BUILT. This report's coverage section says so
      explicitly rather than letting 200+ blank columns pass unremarked.

SCORING

  Every assembled row goes through evaluation.evaluate_row(): tier 1
  (exact match) is computed for the 2 known rows but is INFORMATIONAL
  ONLY — descriptions are LLM prose, never byte-exact, see
  description_builder's docstring. Tier 2 (rule compliance) + tier 3
  (honesty, including the new description.no_invented_numbers check) are
  the actual bar, and they run on all 10 rows regardless of ground truth.

OUTPUT

  backend/output/dishwasher_delivery_rows.csv  — 252-column delivery-format
      CSV, one row per dishwasher part, in the real column order.
  backend/output/step7_report.md               — this run's report:
      per-row scores, the coverage table, and the scope boundary.

Costs 10 live GEMINI_API_KEY calls, rate-limited (see rate_limiter.py) to
stay under the free-tier's 15/min ceiling.
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from pipeline.dataset_loader import load_input_dataset  # noqa: E402
from pipeline.delivery_format import (  # noqa: E402
    DeliveryFormat,
    load_delivery_format,
    load_worked_examples,
)
from pipeline.description_builder import generate_descriptions  # noqa: E402
from pipeline.dishwasher_schema import (  # noqa: E402
    DISHWASHER_ATTRIBUTE_LABELS,
    blank_dishwasher_scaffold,
    build_dishwasher_attribute_slots,
    is_dishwasher,
)
from pipeline.evaluation import EvalResult, derive_zero_evidence_columns, evaluate_row  # noqa: E402
from pipeline.inferred_rules import NOT_BUILT  # noqa: E402
from pipeline.llm_client import LLMClient  # noqa: E402
from pipeline.manufacturer_normalizer import resolve_manufacturer  # noqa: E402
from pipeline.rate_limiter import RateLimitedLLM, RateLimiter  # noqa: E402

OUTPUT_DIR = BACKEND_DIR / "output"
KNOWN_MPNS = {"PDSH4816AF", "WDTS7024RZ"}
INPUT_COLUMNS = ("Mfg_Part_Num", "Part_Desc", "E1_Brand", "Unilog_Brand", "DIB_Brand", "Part_Manuf")


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def section(title: str) -> None:
    print(f"\n-- {title} " + "-" * max(0, 74 - len(title)))


def _source_row(raw_row) -> dict[str, str]:
    return {col: str(raw_row.get(col, "") or "") for col in INPUT_COLUMNS}


def _attribute_and_brand_columns(expected: dict[str, str] | None) -> dict[str, str]:
    """Real attribute values + BRAND_NAME/MANUFACTURER_NAME for a known row,
    the blank scaffold for an unverified one. Same honesty boundary
    description_builder.trusted_fields_for_row() uses for the prompt,
    applied here to the assembled output row."""
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


def assemble_and_score(
    raw_row, expected: dict[str, str] | None, fmt: DeliveryFormat, llm, zero_evidence: frozenset[str]
) -> tuple[dict[str, str], EvalResult, dict[str, list[str]]]:
    mpn, part_desc = raw_row["Mfg_Part_Num"], raw_row["Part_Desc"]
    source = _source_row(raw_row)

    descriptions, violations = generate_descriptions(mpn, part_desc, expected=expected, llm=llm)

    generated = fmt.empty_row()
    generated.update(source)
    generated.update(_attribute_and_brand_columns(expected))
    generated.update(descriptions)

    result = evaluate_row(
        generated,
        expected=expected,  # known rows: enables tier 1 (informational) + correctly
        source_input=source,  # skips the manufacturer honesty check for them
        row_id=mpn,
        fmt=fmt,
        zero_evidence_columns=zero_evidence,
    )
    return generated, result, violations


def run_pipeline(dataset, examples, fmt, llm, zero_evidence):
    rule("1. ASSEMBLE + SCORE — all 10 real dishwasher rows")
    examples_by_mpn = {e["Mfg_Part_Num"]: e for e in examples}
    dishwasher_rows = dataset.frame[dataset.frame["Part_Desc"].map(is_dishwasher)]

    rows_out: list[dict[str, str]] = []
    scores: list[tuple[str, bool, EvalResult, dict[str, list[str]]]] = []

    for _, raw_row in dishwasher_rows.iterrows():
        mpn = raw_row["Mfg_Part_Num"]
        is_known = mpn in KNOWN_MPNS
        expected = examples_by_mpn.get(mpn) if is_known else None

        section(f"{mpn} ({'known' if is_known else 'unverified'})")
        generated, result, violations = assemble_and_score(raw_row, expected, fmt, llm, zero_evidence)
        rows_out.append(generated)
        scores.append((mpn, is_known, result, violations))

        tier1 = result.tier(1)
        tier23 = result.tier(2) + result.tier(3)
        tier23_fail = sum(1 for c in tier23 if c.status == "fail")
        if tier1:
            exact = sum(1 for c in tier1 if c.status == "pass")
            print(f"  tier1 (informational): {exact}/{len(tier1)} fields byte-exact")
        print(f"  tier2/tier3: {sum(1 for c in tier23 if c.status == 'pass')}/{len(tier23)} pass, {tier23_fail} fail")
        for c in tier23:
            if c.status == "fail":
                print(f"      FAIL tier{c.tier} {c.check_id}: {c.reason}")
        if violations:
            print(f"  invented-number violations: {violations}")

        vendor = resolve_manufacturer(_source_row(raw_row))
        print(f"  manufacturer resolution: {vendor.confidence_label}")

    return rows_out, scores


def write_csv(rows_out: list[dict[str, str]], fmt: DeliveryFormat) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = OUTPUT_DIR / "dishwasher_delivery_rows.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fmt.columns)
        writer.writeheader()
        for row in rows_out:
            writer.writerow(row)
    return out_path


def coverage_report(rows_out: list[dict[str, str]], fmt: DeliveryFormat, zero_evidence: frozenset[str]) -> list[str]:
    """Which delivery-format groups got real data across the 10 rows, vs
    zero-evidence columns, vs genuinely NOT_BUILT."""
    lines = ["## Column-group coverage (10 rows)", ""]
    lines.append("| group | columns | populated in >=1 row | zero-evidence columns |")
    lines.append("|---|---|---|---|")
    for name, count, _desc in fmt.summary():
        cols = fmt.group(name).fields
        populated = sum(1 for c in cols if any((r.get(c) or "").strip() for r in rows_out))
        zero_ev = sum(1 for c in cols if c in zero_evidence)
        lines.append(f"| {name} | {count} | {populated} | {zero_ev} |")
    return lines


def write_report(rows_out, scores, fmt, zero_evidence, csv_path: Path) -> Path:
    lines = [
        "# Step 7 — full pipeline report",
        "",
        f"10 real dishwasher rows, 2 with verified ground truth "
        f"({', '.join(sorted(KNOWN_MPNS))}), 8 with only Mfg_Part_Num/Part_Desc.",
        f"Delivery-format CSV: `{csv_path.relative_to(BACKEND_DIR)}`",
        "",
        "## Per-row scores",
        "",
        "| Mfg_Part_Num | known | tier1 (informational) | tier2/tier3 pass | tier2/tier3 fail | invented numbers |",
        "|---|---|---|---|---|---|",
    ]
    total_tier23_fail = 0
    for mpn, is_known, result, violations in scores:
        tier1 = result.tier(1)
        tier1_str = f"{sum(1 for c in tier1 if c.status == 'pass')}/{len(tier1)}" if tier1 else "n/a"
        tier23 = result.tier(2) + result.tier(3)
        p = sum(1 for c in tier23 if c.status == "pass")
        f_ = sum(1 for c in tier23 if c.status == "fail")
        total_tier23_fail += f_
        lines.append(f"| {mpn} | {is_known} | {tier1_str} | {p} | {f_} | {bool(violations)} |")

    lines += ["", f"**Total tier2/tier3 failures across all 10 rows: {total_tier23_fail}**", ""]
    lines += coverage_report(rows_out, fmt, zero_evidence)
    lines += [
        "",
        "## Explicitly out of scope (NOT_BUILT)",
        "",
        "Carried over verbatim from `pipeline/inferred_rules.py` — nothing below",
        "was silently skipped, it was decided against and documented:",
        "",
    ]
    for name, reason in NOT_BUILT:
        lines.append(f"* **{name}** — {reason}")
        lines.append("")

    OUTPUT_DIR.mkdir(exist_ok=True)
    report_path = OUTPUT_DIR / "step7_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def main() -> int:
    if not os.getenv("GEMINI_API_KEY"):
        print("GEMINI_API_KEY is not set. Copy .env.example to .env and add your key.")
        return 1

    fmt = load_delivery_format()
    examples = load_worked_examples()
    dataset = load_input_dataset()
    zero_evidence = derive_zero_evidence_columns(examples, fmt)
    llm = RateLimitedLLM(LLMClient(), RateLimiter())

    rows_out, scores = run_pipeline(dataset, examples, fmt, llm, zero_evidence)

    csv_path = write_csv(rows_out, fmt)
    report_path = write_report(rows_out, scores, fmt, zero_evidence, csv_path)

    total_fail = sum(
        sum(1 for c in (result.tier(2) + result.tier(3)) if c.status == "fail")
        for _, _, result, _ in scores
    )

    rule("STEP 7 COMPLETE")
    print(f"Wrote {csv_path.relative_to(BACKEND_DIR)} ({len(rows_out)} rows, {len(fmt.columns)} columns).")
    print(f"Wrote {report_path.relative_to(BACKEND_DIR)}.")
    print(f"Total tier2/tier3 failures across all 10 rows: {total_fail}.")
    print(
        "Coverage is intentionally partial — 5 description formats + the dishwasher "
        "attribute scaffold + verbatim passthrough are real; everything else is blank "
        "because no module in this codebase builds it yet (see the report's NOT_BUILT "
        "section). A blank column is the honest state, not a bug to hide."
    )
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
