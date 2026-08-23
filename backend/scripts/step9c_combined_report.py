"""
Step 9c runner: combined scale report — one summary of step 9a + step 9b.

    python backend/scripts/step9c_combined_report.py

Re-runs both full-scale passes (manufacturer resolution, UOM/fraction
pattern detection) itself rather than shelling out to step9a/step9b, using
the same pipeline functions those scripts use — resolve_manufacturer(),
cluster_vendor_names(), scan_part_desc(). No new logic beyond aggregating
the two into one report; see step9a_manufacturer_scale.py and
step9b_uom_scale.py for the standalone, more detailed versions of each half.

SELF-TEST before any report is trusted: two hand-verifiable spot checks
against real rows, run first and printed with PASS/FAIL —
  1. Mfg_Part_Num 576355, Part_Desc "576355 60/100/150 Led Med 50k" —
     contains "60/100", a fraction whose denominator (100) doesn't divide
     64, so it must NOT land on the grid. Must report unparsed.
  2. Mfg_Part_Num 37300952, Part_Desc '095842 Fisch Plug Cutter 3/8"' —
     contains "3/8", must parse to exactly 0.375.
If either fails, the script exits non-zero without writing a report.

Written to backend/reports/step9_scale_report.md and .json.
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pipeline.dataset_loader import load_input_dataset  # noqa: E402
from pipeline.desc_pattern_scanner import scan_part_desc  # noqa: E402
from pipeline.manufacturer_normalizer import (  # noqa: E402
    cluster_vendor_names,
    resolve_manufacturer,
)

REPORTS_DIR = BACKEND_DIR / "reports"

SPOT_CHECK_NON_GRID = ("576355", "576355 60/100/150 Led Med 50k", "60/100")
SPOT_CHECK_CLEAN = ("37300952", '095842 Fisch Plug Cutter 3/8"', "3/8", 0.375)


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def section(title: str) -> None:
    print(f"\n-- {title} " + "-" * max(0, 74 - len(title)))


# --------------------------------------------------------------------------
# Self-test — two hand-verifiable real rows, checked before anything else.
# --------------------------------------------------------------------------

def self_test(dataset) -> tuple[bool, list[dict]]:
    rule("SELF-TEST — hand-verifiable spot checks on real rows")
    ok = True
    records: list[dict] = []
    frame = dataset.frame

    section(f"1. non-64th fraction correctly reports as unparsed (Mfg_Part_Num {SPOT_CHECK_NON_GRID[0]})")
    row = frame[frame["Mfg_Part_Num"] == SPOT_CHECK_NON_GRID[0]]
    if row.empty:
        print(f"  FAIL — row {SPOT_CHECK_NON_GRID[0]} not found in dataset")
        ok = False
        records.append({
            "mpn": SPOT_CHECK_NON_GRID[0], "part_desc": None, "primary": None,
            "explanation": f"row {SPOT_CHECK_NON_GRID[0]} not found in dataset", "passed": False,
        })
    else:
        actual_desc = row.iloc[0]["Part_Desc"]
        desc_matches = actual_desc == SPOT_CHECK_NON_GRID[1]
        result = scan_part_desc(actual_desc)
        primary = result.primary
        found_expected_token = bool(primary and primary.raw == SPOT_CHECK_NON_GRID[2])
        correctly_unparsed = bool(primary and primary.kind == "bare_fraction" and not primary.clean)
        passed = desc_matches and found_expected_token and correctly_unparsed
        explanation = (
            "60/100 has denominator 100, and 64 % 100 != 0, so it cannot land on the "
            "1/64 grid — must report unparsed, not a guessed nearest fraction."
        )
        print(f"  Part_Desc: {actual_desc!r}")
        print(f"  primary match: {primary}")
        print(
            f"  {'PASS' if passed else 'FAIL'} — Part_Desc matches expected={desc_matches}, "
            f"primary token='{SPOT_CHECK_NON_GRID[2]}'={found_expected_token}, "
            f"correctly reported unparsed={correctly_unparsed} ({explanation})"
        )
        records.append({
            "mpn": SPOT_CHECK_NON_GRID[0], "part_desc": actual_desc, "primary": primary,
            "explanation": explanation, "passed": passed,
        })
        if not passed:
            ok = False

    section(f"2. '3/8' parses to exactly 0.375 (Mfg_Part_Num {SPOT_CHECK_CLEAN[0]})")
    row = frame[frame["Mfg_Part_Num"] == SPOT_CHECK_CLEAN[0]]
    if row.empty:
        print(f"  FAIL — row {SPOT_CHECK_CLEAN[0]} not found in dataset")
        ok = False
        records.append({
            "mpn": SPOT_CHECK_CLEAN[0], "part_desc": None, "primary": None,
            "explanation": f"row {SPOT_CHECK_CLEAN[0]} not found in dataset", "passed": False,
        })
    else:
        actual_desc = row.iloc[0]["Part_Desc"]
        desc_matches = actual_desc == SPOT_CHECK_CLEAN[1]
        result = scan_part_desc(actual_desc)
        primary = result.primary
        found_expected_token = bool(primary and primary.raw == SPOT_CHECK_CLEAN[2])
        parsed_correctly = bool(
            primary and primary.kind == "bare_fraction" and primary.clean
            and primary.detail == f"decimal={SPOT_CHECK_CLEAN[3]}"
        )
        passed = desc_matches and found_expected_token and parsed_correctly
        explanation = f"3/8 is 24/64 reduced — exactly on the 1/64 grid, decimal value {SPOT_CHECK_CLEAN[3]}."
        print(f"  Part_Desc: {actual_desc!r}")
        print(f"  primary match: {primary}")
        print(
            f"  {'PASS' if passed else 'FAIL'} — Part_Desc matches expected={desc_matches}, "
            f"primary token='{SPOT_CHECK_CLEAN[2]}'={found_expected_token}, "
            f"parsed to {SPOT_CHECK_CLEAN[3]}={parsed_correctly}"
        )
        records.append({
            "mpn": SPOT_CHECK_CLEAN[0], "part_desc": actual_desc, "primary": primary,
            "explanation": explanation, "passed": passed,
        })
        if not passed:
            ok = False

    return ok, records


# --------------------------------------------------------------------------
# 9a half — manufacturer resolution, full scale.
# --------------------------------------------------------------------------

def run_manufacturer_scale(dataset) -> dict:
    status_counts: dict[str, int] = {}
    fabricated = 0

    start = time.perf_counter()
    for _, row in dataset.frame.iterrows():
        resolution = resolve_manufacturer(row.to_dict())
        status_counts[resolution.status] = status_counts.get(resolution.status, 0) + 1
        if resolution.manufacturer_name is not None or resolution.brand_name is not None:
            fabricated += 1
    elapsed = time.perf_counter() - start

    real_names = sorted(dataset.frame["manuf_name"].dropna().unique().tolist())
    clusters = cluster_vendor_names(real_names)

    return {
        "rows_processed": len(dataset.frame),
        "status_counts": status_counts,
        "fabricated_manufacturer_or_brand_values": fabricated,
        "distinct_display_names": len(real_names),
        "distinct_canonical_names": len(clusters),
        "elapsed_sec": elapsed,
        "rows_per_sec": len(dataset.frame) / elapsed if elapsed > 0 else float("inf"),
    }


# --------------------------------------------------------------------------
# 9b half — UOM/fraction pattern detection, full scale.
# --------------------------------------------------------------------------

def run_uom_scale(dataset) -> dict:
    descs = dataset.frame["Part_Desc"].fillna("").tolist()

    start = time.perf_counter()
    results = [scan_part_desc(desc) for desc in descs]
    elapsed = time.perf_counter() - start

    rows_with_pattern = [r for r in results if r.found]
    rows_clean = [r for r in rows_with_pattern if r.clean]
    rows_unparsed = [r for r in rows_with_pattern if not r.clean]
    kind_counts: Counter[str] = Counter(r.primary.kind for r in rows_with_pattern)

    total = len(results)
    return {
        "rows_scanned": total,
        "rows_with_pattern": len(rows_with_pattern),
        "rows_with_pattern_pct": 100 * len(rows_with_pattern) / total if total else 0.0,
        "parsed_cleanly": len(rows_clean),
        "parsed_cleanly_pct": 100 * len(rows_clean) / len(rows_with_pattern) if rows_with_pattern else 0.0,
        "unparsed": len(rows_unparsed),
        "unparsed_pct": 100 * len(rows_unparsed) / len(rows_with_pattern) if rows_with_pattern else 0.0,
        "kind_counts": dict(kind_counts),
        "elapsed_sec": elapsed,
        "rows_per_sec": total / elapsed if elapsed > 0 else float("inf"),
    }


# --------------------------------------------------------------------------
# Report.
# --------------------------------------------------------------------------

HONESTY_SENTENCE = (
    "This demonstrates throughput and internal consistency at full dataset scale. "
    "Field-level accuracy claims remain scoped to the 10 dishwasher rows with "
    "available ground truth."
)


def build_summary(dataset, mfr: dict, uom: dict, spot_checks: list[dict]) -> dict:
    return {
        "rows_processed": len(dataset.frame),
        "manufacturer_resolution": mfr,
        "uom_fraction_patterns": uom,
        "total_elapsed_sec": mfr["elapsed_sec"] + uom["elapsed_sec"],
        "spot_checks": [
            {
                "mpn": r["mpn"],
                "part_desc": r["part_desc"],
                "primary_match": {
                    "raw": r["primary"].raw, "kind": r["primary"].kind,
                    "clean": r["primary"].clean, "detail": r["primary"].detail,
                } if r["primary"] else None,
                "explanation": r["explanation"],
                "passed": r["passed"],
            }
            for r in spot_checks
        ],
        "honesty_statement": HONESTY_SENTENCE,
    }


def write_reports(summary: dict) -> tuple[Path, Path]:
    mfr = summary["manufacturer_resolution"]
    uom = summary["uom_fraction_patterns"]
    spot_checks = summary["spot_checks"]

    lines = [
        "# Step 9 — combined scale report",
        "",
        f"**{HONESTY_SENTENCE}**",
        "",
        f"Total rows processed: **{summary['rows_processed']}**. "
        f"Combined processing time: **{summary['total_elapsed_sec']:.4f}s** "
        f"(manufacturer resolution {mfr['elapsed_sec']:.4f}s + "
        f"UOM/fraction scan {uom['elapsed_sec']:.4f}s).",
        "",
        "## Spot check",
        "",
        "Two hand-verifiable checks against real rows, run as a self-test before "
        "this report is generated — if either fails, no report gets written. "
        "Included here so this report is self-contained proof, not a claim that "
        "requires re-running the script to verify.",
        "",
    ]
    for r in spot_checks:
        status = "PASS" if r["passed"] else "FAIL"
        lines.append(f"**{status}** — `Mfg_Part_Num {r['mpn']}`, `Part_Desc {r['part_desc']!r}`")
        pm = r["primary_match"]
        if pm:
            lines.append(
                f"- primary match: `{pm['raw']}` ({pm['kind']}, "
                f"{'clean' if pm['clean'] else 'unparsed'}) — {pm['detail']}"
            )
        lines.append(f"- {r['explanation']}")
        lines.append("")
    lines += [
        "## Part A — manufacturer/brand honesty layer",
        "",
        f"- rows processed: {mfr['rows_processed']}",
    ]
    for status, count in sorted(mfr["status_counts"].items()):
        lines.append(f"- `{status}`: {count} rows")
    lines += [
        f"- distinct Part_Manuf display names: {mfr['distinct_display_names']}",
        f"- distinct canonical vendor names after clustering: {mfr['distinct_canonical_names']}",
        f"- fabricated MANUFACTURER_NAME/BRAND_NAME values: {mfr['fabricated_manufacturer_or_brand_values']} "
        f"({'confirmed zero' if mfr['fabricated_manufacturer_or_brand_values'] == 0 else 'VIOLATION'})",
        f"- timing: {mfr['elapsed_sec']:.4f}s ({mfr['rows_per_sec']:,.0f} rows/sec)",
        "",
        "See `backend/reports/step9a_report.md` for the standalone, more detailed version.",
        "",
        "## Part B — UOM/fraction pattern detection",
        "",
        f"- rows scanned: {uom['rows_scanned']}",
        f"- rows with a pattern found: {uom['rows_with_pattern']} ({uom['rows_with_pattern_pct']:.1f}%)",
        f"- of those, parsed cleanly: {uom['parsed_cleanly']} ({uom['parsed_cleanly_pct']:.1f}%)",
        f"- of those, unparsed: {uom['unparsed']} ({uom['unparsed_pct']:.1f}%)",
        f"- timing: {uom['elapsed_sec']:.4f}s ({uom['rows_per_sec']:,.0f} rows/sec)",
        "",
        "Primary match kind, rows with a pattern found:",
        "",
    ]
    for kind, count in sorted(uom["kind_counts"].items(), key=lambda kv: -kv[1]):
        lines.append(f"- `{kind}`: {count} rows")
    lines += [
        "",
        "See `backend/reports/step9b_report.md` for the standalone, more detailed "
        "version, including sample rows and known false-positive/false-negative caveats.",
        "",
        "## Scope",
        "",
        "Neither part touches `dishwasher_schema.py`, `description_builder.py`, or "
        "`run_dishwasher_pipeline.py` — those stay scoped to the 10 dishwasher rows "
        "exactly as before. This report is additive.",
        "",
    ]

    REPORTS_DIR.mkdir(exist_ok=True)
    md_path = REPORTS_DIR / "step9_scale_report.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")

    json_path = REPORTS_DIR / "step9_scale_report.json"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return md_path, json_path


def main() -> int:
    dataset = load_input_dataset()

    self_test_ok, spot_checks = self_test(dataset)
    if not self_test_ok:
        rule("SELF-TEST FAILED")
        print("At least one spot check failed above. Refusing to write a report on top of it.")
        return 1

    rule("PART A — manufacturer resolution, full 1000 rows")
    mfr = run_manufacturer_scale(dataset)
    section("summary")
    print(f"  {mfr['rows_processed']} rows in {mfr['elapsed_sec']:.4f}s ({mfr['rows_per_sec']:,.0f} rows/sec)")
    for status, count in sorted(mfr["status_counts"].items()):
        print(f"  {status:<20} {count:>4} rows")
    print(f"  distinct canonical vendor names: {mfr['distinct_canonical_names']}")
    print(f"  fabricated MANUFACTURER_NAME/BRAND_NAME values: {mfr['fabricated_manufacturer_or_brand_values']}")

    rule("PART B — UOM/fraction pattern detection, full 1000 rows")
    uom = run_uom_scale(dataset)
    section("summary")
    print(f"  {uom['rows_scanned']} rows in {uom['elapsed_sec']:.4f}s ({uom['rows_per_sec']:,.0f} rows/sec)")
    print(f"  pattern found: {uom['rows_with_pattern']} ({uom['rows_with_pattern_pct']:.1f}%)")
    print(f"  parsed cleanly: {uom['parsed_cleanly']} ({uom['parsed_cleanly_pct']:.1f}%)")
    print(f"  unparsed: {uom['unparsed']} ({uom['unparsed_pct']:.1f}%)")

    summary = build_summary(dataset, mfr, uom, spot_checks)
    md_path, json_path = write_reports(summary)

    rule("REPORT")
    print(f"Written to {md_path.relative_to(BACKEND_DIR)} and {json_path.relative_to(BACKEND_DIR)}")
    print(md_path.read_text(encoding="utf-8"))

    rule("STEP 9 COMPLETE")
    print(HONESTY_SENTENCE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
