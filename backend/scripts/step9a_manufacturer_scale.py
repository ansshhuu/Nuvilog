"""
Step 9a runner: manufacturer/brand honesty layer at full scale.

    python backend/scripts/step9a_manufacturer_scale.py

Does NOT require ground truth to run — resolve_manufacturer() and
cluster_vendor_names() only read the raw Part_Manuf column, they never
compare against expected MANUFACTURER_NAME/BRAND_NAME. This is the same
finding step4_manufacturer.py already made on all 1000 rows during its
investigation (the 959/41 vendor_code_present/no_vendor_data split); this
script re-runs it formally as a standalone, timed pass and writes a report.

THIS IS NOT AN ACCURACY REPORT. It reports throughput and internal
consistency (rows processed, status counts, distinct canonical vendor
names, timing) — never a comparison against a known-correct answer,
because no ground truth exists for 998/1000 of these rows. Don't add
anything here that implies otherwise.

Does not touch dishwasher_schema.py, description_builder.py, or
run_dishwasher_pipeline.py — those stay scoped to the 10 dishwasher rows.

Written to backend/reports/step9a_report.md and printed to the console.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pipeline.dataset_loader import load_input_dataset  # noqa: E402
from pipeline.manufacturer_normalizer import (  # noqa: E402
    cluster_vendor_names,
    resolve_manufacturer,
)

REPORTS_DIR = BACKEND_DIR / "reports"


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def section(title: str) -> None:
    print(f"\n-- {title} " + "-" * max(0, 74 - len(title)))


def run_full_scale(dataset) -> dict:
    rule("STEP 9A — manufacturer/brand honesty layer, full 1000 rows")

    status_counts: dict[str, int] = {}
    fabricated_values: list[str] = []

    start = time.perf_counter()
    resolutions = []
    for _, row in dataset.frame.iterrows():
        resolution = resolve_manufacturer(row.to_dict())
        resolutions.append(resolution)
        status_counts[resolution.status] = status_counts.get(resolution.status, 0) + 1
        # manufacturer_name/brand_name are properties hardcoded to None on
        # every ManufacturerResolution — this loop just proves that
        # structural guarantee holds for this run's actual objects too,
        # rather than trusting the property definition alone.
        if resolution.manufacturer_name is not None or resolution.brand_name is not None:
            fabricated_values.append(resolution.mfg_part_num)
    elapsed = time.perf_counter() - start

    section("status breakdown, all 1000 rows")
    for status, count in sorted(status_counts.items()):
        print(f"  {status:<20} {count:>4} rows")

    section("fabrication guarantee")
    zero_fabricated = len(fabricated_values) == 0
    print(
        f"  {'PASS' if zero_fabricated else 'FAIL'} — 0 rows produced a non-None "
        f"MANUFACTURER_NAME/BRAND_NAME ({len(fabricated_values)} found)"
    )

    real_names = sorted(dataset.frame["manuf_name"].dropna().unique().tolist())
    clusters = cluster_vendor_names(real_names)
    merged = [c for c in clusters if not c.is_singleton]

    section("vendor-name clustering, full run")
    print(f"  {len(real_names)} distinct Part_Manuf display names before clustering")
    print(f"  {len(clusters)} distinct canonical vendor names after clustering")
    print(f"  {len(merged)} groups merged 2+ names")

    section("timing")
    rows_per_sec = len(dataset.frame) / elapsed if elapsed > 0 else float("inf")
    print(f"  {len(dataset.frame)} rows in {elapsed:.4f}s ({rows_per_sec:,.0f} rows/sec)")

    return {
        "rows_processed": len(dataset.frame),
        "status_counts": status_counts,
        "zero_fabricated": zero_fabricated,
        "distinct_display_names": len(real_names),
        "distinct_canonical_names": len(clusters),
        "merged_groups": len(merged),
        "elapsed_sec": elapsed,
        "rows_per_sec": rows_per_sec,
    }


def write_report(stats: dict) -> Path:
    lines = [
        "# Step 9a — manufacturer/brand honesty layer, full-scale report",
        "",
        "**Not an accuracy report.** This module never compares its output against "
        "a known-correct MANUFACTURER_NAME/BRAND_NAME, because ground truth exists "
        "for only 2/1000 rows. What follows is throughput and internal consistency "
        "at real scale: how many rows resolved to which status, how the vendor-name "
        "vocabulary clusters, and how fast it runs. See `pipeline/manufacturer_normalizer.py` "
        "and `backend/scripts/step4_manufacturer.py` for why this module deliberately "
        "never emits MANUFACTURER_NAME/BRAND_NAME.",
        "",
        "## Run stats",
        "",
        f"- rows processed: {stats['rows_processed']}",
    ]
    for status, count in sorted(stats["status_counts"].items()):
        lines.append(f"- `{status}`: {count} rows")
    lines += [
        f"- distinct Part_Manuf display names: {stats['distinct_display_names']}",
        f"- distinct canonical vendor names after clustering: {stats['distinct_canonical_names']}",
        f"- clustering groups merged (2+ names -> 1 canonical): {stats['merged_groups']}",
        f"- fabricated MANUFACTURER_NAME/BRAND_NAME values: 0 "
        f"({'confirmed' if stats['zero_fabricated'] else 'VIOLATION — see console output'}) "
        "— structural guarantee, `ManufacturerResolution.manufacturer_name`/`.brand_name` "
        "are hardcoded `None` properties, checked here on every one of this run's objects",
        f"- timing: {stats['elapsed_sec']:.4f}s for {stats['rows_processed']} rows "
        f"({stats['rows_per_sec']:,.0f} rows/sec)",
        "",
    ]
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / "step9a_report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> int:
    dataset = load_input_dataset()
    stats = run_full_scale(dataset)

    if not stats["zero_fabricated"]:
        rule("STEP 9A FAILED")
        print("Fabrication guarantee violated. Do not trust the report below.")
        return 1

    report_path = write_report(stats)

    rule("REPORT")
    print(f"Written to {report_path.relative_to(BACKEND_DIR)}")
    print(report_path.read_text(encoding="utf-8"))

    rule("STEP 9A COMPLETE")
    print(
        f"{stats['rows_processed']} rows processed in {stats['elapsed_sec']:.4f}s "
        f"({stats['rows_per_sec']:,.0f} rows/sec). "
        f"{stats['status_counts'].get('vendor_code_present', 0)} vendor_code_present / "
        f"{stats['status_counts'].get('no_vendor_data', 0)} no_vendor_data, "
        f"{stats['distinct_canonical_names']} distinct canonical vendor names, "
        "0 fabricated MANUFACTURER_NAME/BRAND_NAME values. Throughput and internal "
        "consistency only — not an accuracy claim."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
