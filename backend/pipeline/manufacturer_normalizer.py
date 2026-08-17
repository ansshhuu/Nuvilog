"""
Step 4: manufacturer/brand — honest canonicalization only.

READ THIS BEFORE TRUSTING ANYTHING IN THIS FILE.

INVESTIGATION (done before writing any of this) proved that
MANUFACTURER_NAME / BRAND_NAME cannot be derived from the input row.
Both known worked-example rows (PDSH4816AF, WDTS7024RZ) share an
IDENTICAL Part_Manuf value — 'Appliance Dealers Cooperative (APPDE)' —
and IDENTICAL sentinel-empty E1_Brand/Unilog_Brand/DIB_Brand columns,
yet resolve to two completely different manufacturers and brands
(Rheem Manufacturing / FRIGIDAIRE vs Whirlpool Corporation / Whirlpool).
The same input value cannot map to two different outputs, so no function
Part_Manuf -> MANUFACTURER_NAME exists. The ground-truth values in the
worked examples came from looking up what the part numbers actually are
in the real world, not from transforming anything present in the row.

Part_Manuf is Unilog's own vendor/distributor-cooperative field — who
supplied the part into Unilog's catalog — not the product manufacturer.
See inferred_rules.NOT_BUILT for the earlier decision not to build a
fuzzy matcher against a manufacturer master list that does not exist.

What IS real, in-row signal, and what this module actually builds:
  * the "Name (CODE)" pattern dataset_loader.py already parses on
    959/1000 rows (the other 41 are the literal sentinel '-', meaning
    no vendor data at all — not a parse failure);
  * 76 distinct vendor display names, worth canonicalizing for internal
    spelling/punctuation consistency;
  * a per-row confidence flag so a blank manufacturer field reads as
    "known unresolved", not a silent omission that looks like a bug.

This module does NOT and WILL NOT produce a MANUFACTURER_NAME or
BRAND_NAME value. Any code that tries to fill those fields from
Part_Manuf is wrong by the two known rows above — don't add it here.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Literal, Sequence

# Part_Manuf == '-' is a distinct sentinel meaning "no vendor recorded at
# all" — different from a code-parse failure. 41/1000 rows in the sample.
NO_VENDOR_DATA_SENTINEL = "-"

# Chosen from an audit of the real 76-value vocabulary (see
# cluster_vendor_names docstring): the closest ratio between two genuinely
# DIFFERENT companies in this dataset is 0.80 ('CMT USA Inc' vs
# 'Makita Usa Inc'). True spelling variants of the same name normalize to
# ratio 1.0 ('Freud Inc' / 'Freud, Inc.' / 'FREUD INC'). 0.90 sits with
# margin on both sides of that gap.
DEFAULT_CLUSTER_THRESHOLD = 0.90

ResolutionStatus = Literal["vendor_code_present", "no_vendor_data"]

RESOLUTION_LABEL: dict[ResolutionStatus, str] = {
    "vendor_code_present": "vendor code present, actual manufacturer unresolved",
    "no_vendor_data": "no vendor data in source row, actual manufacturer unresolved",
}


def normalize_vendor_display(name: str) -> str:
    """Whitespace/punctuation-spacing cleanup only — never changes meaning.

    Collapses repeated whitespace and trims stray leading/trailing
    punctuation. Does not change case or merge words: this is display
    hygiene, not the clustering step below.
    """
    cleaned = re.sub(r"\s+", " ", name).strip()
    cleaned = cleaned.strip(" ,.")
    return cleaned


def _normalize_for_clustering(name: str) -> str:
    """Aggressive normalization used ONLY to compare names for clustering."""
    s = name.lower()
    s = re.sub(r"[.,]", "", s)
    s = re.sub(r"[&/]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


@dataclass(frozen=True)
class VendorCluster:
    """A group of vendor display strings judged to be the same vendor."""

    canonical: str
    members: tuple[str, ...]

    @property
    def is_singleton(self) -> bool:
        """True when this 'cluster' is just one name with nothing to merge."""
        return len(self.members) == 1


def cluster_vendor_names(
    names: Sequence[str], threshold: float = DEFAULT_CLUSTER_THRESHOLD
) -> list[VendorCluster]:
    """Group near-identical vendor spellings via difflib similarity.

    Greedy single-link clustering over the 76-value vocabulary — a
    within-dataset consolidation step, not a match against any external
    master list (none exists, see inferred_rules.NOT_BUILT). Each name is
    compared to the first member of every existing cluster; anything at or
    above `threshold` after normalization joins that cluster, otherwise it
    starts its own.

    Run against the real 76 Part_Manuf names, this returns 76 singleton
    clusters — see backend/scripts/step4_manufacturer.py for the full
    printout. That is a genuine finding, not a bug: this vocabulary
    already carries a unique vendor code per name (verified 1:1 in
    dataset_loader's parsed manuf_code column), so there is nothing left
    to dedupe. The clustering logic itself is still proven correct via
    self-test against synthetic near-duplicates ('Freud Inc' / 'Freud,
    Inc.' / 'FREUD INC') that DO need to merge.
    """
    ordered_unique = list(dict.fromkeys(names))
    normalized = {n: _normalize_for_clustering(n) for n in ordered_unique}

    clusters: list[list[str]] = []
    for name in ordered_unique:
        placed = False
        for cluster in clusters:
            representative = cluster[0]
            ratio = difflib.SequenceMatcher(
                None, normalized[name], normalized[representative]
            ).ratio()
            if ratio >= threshold:
                cluster.append(name)
                placed = True
                break
        if not placed:
            clusters.append([name])

    return [
        VendorCluster(canonical=min(cluster, key=len), members=tuple(cluster))
        for cluster in clusters
    ]


@dataclass(frozen=True)
class ManufacturerResolution:
    """Per-row outcome. Never carries a MANUFACTURER_NAME or BRAND_NAME."""

    mfg_part_num: str
    vendor_name: str | None  # cleaned Part_Manuf display name, code stripped
    vendor_code: str | None
    status: ResolutionStatus

    @property
    def confidence_label(self) -> str:
        return RESOLUTION_LABEL[self.status]

    @property
    def manufacturer_name(self) -> None:
        """Always None. Present so callers can see, by the type, that this
        module refuses to guess — not just read a docstring saying so."""
        return None

    @property
    def brand_name(self) -> None:
        return None


def resolve_manufacturer(source_row: dict[str, str]) -> ManufacturerResolution:
    """Build the honest per-row flag from a raw 6-column input row.

    Expects the raw `Part_Manuf` column (not the pre-parsed manuf_name/
    manuf_code — this works directly off dataset_loader's regex so it has
    no hidden dependency on the DataFrame pipeline having already run).
    """
    mfg_part_num = (source_row.get("Mfg_Part_Num") or "").strip()
    raw = (source_row.get("Part_Manuf") or "").strip()

    if not raw or raw == NO_VENDOR_DATA_SENTINEL:
        return ManufacturerResolution(
            mfg_part_num=mfg_part_num,
            vendor_name=None,
            vendor_code=None,
            status="no_vendor_data",
        )

    match = re.match(r"^(?P<name>.*?)\s*\((?P<code>[^()]+)\)\s*$", raw)
    if match:
        vendor_name = normalize_vendor_display(match.group("name"))
        vendor_code = match.group("code").strip()
    else:
        vendor_name = normalize_vendor_display(raw)
        vendor_code = None

    return ManufacturerResolution(
        mfg_part_num=mfg_part_num,
        vendor_name=vendor_name or None,
        vendor_code=vendor_code,
        status="vendor_code_present" if vendor_code else "no_vendor_data",
    )
