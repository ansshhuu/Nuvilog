"""
Step 1: load and clean the Unihack sample input dataset.

The input file has six columns and 1000 rows. Three of the brand columns use
sentinel strings ("-- Unbranded --", "-- No Unilog Brand --",
"-- No DIB Brand --") that mean "no value", not "a brand called Unbranded".
They are stripped to None here so nothing downstream ever branches on the
literal text.

One nuance worth keeping straight: the sentinels are stripped for *reasoning*,
but the delivery format echoes the raw input columns back on the output row,
and both worked examples carry the sentinels through verbatim. So the cleaned
frame keeps the originals alongside the nulled versions — see `raw_columns`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_CSV = PROJECT_ROOT / "Unihack_ Sample Dataset - Input.csv"

# Sentinel values that mean "empty". Compared case-insensitively after strip.
BRAND_PLACEHOLDERS: frozenset[str] = frozenset(
    {
        "-- unbranded --",
        "-- no unilog brand --",
        "-- no dib brand --",
        "-- no brand --",
    }
)

BRAND_COLUMNS = ("E1_Brand", "Unilog_Brand", "DIB_Brand")

# Part_Manuf looks like "Freud Inc (2435)" — a display name plus a vendor code.
_MANUF_CODE_RE = re.compile(r"^(?P<name>.*?)\s*\((?P<code>[^()]+)\)\s*$")


@dataclass(frozen=True)
class InputDataset:
    """The cleaned input, plus the provenance needed to echo it back out."""

    frame: pd.DataFrame
    source_path: Path

    @property
    def raw_columns(self) -> tuple[str, ...]:
        """The original six columns, unmodified — safe to echo to the output row."""
        return ("Mfg_Part_Num", "Part_Desc", "E1_Brand", "Unilog_Brand", "DIB_Brand", "Part_Manuf")

    def __len__(self) -> int:
        return len(self.frame)


def _null_placeholders(series: pd.Series) -> pd.Series:
    stripped = series.astype("string").str.strip()
    is_placeholder = stripped.str.lower().isin(BRAND_PLACEHOLDERS)
    return stripped.mask(is_placeholder | (stripped == ""), other=pd.NA)


def load_input_dataset(path: Path = INPUT_CSV) -> InputDataset:
    """Read the sample dataset and derive clean working columns.

    Adds, without touching the originals:
      * `<Brand>_clean`  — sentinel/blank values nulled out
      * `brand_resolved` — first non-null of DIB > E1 > Unilog brand
      * `manuf_name` / `manuf_code` — Part_Manuf split on its trailing "(CODE)"
    """
    frame = pd.read_csv(path, dtype="string", keep_default_na=False, encoding="utf-8")

    missing = [c for c in ("Mfg_Part_Num", "Part_Desc", "Part_Manuf") if c not in frame.columns]
    if missing:
        raise ValueError(f"Input dataset is missing expected columns: {missing}")

    for col in BRAND_COLUMNS:
        if col in frame.columns:
            frame[f"{col}_clean"] = _null_placeholders(frame[col])

    # Preference order is a judgement call: DIB brands are the most specific
    # real brand strings in this file, E1 next, Unilog is empty throughout.
    clean_brand_cols = [f"{c}_clean" for c in BRAND_COLUMNS if f"{c}_clean" in frame.columns]
    priority = [c for c in ("DIB_Brand_clean", "E1_Brand_clean", "Unilog_Brand_clean") if c in clean_brand_cols]
    frame["brand_resolved"] = pd.NA
    for col in priority:
        frame["brand_resolved"] = frame["brand_resolved"].fillna(frame[col])

    manuf = frame["Part_Manuf"].astype("string").str.strip()
    extracted = manuf.str.extract(_MANUF_CODE_RE)
    frame["manuf_name"] = extracted["name"].fillna(manuf).replace("", pd.NA)
    frame["manuf_code"] = extracted["code"]

    frame["Part_Desc"] = frame["Part_Desc"].astype("string").str.strip()
    frame["Mfg_Part_Num"] = frame["Mfg_Part_Num"].astype("string").str.strip()

    return InputDataset(frame=frame, source_path=path)


def placeholder_report(dataset: InputDataset) -> pd.DataFrame:
    """Per-brand-column count of how many rows were sentinels vs real values."""
    rows = []
    for col in BRAND_COLUMNS:
        clean = f"{col}_clean"
        if clean not in dataset.frame.columns:
            continue
        total = len(dataset.frame)
        real = int(dataset.frame[clean].notna().sum())
        rows.append(
            {
                "column": col,
                "rows": total,
                "real_values": real,
                "placeholder_or_blank": total - real,
                "distinct_real_values": int(dataset.frame[clean].nunique(dropna=True)),
            }
        )
    return pd.DataFrame(rows)
