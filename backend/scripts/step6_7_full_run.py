"""
Step 6/7 Section C: full run of run_dishwasher_pipeline.process_row() over
all 10 real dishwasher rows, scored, and written to one clean report.

    python backend/scripts/step6_7_full_run.py

ORDER, AND WHY

  1. STRUCTURAL SELF-TEST (no LLM call) — the honesty guarantee
     process_row() is built on is provable without spending an API call:
     stage 3 (resolve_manufacturer) never returns a manufacturer_name/
     brand_name, and stage 4 (blank_dishwasher_scaffold) never returns a
     non-empty ATTRIBUTE_VALUE. Prove both directly before trusting
     anything downstream.

  2. LIVE SELF-TEST (1 LLM call) — run process_row() itself on one row and
     confirm the assembled output actually has MANUFACTURER_NAME,
     BRAND_NAME and every ATTRIBUTE_VALUE blank, and that evaluate_row()
     reports zero tier-3 honesty violations against it. This is the same
     "prove the harness isn't lying before trusting a summary" discipline
     every prior step script uses (step2, step5, step6).

  3. FULL RUN (10 LLM calls, rate-limited) — process_row() on all 10 real
     dishwasher rows.
       * PDSH4816AF, WDTS7024RZ (known): evaluate_row() with expected= the
         real worked-example row, all 3 tiers.
       * the other 8: evaluate_row() with expected=None — tier 1 does not
         run (there is nothing to compare against), tier 2 + tier 3 do.

  4. REPORT — one summary: rows processed, aggregate tier2/tier3
     rule-compliance rate, a tier-3 honesty-violation count (this is the
     one number in this whole file that MUST be zero — the script exits
     non-zero and prints every violation in full if it isn't, rather than
     folding it into an aggregate percentage where it could hide), and for
     the 2 known rows only, a length/structure comparison against the real
     descriptions (process_row() is not expected to match them — see
     run_dishwasher_pipeline.py's docstring on why — this table shows
     exactly how far off, not whether it "passed").

  Written to backend/reports/step6_7_report.md, and printed to the
  console in full either way.
"""
from __future__ import annotations

import json
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
from pipeline.description_builder import DESCRIPTION_FIELDS  # noqa: E402
from pipeline.dishwasher_schema import blank_dishwasher_scaffold, is_dishwasher  # noqa: E402
from pipeline.evaluation import EvalResult, derive_zero_evidence_columns, evaluate_row  # noqa: E402
from pipeline.llm_client import LLMClient  # noqa: E402
from pipeline.manufacturer_normalizer import resolve_manufacturer  # noqa: E402
from pipeline.rate_limiter import RateLimitedLLM, RateLimiter  # noqa: E402
from pipeline.run_dishwasher_pipeline import RAW_INPUT_COLUMNS, process_row  # noqa: E402

KNOWN_MPNS = {"PDSH4816AF", "WDTS7024RZ"}
REPORTS_DIR = BACKEND_DIR / "reports"


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def section(title: str) -> None:
    print(f"\n-- {title} " + "-" * max(0, 74 - len(title)))


# --------------------------------------------------------------------------
# 1. Structural self-test — no LLM call.
# --------------------------------------------------------------------------

def structural_self_test() -> bool:
    rule("1. STRUCTURAL SELF-TEST — no LLM call")
    ok = True

    section("stage 3 (manufacturer resolve) never emits a name/brand")
    sample_input = {
        "Mfg_Part_Num": "PDSH4816AF",
        "Part_Desc": "PDSH4816AF Dishwasher SS - Display Only",
        "E1_Brand": "-- Unbranded --",
        "Unilog_Brand": "-- No Unilog Brand --",
        "DIB_Brand": "-- No DIB Brand --",
        "Part_Manuf": "Appliance Dealers Cooperative (APPDE)",
    }
    resolution = resolve_manufacturer(sample_input)
    passed = resolution.manufacturer_name is None and resolution.brand_name is None
    print(f"  {'PASS' if passed else 'FAIL'} — manufacturer_name={resolution.manufacturer_name!r} "
          f"brand_name={resolution.brand_name!r} (status={resolution.status})")
    ok = ok and passed

    section("stage 4 (dishwasher scaffold) never emits an ATTRIBUTE_VALUE")
    blank = blank_dishwasher_scaffold()
    non_blank_values = [k for k, v in blank.items() if k.startswith("ATTRIBUTE_VALUE") and v]
    passed = not non_blank_values
    print(f"  {'PASS' if passed else 'FAIL'} — non-blank ATTRIBUTE_VALUE keys: {non_blank_values}")
    ok = ok and passed

    section("dishwasher detection matches all 10 known dishwasher rows")
    dataset = load_input_dataset()
    dishwasher_rows = dataset.frame[dataset.frame["Part_Desc"].map(is_dishwasher)]
    passed = len(dishwasher_rows) == 10
    print(f"  {'PASS' if passed else 'FAIL'} — {len(dishwasher_rows)} rows matched (expected 10)")
    ok = ok and passed

    return ok


# --------------------------------------------------------------------------
# 2. Live self-test — 1 LLM call.
# --------------------------------------------------------------------------

def live_self_test(fmt, zero_evidence, llm) -> bool:
    rule("2. LIVE SELF-TEST — process_row() on 1 real row, 1 LLM call")
    ok = True

    dataset = load_input_dataset()
    raw = dataset.frame[dataset.frame["Mfg_Part_Num"] == "PDSH4816AF"].iloc[0]
    input_row = {c: raw[c] for c in RAW_INPUT_COLUMNS}

    generated = process_row(input_row, llm=llm, fmt=fmt)

    section("output never carries MANUFACTURER_NAME/BRAND_NAME/attribute values")
    leaked = [f for f in ("MANUFACTURER_NAME", "BRAND_NAME") if generated.get(f, "").strip()]
    leaked += [
        f"ATTRIBUTE_VALUE {i}" for i in range(1, 51) if generated.get(f"ATTRIBUTE_VALUE {i}", "").strip()
    ]
    passed = not leaked
    print(f"  {'PASS' if passed else 'FAIL'} — leaked fields: {leaked}")
    ok = ok and passed

    section("evaluate_row() reports zero tier-3 honesty violations")
    result = evaluate_row(
        generated,
        expected=None,
        source_input=input_row,
        row_id="self-test-live",
        fmt=fmt,
        zero_evidence_columns=zero_evidence,
    )
    tier3_fails = [c for c in result.tier(3) if c.status == "fail"]
    passed = not tier3_fails
    print(f"  {'PASS' if passed else 'FAIL'} — {len(tier3_fails)} tier-3 failure(s)")
    for c in tier3_fails:
        print(f"      {c.check_id}: {c.reason}")
    ok = ok and passed

    return ok


# --------------------------------------------------------------------------
# 3. Full run.
# --------------------------------------------------------------------------

def _length_structure_row(field: str, real: str, generated: str) -> dict[str, object]:
    return {
        "field": field,
        "real_len": len(real),
        "generated_len": len(generated),
        "len_delta": len(generated) - len(real),
        "generated_nonempty": bool(generated.strip()),
    }


def full_run(fmt, examples, zero_evidence, llm):
    rule("3. FULL RUN — process_row() over all 10 dishwasher rows")
    examples_by_mpn = {e["Mfg_Part_Num"]: e for e in examples}
    dataset = load_input_dataset()
    dishwasher_rows = dataset.frame[dataset.frame["Part_Desc"].map(is_dishwasher)]

    per_row: list[dict] = []
    for _, raw in dishwasher_rows.iterrows():
        mpn = raw["Mfg_Part_Num"]
        is_known = mpn in KNOWN_MPNS
        input_row = {c: raw[c] for c in RAW_INPUT_COLUMNS}

        section(f"{mpn} ({'known' if is_known else 'unverified'})")
        generated = process_row(input_row, llm=llm, fmt=fmt)

        expected = examples_by_mpn.get(mpn) if is_known else None
        result = evaluate_row(
            generated,
            expected=expected,
            source_input=input_row,
            row_id=mpn,
            fmt=fmt,
            zero_evidence_columns=zero_evidence,
        )

        tier1 = result.tier(1)
        tier2 = result.tier(2)
        tier3 = result.tier(3)
        if tier1:
            exact = sum(1 for c in tier1 if c.status == "pass")
            print(f"  tier1 (exact match, real ground truth): {exact}/{len(tier1)} fields")
        else:
            print("  tier1: not applicable (no known answer for this row)")
        print(f"  tier2 (rule compliance): {sum(1 for c in tier2 if c.status == 'pass')}/{len(tier2)} pass")
        print(f"  tier3 (honesty):         {sum(1 for c in tier3 if c.status == 'pass')}/{len(tier3)} pass")
        for c in tier2 + tier3:
            if c.status == "fail":
                print(f"      FAIL tier{c.tier} {c.check_id}: {c.reason}")

        length_structure = None
        if is_known:
            length_structure = [
                _length_structure_row(f, expected.get(f, ""), generated.get(f, ""))
                for f in DESCRIPTION_FIELDS
            ]
            section(f"{mpn} description length/structure vs real")
            for row in length_structure:
                print(
                    f"    {row['field']:<24} real={row['real_len']:>4}  generated={row['generated_len']:>4}"
                    f"  delta={row['len_delta']:>+5}  nonempty={row['generated_nonempty']}"
                )

        per_row.append(
            {
                "mpn": mpn,
                "is_known": is_known,
                "result": result,
                "length_structure": length_structure,
            }
        )

    return per_row


# --------------------------------------------------------------------------
# 4. Report.
# --------------------------------------------------------------------------

def build_report(per_row: list[dict]) -> tuple[str, bool]:
    total_tier23 = 0
    pass_tier23 = 0
    tier3_violations: list[tuple[str, str, str]] = []  # (mpn, check_id, reason)

    lines = [
        "# Step 6/7 — full pipeline run report",
        "",
        f"`run_dishwasher_pipeline.process_row()` run over all {len(per_row)} real dishwasher rows.",
        "process_row() never receives ground truth for any row — see that module's docstring.",
        "",
        "## Per-row tier summary",
        "",
        "| Mfg_Part_Num | known | tier1 (informational) | tier2 pass | tier3 pass | tier3 violations |",
        "|---|---|---|---|---|---|",
    ]

    for entry in per_row:
        mpn, is_known, result = entry["mpn"], entry["is_known"], entry["result"]
        tier1 = result.tier(1)
        tier2 = result.tier(2)
        tier3 = result.tier(3)
        tier1_str = f"{sum(1 for c in tier1 if c.status == 'pass')}/{len(tier1)}" if tier1 else "n/a"

        row_tier3_fails = [c for c in tier3 if c.status == "fail"]
        for c in row_tier3_fails:
            tier3_violations.append((mpn, c.check_id, c.reason))

        total_tier23 += len(tier2) + len(tier3)
        pass_tier23 += sum(1 for c in tier2 + tier3 if c.status == "pass")

        lines.append(
            f"| {mpn} | {is_known} | {tier1_str} | "
            f"{sum(1 for c in tier2 if c.status == 'pass')}/{len(tier2)} | "
            f"{sum(1 for c in tier3 if c.status == 'pass')}/{len(tier3)} | "
            f"{len(row_tier3_fails)} |"
        )

    compliance_rate = pass_tier23 / total_tier23 if total_tier23 else 0.0
    lines += [
        "",
        f"**Rows processed:** {len(per_row)}",
        f"**Aggregate tier2+tier3 rule-compliance rate:** {pass_tier23}/{total_tier23} ({compliance_rate:.1%})",
        f"**Tier-3 honesty-check violations:** {len(tier3_violations)} "
        f"{'— MUST be 0, see below' if tier3_violations else '(expected: 0)'}",
        "",
    ]

    if tier3_violations:
        lines += ["## HONESTY-CHECK VIOLATIONS (not hidden in the aggregate above)", ""]
        for mpn, check_id, reason in tier3_violations:
            lines.append(f"* **{mpn}** `{check_id}`: {reason}")
        lines.append("")

    lines += ["## Known-row description length/structure vs real", ""]
    for entry in per_row:
        if not entry["is_known"]:
            continue
        lines.append(f"### {entry['mpn']}")
        lines.append("")
        lines.append("| field | real len | generated len | delta | generated nonempty |")
        lines.append("|---|---|---|---|---|")
        for row in entry["length_structure"]:
            lines.append(
                f"| {row['field']} | {row['real_len']} | {row['generated_len']} | "
                f"{row['len_delta']:+d} | {row['generated_nonempty']} |"
            )
        lines.append("")
        lines.append(
            "process_row() has no external-lookup stage, so for a known row it only ever sees "
            "Mfg_Part_Num/Part_Desc — same as the 8 unverified rows. The gaps above are exactly "
            "what external lookup would need to close, not a generation-quality problem."
        )
        lines.append("")

    return "\n".join(lines), not tier3_violations


def main() -> int:
    if not os.getenv("GEMINI_API_KEY"):
        print("GEMINI_API_KEY is not set. Copy .env.example to .env and add your key.")
        return 1

    fmt = load_delivery_format()
    examples = load_worked_examples()
    zero_evidence = derive_zero_evidence_columns(examples, fmt)

    if not structural_self_test():
        rule("STRUCTURAL SELF-TEST FAILED")
        print("Refusing to spend LLM calls on a pipeline that failed its own structural guarantees.")
        return 1

    llm = RateLimitedLLM(LLMClient(), RateLimiter())

    if not live_self_test(fmt, zero_evidence, llm):
        rule("LIVE SELF-TEST FAILED")
        print("Refusing to run the full 10-row pass — fix process_row() before spending more calls.")
        return 1

    per_row = full_run(fmt, examples, zero_evidence, llm)

    report_md, honesty_clean = build_report(per_row)
    REPORTS_DIR.mkdir(exist_ok=True)
    report_path = REPORTS_DIR / "step6_7_report.md"
    report_path.write_text(report_md, encoding="utf-8")

    json_path = REPORTS_DIR / "step6_7_report.json"
    json_path.write_text(
        json.dumps(
            [
                {
                    "mpn": e["mpn"],
                    "is_known": e["is_known"],
                    "counts": e["result"].counts(),
                    "tier3_failures": [
                        {"check_id": c.check_id, "reason": c.reason}
                        for c in e["result"].tier(3)
                        if c.status == "fail"
                    ],
                }
                for e in per_row
            ],
            indent=2,
        ),
        encoding="utf-8",
    )

    rule("4. REPORT")
    print(report_md)
    print(f"\nWritten to {report_path.relative_to(BACKEND_DIR)} and {json_path.relative_to(BACKEND_DIR)}")

    rule("STEP 6/7 COMPLETE" if honesty_clean else "STEP 6/7 — HONESTY VIOLATIONS FOUND, NOT COMPLETE")
    return 0 if honesty_clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
