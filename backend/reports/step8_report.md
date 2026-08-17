# Step 8 — manufacturer-site enrichment report

Proof-of-concept scoped to the 2 known dishwasher rows with a known MFR URL. See `pipeline/manufacturer_enrichment.py` and the NOT_BUILT entry in `pipeline/inferred_rules.py` for why this doesn't extend to the other 8/990 rows yet.

**Evidence-discipline self-test:** PASS — every high/medium-confidence extracted field's snippet is a genuine substring of the fetched page.

## Before / after

| Mfg_Part_Num | descriptions nonempty (before -> after) | attributes verified (before -> after) | tier1 (before -> after) | tier2 (before -> after) | tier3 (before -> after) |
|---|---|---|---|---|---|
| PDSH4816AF | 1/5 -> 1/5 | 0/15 -> 0/15 | 210/252 -> 210/252 | 11/11 -> 11/11 | 176/176 -> 176/176 |
| WDTS7024RZ | 1/5 -> 1/5 | 0/15 -> 4/15 | 202/252 -> 205/252 | 11/11 -> 11/11 | 176/176 -> 176/176 |

## Findings

generate_descriptions() calls Gemini at temperature 0.1, not 0 — the exact split of which formats come back nonempty can vary slightly run to run for the same trusted fields (observed directly while building this report: one run produced 2/5 nonempty for WDTS7024RZ with SHORT_DESC picking up the real Series value, another run with fewer verified attributes produced 1/5). The pattern below held across every run: attribute verification lift is deterministic (it's a direct read of confidence_engine's scoring against the fetched page), description lift is not guaranteed even when attributes verify, because SHORT_DESC/LONG_DESC1's rules assume BRAND_NAME, which attribute-only enrichment never recovers.

* **PDSH4816AF**: fetch failed (see section 1), so 0 attributes verified and no lift of any kind — the honest outcome of a dead manufacturer link, not a generation problem.
* **WDTS7024RZ**: 4 attributes went from unresolved to verified, tier1 exact-match moved 202 -> 205 fields purely from those values landing in the assembled row. Description generation did NOT pick up the lift this run (1/5 -> 1/5 nonempty) — see the note above on why that's not guaranteed even with real verified attributes on hand.


## Generated descriptions, before / after

### PDSH4816AF

* **INVOICE_DESC**
    * before: 'PDSH4816AF DISHWASHER SS'
    * after:  'PDSH4816AF DISHWASHER SS - DISPLAY ONLY'
* **MOBILE_DESC**
    * before: ''
    * after:  ''
* **SHORT_DESC**
    * before: ''
    * after:  ''
* **LONG_DESC1**
    * before: ''
    * after:  ''
* **MARKETING_DESCRIPTION**
    * before: ''
    * after:  ''

### WDTS7024RZ

* **INVOICE_DESC**
    * before: 'WDTS7024RZ DISHWASHER SS'
    * after:  'WDTS7024RZ DISHWASHER SS'
* **MOBILE_DESC**
    * before: ''
    * after:  ''
* **SHORT_DESC**
    * before: ''
    * after:  ''
* **LONG_DESC1**
    * before: ''
    * after:  ''
* **MARKETING_DESCRIPTION**
    * before: ''
    * after:  ''
