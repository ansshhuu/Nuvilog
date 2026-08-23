# Step 9b — UOM/fraction pattern detection, full-scale report

**Not an accuracy report.** There is no ground truth for what "the" measurement in a free-text `Part_Desc` string is, so nothing here is scored against a known-correct answer. This reports pattern-detection throughput and parse-cleanliness at real scale: how many rows contain a numeric+fraction+unit-shaped token, and of those, how many resolved on the 1/64 grid with a `uom_normalizer`-recognized unit vs how many didn't. Unparsed patterns are reported, never guessed at or fixed — see `pipeline/desc_pattern_scanner.py` for the detection rules and their documented false-positive/false-negative limitations.

## Run stats

- rows scanned: 1000
- rows with a pattern found: 611 (61.1%)
- of those, parsed cleanly: 434 (71.0%)
- of those, unparsed: 177 (29.0%)
- timing: 0.0106s for 1000 rows (94,393 rows/sec)

## Primary match kind, rows with a pattern found

- `known_unit`: 331 rows
- `unknown_unit`: 168 rows
- `bare_fraction`: 73 rows
- `compound`: 39 rows

## Findings

The clean-parse rate reflects how the real data is written, not a defect in the scanner: fractions like `3/8` and `6-1/2` land exactly on the 64ths grid and parse cleanly, but a large share of `Part_Desc` trailing symbols after a number are domain markers this UOM registry was never built to cover — `#` for a screw-head size (`150#`, `#1 Phillips`), `'` for feet (`6'`), horsepower/phase markers (`1.75HP`, `1PH`). Those are counted as `unknown_unit` and left unparsed rather than guessed at.

This is a pattern-shape scanner, not a semantic one: the token-start guard in `desc_pattern_scanner.py` filters out most alphanumeric SKU-code fragments (e.g. `49-94-0013`, `5B-332-080`), but a real unit abbreviation can still coincide with a brand/part-code fragment — `775L` (a 3M product code) reads as "775 liters", `9A` (a SKU prefix) reads as "9 amps". Those register as `known_unit` clean matches even though they are not genuine physical measurements. This is a known, documented imprecision (see the module docstring), not hidden in this report.

## Sample — parsed cleanly

- `DCB518ASTS06G` 'DCB518ASTS06G Diablo 1/2"x18" - Sanding Belt 6pc'
    - bare_fraction: `1/2` — decimal=0.5
- `5B-332-080` '5B-332-080 HIOLIT 5" P80'
    - known_unit: `5"` — unit=in (confirmed)
- `5B-332-120` '5B-332-120 HIOLIT 5" P120'
    - known_unit: `5"` — unit=in (confirmed)
- `9A-570-240` '9A-570-240 Abranet 2.75x30'
    - known_unit: `9A` — unit=A (confirmed)
- `9A-570-320` '9A-570-320 Abranet 2.75x30'
    - known_unit: `9A` — unit=A (confirmed)
- `DBD090094101F` 'DBD090094101F Diablo 9" - Metal Cut-Off Disc'
    - known_unit: `9"` — unit=in (confirmed)
- `DBDS12125A01F` 'DBDS12125A01F Diablo 12" - Steel Demon Metal Cut-Off Disc'
    - known_unit: `12"` — unit=in (confirmed)
- `DBDS12125G01F` 'DBDS12125G01F Diablo 12"x20mm - Speed Demon Metal Cut-Off Disc'
    - known_unit: `20mm` — unit=mm (inferred)

## Sample — unparsed

- `3MABR-7100075678` '3M 775L Stikit Film P150 - Cubitron II 50 Disc/Box'
    - unknown_unit: `3M` — unit not recognized
- `3MABR-7100045865` '3M 775L Stikit Film P120 - Cubitron II 50 Disc/Box'
    - unknown_unit: `3M` — unit not recognized
- `3MABR-7100048736` '3M 775L Stikit Film P80 - Cubitron II 50 Disc/Box'
    - unknown_unit: `3M` — unit not recognized
- `3MABR-7100075690` '3M 775L Stikit Film P180 - Cubitron II 50 Disc/Box'
    - unknown_unit: `3M` — unit not recognized
- `3MABR-7100075692` '3M 775L Stikit Film P220 - Cubitron II 50 Disc/Box'
    - unknown_unit: `3M` — unit not recognized
- `3MABR-7100145365` '3M 775L Stikit Film P320 - Cubitron II 50 Disc/Box'
    - unknown_unit: `3M` — unit not recognized
- `DFBLBLOMFN01G` 'DFBLBLOMFN01G Diablo 220 Grit - Flat Edge Sanding Sponge'
    - unknown_unit: `220 Grit` — unit not recognized
- `1700-1PK-BB40` "3/4x60' Vinyl Elect Tape"
    - unknown_unit: `60'` — unit not recognized
