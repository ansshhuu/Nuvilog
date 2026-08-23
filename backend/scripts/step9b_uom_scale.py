"""
Step 9b runner: UOM/fraction pattern detection across Part_Desc, full 1000 rows.

    python backend/scripts/step9b_uom_scale.py

This is the genuinely new piece of step 9: Part_Desc is free text, not
structured ATTRIBUTE_VALUE/UOM columns (those don't exist for 998/1000
rows — no extraction has run on them). desc_pattern_scanner.py scans the
raw text for numeric+fraction+unit-shaped tokens and runs each one through
the ALREADY-BUILT fraction_converter/uom_normalizer functions — no new
conversion logic here, just a new place to look for the input.

NOT AN ACCURACY REPORT — same discipline as step9a. There is no ground
truth for what "the" measurement in a free-text description is, so this
can't be scored against a right answer. What it reports is: how many rows
have a pattern-shaped token at all, and of those, how many parsed cleanly
(fraction on the 1/64 grid, unit recognized by uom_normalizer) vs how many
hit something unparseable. A low clean-parse rate is not a bug in this
scanner — it's a real finding about how messy free-text descriptions are
relative to the 64ths grid / confirmed UOM set, and is reported as such,
not smoothed over. Unparseable patterns are never fixed or guessed at;
they're counted and left alone.

Does not touch dishwasher_schema.py, description_builder.py, or
run_dishwasher_pipeline.py — those stay scoped to the 10 dishwasher rows.

Written to backend/reports/step9b_report.md and printed to the console.
"""
from __future__ import annotations

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

REPORTS_DIR = BACKEND_DIR / "reports"
EXAMPLE_COUNT = 8


def rule(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def section(title: str) -> None:
    print(f"\n-- {title} " + "-" * max(0, 74 - len(title)))


def run_full_scale(dataset) -> dict:
    rule("STEP 9B — UOM/fraction pattern detection, full 1000 rows")

    descs = dataset.frame["Part_Desc"].fillna("").tolist()
    mpns = dataset.frame["Mfg_Part_Num"].fillna("").tolist()

    start = time.perf_counter()
    results = [scan_part_desc(desc) for desc in descs]
    elapsed = time.perf_counter() - start

    rows_with_pattern = [r for r in results if r.found]
    rows_clean = [r for r in rows_with_pattern if r.clean]
    rows_unparsed = [r for r in rows_with_pattern if not r.clean]

    kind_counts: Counter[str] = Counter()
    for r in rows_with_pattern:
        kind_counts[r.primary.kind] += 1

    clean_examples = [(mpns[i], results[i].part_desc, results[i].primary) for i, r in enumerate(results) if r.found and r.clean][:EXAMPLE_COUNT]
    unparsed_examples = [(mpns[i], results[i].part_desc, results[i].primary) for i, r in enumerate(results) if r.found and not r.clean][:EXAMPLE_COUNT]

    total = len(results)
    found_pct = 100 * len(rows_with_pattern) / total if total else 0.0
    clean_pct = 100 * len(rows_clean) / len(rows_with_pattern) if rows_with_pattern else 0.0
    unparsed_pct = 100 * len(rows_unparsed) / len(rows_with_pattern) if rows_with_pattern else 0.0

    section("detection summary")
    print(f"  rows scanned:                 {total}")
    print(f"  rows with a pattern found:    {len(rows_with_pattern)} ({found_pct:.1f}%)")
    print(f"  of those, parsed cleanly:     {len(rows_clean)} ({clean_pct:.1f}%)")
    print(f"  of those, unparsed:           {len(rows_unparsed)} ({unparsed_pct:.1f}%)")

    section("primary match kind, rows with a pattern found")
    for kind, count in kind_counts.most_common():
        print(f"  {kind:<16} {count:>4} rows")

    section("timing")
    rows_per_sec = total / elapsed if elapsed > 0 else float("inf")
    print(f"  {total} rows in {elapsed:.4f}s ({rows_per_sec:,.0f} rows/sec)")

    section(f"sample — parsed cleanly (up to {EXAMPLE_COUNT})")
    for mpn, desc, match in clean_examples:
        print(f"  {mpn:<16} {desc!r}\n      -> {match}")

    section(f"sample — unparsed (up to {EXAMPLE_COUNT})")
    for mpn, desc, match in unparsed_examples:
        print(f"  {mpn:<16} {desc!r}\n      -> {match}")

    return {
        "total": total,
        "found": len(rows_with_pattern),
        "found_pct": found_pct,
        "clean": len(rows_clean),
        "clean_pct": clean_pct,
        "unparsed": len(rows_unparsed),
        "unparsed_pct": unparsed_pct,
        "kind_counts": kind_counts,
        "elapsed_sec": elapsed,
        "rows_per_sec": rows_per_sec,
        "clean_examples": clean_examples,
        "unparsed_examples": unparsed_examples,
    }


def write_report(stats: dict) -> Path:
    lines = [
        "# Step 9b — UOM/fraction pattern detection, full-scale report",
        "",
        "**Not an accuracy report.** There is no ground truth for what \"the\" "
        "measurement in a free-text `Part_Desc` string is, so nothing here is "
        "scored against a known-correct answer. This reports pattern-detection "
        "throughput and parse-cleanliness at real scale: how many rows contain "
        "a numeric+fraction+unit-shaped token, and of those, how many resolved "
        "on the 1/64 grid with a `uom_normalizer`-recognized unit vs how many "
        "didn't. Unparsed patterns are reported, never guessed at or fixed — "
        "see `pipeline/desc_pattern_scanner.py` for the detection rules and "
        "their documented false-positive/false-negative limitations.",
        "",
        "## Run stats",
        "",
        f"- rows scanned: {stats['total']}",
        f"- rows with a pattern found: {stats['found']} ({stats['found_pct']:.1f}%)",
        f"- of those, parsed cleanly: {stats['clean']} ({stats['clean_pct']:.1f}%)",
        f"- of those, unparsed: {stats['unparsed']} ({stats['unparsed_pct']:.1f}%)",
        f"- timing: {stats['elapsed_sec']:.4f}s for {stats['total']} rows "
        f"({stats['rows_per_sec']:,.0f} rows/sec)",
        "",
        "## Primary match kind, rows with a pattern found",
        "",
    ]
    for kind, count in stats["kind_counts"].most_common():
        lines.append(f"- `{kind}`: {count} rows")
    lines += [
        "",
        "## Findings",
        "",
        "The clean-parse rate reflects how the real data is written, not a "
        "defect in the scanner: fractions like `3/8` and `6-1/2` land exactly "
        "on the 64ths grid and parse cleanly, but a large share of `Part_Desc` "
        "trailing symbols after a number are domain markers this UOM registry "
        "was never built to cover — `#` for a screw-head size (`150#`, "
        "`#1 Phillips`), `'` for feet (`6'`), horsepower/phase markers "
        "(`1.75HP`, `1PH`). Those are counted as `unknown_unit` and left "
        "unparsed rather than guessed at.",
        "",
        "This is a pattern-shape scanner, not a semantic one: the token-start "
        "guard in `desc_pattern_scanner.py` filters out most alphanumeric "
        "SKU-code fragments (e.g. `49-94-0013`, `5B-332-080`), but a real unit "
        "abbreviation can still coincide with a brand/part-code fragment — "
        "`775L` (a 3M product code) reads as \"775 liters\", `9A` (a SKU "
        "prefix) reads as \"9 amps\". Those register as `known_unit` clean "
        "matches even though they are not genuine physical measurements. This "
        "is a known, documented imprecision (see the module docstring), not "
        "hidden in this report.",
        "",
        "## Sample — parsed cleanly",
        "",
    ]
    for mpn, desc, match in stats["clean_examples"]:
        lines.append(f"- `{mpn}` {desc!r}")
        lines.append(f"    - {match.kind}: `{match.raw}` — {match.detail}")
    lines += ["", "## Sample — unparsed", ""]
    for mpn, desc, match in stats["unparsed_examples"]:
        lines.append(f"- `{mpn}` {desc!r}")
        lines.append(f"    - {match.kind}: `{match.raw}` — {match.detail}")
    lines.append("")

    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / "step9b_report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> int:
    dataset = load_input_dataset()
    stats = run_full_scale(dataset)
    report_path = write_report(stats)

    rule("REPORT")
    print(f"Written to {report_path.relative_to(BACKEND_DIR)}")

    rule("STEP 9B COMPLETE")
    print(
        f"{stats['total']} rows scanned in {stats['elapsed_sec']:.4f}s "
        f"({stats['rows_per_sec']:,.0f} rows/sec). "
        f"{stats['found']}/{stats['total']} ({stats['found_pct']:.1f}%) rows have a "
        f"measurement-shaped pattern in Part_Desc; of those, {stats['clean']} "
        f"({stats['clean_pct']:.1f}%) parsed cleanly and {stats['unparsed']} "
        f"({stats['unparsed_pct']:.1f}%) hit an unrecognized fraction/unit. "
        "Pattern-shape and throughput only — not an accuracy claim."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
