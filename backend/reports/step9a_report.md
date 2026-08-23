# Step 9a — manufacturer/brand honesty layer, full-scale report

**Not an accuracy report.** This module never compares its output against a known-correct MANUFACTURER_NAME/BRAND_NAME, because ground truth exists for only 2/1000 rows. What follows is throughput and internal consistency at real scale: how many rows resolved to which status, how the vendor-name vocabulary clusters, and how fast it runs. See `pipeline/manufacturer_normalizer.py` and `backend/scripts/step4_manufacturer.py` for why this module deliberately never emits MANUFACTURER_NAME/BRAND_NAME.

## Run stats

- rows processed: 1000
- `no_vendor_data`: 41 rows
- `vendor_code_present`: 959 rows
- distinct Part_Manuf display names: 76
- distinct canonical vendor names after clustering: 76
- clustering groups merged (2+ names -> 1 canonical): 0
- fabricated MANUFACTURER_NAME/BRAND_NAME values: 0 (confirmed) — structural guarantee, `ManufacturerResolution.manufacturer_name`/`.brand_name` are hardcoded `None` properties, checked here on every one of this run's objects
- timing: 0.0319s for 1000 rows (31,353 rows/sec)
