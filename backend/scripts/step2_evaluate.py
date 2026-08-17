"""
Step 2 runner: prove the evaluation harness works, then run it.

    python backend/scripts/step2_evaluate.py

Order matters here and is deliberate:

  1. SELF-TEST — before any score from this harness is trusted, it has to
     prove it isn't lying in either direction:
       (a) a "generated" row that is a byte-for-byte copy of a known answer
           must score 100% clean (0 fails, 0 honesty violations)
       (b) a row deliberately broken in 3 independent ways (an oversized
           INVOICE_DESC, a fabricated UNSPSC code, a missing required field)
           must be caught on all 3
     If either self-test fails, the script exits non-zero and prints why —
     it will not go on to print a summary table from a harness that just
     proved it can't be trusted.

  2. TIER 1 against both known example rows, using the harness in the
     direction it's designed for.

  3. TIER 2 + TIER 3 against a handful of the other 998 input rows. There is
     no generator built yet (see backend/pipeline/evaluation.py — nothing in
     this repo produces a 252-column row from a 6-column input row). This
     script does not fabricate generated output to fill that gap; it prints
     the stub point instead. Faking "generated" rows here would make the
     harness look tested against real output when it wasn't.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from pipeline.dataset_loader import load_input_dataset  # noqa: E402
from pipeline.delivery_format import load_delivery_format, load_worked_examples  # noqa: E402
from pipeline.evaluation import (  # noqa: E402
    EvalResult,
    derive_zero_evidence_columns,
    evaluate_row,
)


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def section(title: str) -> None:
    print(f"\n-- {title} " + "-" * max(0, 74 - len(title)))


def _passthrough_source(expected_row: dict[str, str]) -> dict[str, str]:
    """Reconstruct the source input row from an expected row's own passthrough columns."""
    return {
        col: expected_row.get(col, "")
        for col in ("Mfg_Part_Num", "Part_Desc", "E1_Brand", "Unilog_Brand", "DIB_Brand", "Part_Manuf")
    }


def self_test(examples: list[dict[str, str]], fmt) -> bool:
    rule("0. HARNESS SELF-TEST")
    ok = True

    # --- (a) a perfect copy must score 100% ---
    section("(a) known-good copy must score clean")
    example = examples[0]
    generated = copy.deepcopy(example)
    source = _passthrough_source(example)
    result = evaluate_row(generated, expected=example, source_input=source, row_id="self-test-perfect-copy")

    counts = result.counts()
    print(f"row_id={result.row_id}  counts={counts}")
    if result.failures:
        ok = False
        print("FAIL — a byte-identical copy of a known row produced failures. Harness bug.")
        for c in result.failures[:10]:
            print(f"    tier{c.tier} {c.check_id}: {c.reason} (expected={c.expected!r} actual={c.actual!r})")
    else:
        print("PASS — 0 failures, 0 honesty violations, as expected.")

    # --- (b) a deliberately broken row must be caught on every break ---
    section("(b) deliberately broken row must be caught")
    broken = copy.deepcopy(example)
    zero_evidence_cols = derive_zero_evidence_columns(examples, fmt)
    fabricated_col = "UNSPSC" if "UNSPSC" in zero_evidence_cols else next(iter(zero_evidence_cols))

    broken["INVOICE_DESC"] = "X" * 60  # break 1: exceeds the 40-char rule
    broken[fabricated_col] = "43211500"  # break 2: fabricated zero-evidence field
    broken["Mfg_Part_Num"] = ""  # break 3: required passthrough field dropped

    result = evaluate_row(broken, expected=example, source_input=source, row_id="self-test-broken-row")
    counts = result.counts()
    print(f"row_id={result.row_id}  counts={counts}")

    caught = {
        "invoice_length": any(
            c.check_id == "invoice_desc.max_len_40" and c.status == "fail" for c in result.tier(2)
        ),
        "invoice_tier1_mismatch": any(
            c.check_id == "INVOICE_DESC" and c.status == "fail" for c in result.tier(1)
        ),
        "fabricated_zero_evidence_field": any(
            c.check_id == fabricated_col and c.status == "fail" for c in result.tier(3)
        ),
        "missing_required_field": any(
            c.check_id == "required:Mfg_Part_Num" and c.status == "fail" for c in result.tier(3)
        ),
    }
    for name, was_caught in caught.items():
        print(f"  {'caught' if was_caught else 'MISSED':<8} {name}")
    if not all(caught.values()):
        ok = False
        print("FAIL — the harness missed at least one deliberately introduced defect.")
    else:
        print("PASS — all 3 introduced defects were caught.")

    return ok


def print_result_table(result: EvalResult) -> None:
    counts = result.counts()
    print(
        f"  {result.row_id:<20} tier1={_tier_summary(result, 1):<14} "
        f"tier2={_tier_summary(result, 2):<14} tier3={_tier_summary(result, 3):<14} "
        f"overall={'PASS' if result.passed else 'FAIL'}"
    )
    if counts["fail"]:
        for c in result.failures:
            print(f"      FAIL  tier{c.tier} {c.check_id}: {c.reason}")
    if counts["warn"]:
        for c in result.warnings:
            print(f"      warn  tier{c.tier} {c.check_id}: {c.reason}")


def _tier_summary(result: EvalResult, n: int) -> str:
    checks = result.tier(n)
    if not checks:
        return "n/a"
    passed = sum(1 for c in checks if c.status == "pass")
    return f"{passed}/{len(checks)} pass"


def run_tier1_on_known_rows(examples: list[dict[str, str]], fmt) -> None:
    rule("1. TIER 1 — EXACT MATCH AGAINST THE 2 KNOWN ROWS")
    print(
        "No generator exists yet, so 'generated' here is the known row copied verbatim —\n"
        "this proves tier 1 wiring end-to-end. It is NOT a claim that generation works."
    )
    for i, example in enumerate(examples):
        generated = copy.deepcopy(example)
        source = _passthrough_source(example)
        result = evaluate_row(generated, expected=example, source_input=source, row_id=f"known-row-{i}")
        print_result_table(result)


def run_tier2_tier3_stub(dataset, fmt) -> None:
    rule("2. TIER 2 + TIER 3 — AGAINST A SAMPLE OF THE OTHER 998 INPUT ROWS")
    sample = dataset.frame.head(5)
    print("Sample input rows this would run against once a generator exists:")
    for _, row in sample.iterrows():
        print(f"  {row['Mfg_Part_Num']:<20} {row['Part_Desc']}")

    print(
        "\nSTUB — no generator is built yet (nothing in this repo turns a 6-column\n"
        "input row into a 252-column delivery row). Rather than fabricate 'generated'\n"
        "output to exercise this path, wire it up here once generation exists:\n\n"
        "    from pipeline.evaluation import evaluate_row\n"
        "    generated_row = generate(source_input_row)   # <- does not exist yet\n"
        "    result = evaluate_row(generated_row, expected=None, source_input=source_input_row)\n\n"
        "Tier 1 is skipped for these rows on purpose (expected=None) — none of the 998\n"
        "rows has a known-correct answer. Tier 2 (rule compliance) and Tier 3 (honesty)\n"
        "both run on any generated row regardless of whether ground truth exists, which\n"
        "is exactly why they're the tiers usable at scale here."
    )


def main() -> int:
    fmt = load_delivery_format()
    examples = load_worked_examples()
    dataset = load_input_dataset()

    if not self_test(examples, fmt):
        rule("SELF-TEST FAILED")
        print("Refusing to print a summary from a harness that failed its own self-test.")
        return 1

    run_tier1_on_known_rows(examples, fmt)
    run_tier2_tier3_stub(dataset, fmt)

    rule("STEP 2 COMPLETE")
    print(
        "Harness self-tested clean. evaluate_row()/evaluate_rows() in\n"
        "backend/pipeline/evaluation.py are ready to score real generated output\n"
        "the moment a generator exists — no changes needed to this harness."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
