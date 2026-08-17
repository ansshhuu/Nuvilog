# Step 7 — full pipeline report

10 real dishwasher rows, 2 with verified ground truth (PDSH4816AF, WDTS7024RZ), 8 with only Mfg_Part_Num/Part_Desc.
Delivery-format CSV: `output\dishwasher_delivery_rows.csv`

## Per-row scores

| Mfg_Part_Num | known | tier1 (informational) | tier2/tier3 pass | tier2/tier3 fail | invented numbers |
|---|---|---|---|---|---|
| KDFM404KPS | False | n/a | 188 | 0 | False |
| PDSH4816AF | True | 228/252 | 187 | 0 | False |
| PDT715SYVFS | False | n/a | 188 | 0 | False |
| LDPH5554D | False | n/a | 188 | 0 | False |
| WDTS7024RZ | True | 220/252 | 187 | 0 | False |
| PDD415PYYFS | False | n/a | 188 | 0 | False |
| KDTS424SBE | False | n/a | 188 | 0 | False |
| KDTS324SPS | False | n/a | 188 | 0 | False |
| KDPS624SJP | False | n/a | 188 | 0 | False |
| KDTS624SBE | False | n/a | 188 | 0 | False |

**Total tier2/tier3 failures across all 10 rows: 0**

## Column-group coverage (10 rows)

| group | columns | populated in >=1 row | zero-evidence columns |
|---|---|---|---|
| source_passthrough | 6 | 6 | 0 |
| identity | 8 | 0 | 3 |
| classification | 4 | 0 | 0 |
| manufacturer_brand | 5 | 2 | 2 |
| descriptions | 6 | 4 | 0 |
| item_features | 20 | 0 | 9 |
| description_components | 6 | 0 | 3 |
| attributes | 150 | 33 | 117 |
| commerce | 9 | 0 | 8 |
| physical | 10 | 0 | 10 |
| digital_assets | 25 | 0 | 19 |
| metadata | 3 | 0 | 2 |

## Explicitly out of scope (NOT_BUILT)

Carried over verbatim from `pipeline/inferred_rules.py` — nothing below
was silently skipped, it was decided against and documented:

* **manufacturer/brand fuzzy matcher against a master list** — Still cancelled, and permanently so. Matching Part_Manuf or the brand columns against a manufacturer master list requires that master list; it does not exist on disk and the organizer confirmed it will not be distributed. Confirmed separately (see manufacturer.not_derivable_from_part_manuf above): even if Part_Manuf were matched against something, it wouldn't help — the 2 known rows share an identical Part_Manuf and still resolve to different manufacturers, so Part_Manuf is not a manufacturer signal at all, it's Unilog's own vendor/distributor field. What WAS built instead (pipeline/manufacturer_normalizer.py): the 'Name (CODE)' vendor-code parse (959/1000 rows), within-dataset clustering of the 76 distinct vendor names for spelling/punctuation consolidation (real result: 0 of 76 turn out to be duplicates of each other — each already carries a unique code), and a per-row 'vendor code present, actual manufacturer unresolved' confidence flag. It never emits a MANUFACTURER_NAME or BRAND_NAME value.

* **range attribute scaffold** — 10 real range rows exist in the 1000-row sample (e.g. 'PS960YPFS 30" GE Electric Range SS - Display Only') but zero of them have a known-correct delivery-format answer. The confirmed dishwasher scaffold (attributes.dishwasher_scaffold_15_labels) does not transfer — 'Number of Wash Cycles' and 'Depth With Door Open' don't apply to a range. Guessing a range-specific label set from Part_Desc text alone would be exactly the kind of fabrication this project keeps refusing to do.

* **washer (laundry) attribute scaffold** — 8 real rows (e.g. 'FF7011WN Speed Queen Washer Wh'), zero ground-truth answers. Same reasoning as range attribute scaffold above.

* **microwave attribute scaffold** — 8 real rows (e.g. 'MSER2090S LG Microwave SS'), zero ground-truth answers. Same reasoning as range attribute scaffold above.

* **freezer attribute scaffold** — 3 real rows (e.g. 'EUF17CDBW Element 17CF Freezer - Upright'), zero ground-truth answers. Same reasoning as range attribute scaffold above.

* **cooktop attribute scaffold** — 2 real rows (e.g. 'PEP9030DTBB 30" GE Cooktop Bk'), zero ground-truth answers. Same reasoning as range attribute scaffold above.

* **UOM normalization table** — No UOM master file exists. Only the UOMs observed in the 2 examples (in, V, A, dBA) are known to be valid; any wider vocabulary would be invented.

* **fraction conversion table** — No fraction table exists. The ASCII fraction style is observable (see formatting.ascii_fractions) but rounding and denominator rules are not.

* **attribute LOV / constrained vocabulary** — No LOV files exist. The attribute label template is observable for one category (dishwashers) from 2 rows; permitted values per label are not.
