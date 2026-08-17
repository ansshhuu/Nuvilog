# Step 6/7 — full pipeline run report

`run_dishwasher_pipeline.process_row()` run over all 10 real dishwasher rows.
process_row() never receives ground truth for any row — see that module's docstring.

## Per-row tier summary

| Mfg_Part_Num | known | tier1 (informational) | tier2 pass | tier3 pass | tier3 violations |
|---|---|---|---|---|---|
| KDFM404KPS | False | n/a | 11/11 | 177/177 | 0 |
| PDSH4816AF | True | 210/252 | 11/11 | 176/176 | 0 |
| PDT715SYVFS | False | n/a | 11/11 | 177/177 | 0 |
| LDPH5554D | False | n/a | 11/11 | 177/177 | 0 |
| WDTS7024RZ | True | 202/252 | 11/11 | 176/176 | 0 |
| PDD415PYYFS | False | n/a | 11/11 | 177/177 | 0 |
| KDTS424SBE | False | n/a | 11/11 | 177/177 | 0 |
| KDTS324SPS | False | n/a | 11/11 | 177/177 | 0 |
| KDPS624SJP | False | n/a | 11/11 | 177/177 | 0 |
| KDTS624SBE | False | n/a | 11/11 | 177/177 | 0 |

**Rows processed:** 10
**Aggregate tier2+tier3 rule-compliance rate:** 1878/1878 (100.0%)
**Tier-3 honesty-check violations:** 0 (expected: 0)

## Known-row description length/structure vs real

### PDSH4816AF

| field | real len | generated len | delta | generated nonempty |
|---|---|---|---|---|
| INVOICE_DESC | 38 | 24 | -14 | True |
| MOBILE_DESC | 75 | 0 | -75 | False |
| SHORT_DESC | 115 | 0 | -115 | False |
| LONG_DESC1 | 390 | 0 | -390 | False |
| MARKETING_DESCRIPTION | 0 | 0 | +0 | False |

process_row() has no external-lookup stage, so for a known row it only ever sees Mfg_Part_Num/Part_Desc — same as the 8 unverified rows. The gaps above are exactly what external lookup would need to close, not a generation-quality problem.

### WDTS7024RZ

| field | real len | generated len | delta | generated nonempty |
|---|---|---|---|---|
| INVOICE_DESC | 39 | 39 | +0 | True |
| MOBILE_DESC | 64 | 0 | -64 | False |
| SHORT_DESC | 96 | 0 | -96 | False |
| LONG_DESC1 | 405 | 0 | -405 | False |
| MARKETING_DESCRIPTION | 214 | 0 | -214 | False |

process_row() has no external-lookup stage, so for a known row it only ever sees Mfg_Part_Num/Part_Desc — same as the 8 unverified rows. The gaps above are exactly what external lookup would need to close, not a generation-quality problem.
