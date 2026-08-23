# Step 9 — combined scale report

**This demonstrates throughput and internal consistency at full dataset scale. Field-level accuracy claims remain scoped to the 10 dishwasher rows with available ground truth.**

Total rows processed: **1000**. Combined processing time: **0.0450s** (manufacturer resolution 0.0338s + UOM/fraction scan 0.0112s).

## Spot check

Two hand-verifiable checks against real rows, run as a self-test before this report is generated — if either fails, no report gets written. Included here so this report is self-contained proof, not a claim that requires re-running the script to verify.

**PASS** — `Mfg_Part_Num 576355`, `Part_Desc '576355 60/100/150 Led Med 50k'`
- primary match: `60/100` (bare_fraction, unparsed) — not on 1/64 grid
- 60/100 has denominator 100, and 64 % 100 != 0, so it cannot land on the 1/64 grid — must report unparsed, not a guessed nearest fraction.

**PASS** — `Mfg_Part_Num 37300952`, `Part_Desc '095842 Fisch Plug Cutter 3/8"'`
- primary match: `3/8` (bare_fraction, clean) — decimal=0.375
- 3/8 is 24/64 reduced — exactly on the 1/64 grid, decimal value 0.375.

## Part A — manufacturer/brand honesty layer

- rows processed: 1000
- `no_vendor_data`: 41 rows
- `vendor_code_present`: 959 rows
- distinct Part_Manuf display names: 76
- distinct canonical vendor names after clustering: 76
- fabricated MANUFACTURER_NAME/BRAND_NAME values: 0 (confirmed zero)
- timing: 0.0338s (29,578 rows/sec)

See `backend/reports/step9a_report.md` for the standalone, more detailed version.

## Part B — UOM/fraction pattern detection

- rows scanned: 1000
- rows with a pattern found: 611 (61.1%)
- of those, parsed cleanly: 434 (71.0%)
- of those, unparsed: 177 (29.0%)
- timing: 0.0112s (89,117 rows/sec)

Primary match kind, rows with a pattern found:

- `known_unit`: 331 rows
- `unknown_unit`: 168 rows
- `bare_fraction`: 73 rows
- `compound`: 39 rows

See `backend/reports/step9b_report.md` for the standalone, more detailed version, including sample rows and known false-positive/false-negative caveats.

## Scope

Neither part touches `dishwasher_schema.py`, `description_builder.py`, or `run_dishwasher_pipeline.py` — those stay scoped to the 10 dishwasher rows exactly as before. This report is additive.
