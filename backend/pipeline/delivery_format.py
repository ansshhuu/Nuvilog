"""
Step 1: structured parse of the Unihack delivery format.

The delivery target is the 252-column header of
`Unihack_ Expected Output - Delivery Format.csv`. That header is the only
authoritative artifact we have for the output shape — there is no spec
document, no LOV file, no UOM master. So this module treats the CSV header
itself as the source of truth and derives structure from it at load time.

Nothing downstream should hardcode column names. Ask this module instead:

    fmt = load_delivery_format()
    fmt.group("descriptions").fields      # the 6 description columns
    fmt.attribute_slots[0].label_column   # "ATTRIBUTE_LABEL 1"
    row = fmt.empty_row()                 # all 252 keys, blank values

Group membership is expressed as match rules, not as a copied-out list of
252 strings, and load() asserts that every header column lands in exactly
one group. If the organizer ships a revised delivery file with new columns,
the load fails loudly instead of silently dropping them.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Pattern, Union

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DELIVERY_FORMAT_CSV = PROJECT_ROOT / "Unihack_ Expected Output - Delivery Format.csv"

Matcher = Union[str, Pattern[str]]


@dataclass(frozen=True)
class FieldGroup:
    """One logical block of the delivery format."""

    name: str
    description: str
    fields: tuple[str, ...]

    def __len__(self) -> int:
        return len(self.fields)

    def __iter__(self) -> Iterator[str]:
        return iter(self.fields)


@dataclass(frozen=True)
class AttributeSlot:
    """One ATTRIBUTE_LABEL/VALUE/UOM triplet, index 1..50."""

    index: int
    label_column: str
    value_column: str
    uom_column: str

    @property
    def columns(self) -> tuple[str, str, str]:
        return (self.label_column, self.value_column, self.uom_column)


@dataclass(frozen=True)
class MeasurePair:
    """A physical measurement column and its paired _UOM column."""

    measure: str  # e.g. "LENGTH"
    value_column: str  # "LENGTH"
    uom_column: str  # "LENGTH_UOM"


# Ordered group rules. First match wins, so more specific patterns come first.
# `description` is written for humans reading a pitch, not just for code.
_GROUP_RULES: tuple[tuple[str, str, tuple[Matcher, ...]], ...] = (
    (
        "source_passthrough",
        "The six input columns echoed back verbatim on the output row.",
        ("Mfg_Part_Num", "Part_Desc", "E1_Brand", "Unilog_Brand", "DIB_Brand", "Part_Manuf"),
    ),
    (
        "identity",
        "Item identity and the source URLs the enrichment was evidenced from.",
        ("MFR URL", re.compile(r"^Ref URL \d+$"), "PART_NUMBER", "SKU - MY_PART_NUMBER"),
    ),
    (
        "classification",
        "Merchant hierarchy (Dept/Class/Fine) plus the vendor-facing Classpath string.",
        ("Dept", "Class", "Fine", "Classpath"),
    ),
    (
        "manufacturer_brand",
        "Manufacturer, brand and part-number resolution.",
        (
            "MANUFACTURER_NAME",
            "BRAND_NAME",
            "TRADE_NAME",
            "MANUFACTURER_PART_NUMBER",
            "ALTERNATE_PART_NUMBER",
        ),
    ),
    (
        "descriptions",
        "The five/six generated description formats, each with its own length and casing rules.",
        (
            "MOBILE_DESC",
            "INVOICE_DESC",
            "SHORT_DESC",
            "LONG_DESC1",
            "RETAIL_DESC",
            "MARKETING_DESCRIPTION",
        ),
    ),
    (
        "item_features",
        "Repeating marketing feature bullets, slots 1-20.",
        (re.compile(r"^ITEM_FEATURES_\d+$"),),
    ),
    (
        "description_components",
        "Reusable phrase fragments the long/short descriptions are assembled from.",
        (
            "With",
            "Standard/Approvals",
            "Prop 65",
            "Application",
            "Includes",
            "Product Name",
        ),
    ),
    (
        "attributes",
        "Repeating LABEL/VALUE/UOM triplets, slots 1-50 — the constrained-vocabulary block.",
        (re.compile(r"^ATTRIBUTE_(LABEL|VALUE|UOM) \d+$"),),
    ),
    (
        "commerce",
        "Trade identifiers, pricing and selling/packaging units.",
        (
            "UPC",
            "EAN",
            "GTIN",
            "UNSPSC",
            "Warranty",
            "List Price",
            "Selling Qty",
            "Selling UOM",
            "Standard Packaging Information",
        ),
    ),
    (
        "physical",
        "Dimensions and weight, each as a value column plus a paired _UOM column.",
        (re.compile(r"^(LENGTH|HEIGHT|WIDTH|WEIGHT|VOLUME)(_UOM)?$"),),
    ),
    (
        "digital_assets",
        "Image, document and video asset filenames/links.",
        (
            "Product Image",
            re.compile(r"^Alternate Image \d+$"),
            re.compile(r"^SDS(_\d+)?$"),
            "Warranty Information",
            "Catalog",
            "Specification Sheet",
            "Instruction/Installation Manual",
            "Service Manual",
            "Owners/User Manual",
            "Line Drawing",
            "MTR",
            "RoHS",
            "Full Engineering Drawing",
            "Energy Star Guide",
            "Technical Bulletin",
            "Submittal",
            "Compatibility Chart",
            "Size Chart",
            "Product Label/Insert",
            re.compile(r"^Video Link( \d+)?$"),
        ),
    ),
    (
        "metadata",
        "Row-level flags and provenance.",
        ("Country Of Origin", "Discontinued", "Actual Image (Yes/No)"),
    ),
)

# Measurements that follow the VALUE + VALUE_UOM convention, in header order.
_MEASURES = ("LENGTH", "HEIGHT", "WIDTH", "WEIGHT", "VOLUME")


def _matches(column: str, matcher: Matcher) -> bool:
    if isinstance(matcher, str):
        return column == matcher
    return bool(matcher.match(column))


@dataclass(frozen=True)
class DeliveryFormat:
    """The parsed 252-column delivery format."""

    columns: tuple[str, ...]
    groups: dict[str, FieldGroup]
    attribute_slots: tuple[AttributeSlot, ...]
    item_feature_columns: tuple[str, ...]
    measure_pairs: tuple[MeasurePair, ...]
    source_path: Path
    _column_group: dict[str, str] = field(repr=False, default_factory=dict)

    def group(self, name: str) -> FieldGroup:
        try:
            return self.groups[name]
        except KeyError:
            raise ValueError(
                f"Unknown group '{name}'. Available: {', '.join(self.groups)}"
            ) from None

    def group_of(self, column: str) -> str:
        try:
            return self._column_group[column]
        except KeyError:
            raise ValueError(f"'{column}' is not a delivery-format column") from None

    def empty_row(self) -> dict[str, str]:
        """A blank output row with all 252 keys in delivery order."""
        return {col: "" for col in self.columns}

    def summary(self) -> list[tuple[str, int, str]]:
        return [(g.name, len(g.fields), g.description) for g in self.groups.values()]


def load_delivery_format(path: Path = DELIVERY_FORMAT_CSV) -> DeliveryFormat:
    """Parse the delivery CSV header into a grouped, queryable structure."""
    with open(path, "r", encoding="utf-8", newline="") as f:
        header = next(csv.reader(f))

    columns = tuple(h.strip() for h in header)
    if len(set(columns)) != len(columns):
        dupes = sorted({c for c in columns if columns.count(c) > 1})
        raise ValueError(f"Delivery format has duplicate columns: {dupes}")

    grouped: dict[str, list[str]] = {name: [] for name, _, _ in _GROUP_RULES}
    column_group: dict[str, str] = {}

    for col in columns:
        for name, _, matchers in _GROUP_RULES:
            if any(_matches(col, m) for m in matchers):
                grouped[name].append(col)
                column_group[col] = name
                break
        else:
            raise ValueError(
                f"Delivery column '{col}' matched no group rule. The delivery format "
                f"changed — update _GROUP_RULES in {Path(__file__).name} rather than "
                f"letting the column be dropped."
            )

    groups = {
        name: FieldGroup(name=name, description=desc, fields=tuple(grouped[name]))
        for name, desc, _ in _GROUP_RULES
    }

    attribute_slots = _parse_attribute_slots(groups["attributes"].fields)
    item_features = groups["item_features"].fields
    measure_pairs = tuple(
        MeasurePair(measure=m, value_column=m, uom_column=f"{m}_UOM")
        for m in _MEASURES
        if m in column_group and f"{m}_UOM" in column_group
    )

    return DeliveryFormat(
        columns=columns,
        groups=groups,
        attribute_slots=attribute_slots,
        item_feature_columns=item_features,
        measure_pairs=measure_pairs,
        source_path=path,
        _column_group=column_group,
    )


def _parse_attribute_slots(attribute_columns: tuple[str, ...]) -> tuple[AttributeSlot, ...]:
    """Fold the flat ATTRIBUTE_* columns back into LABEL/VALUE/UOM triplets."""
    by_index: dict[int, dict[str, str]] = {}
    pattern = re.compile(r"^ATTRIBUTE_(LABEL|VALUE|UOM) (\d+)$")

    for col in attribute_columns:
        match = pattern.match(col)
        if not match:  # pragma: no cover - group rule guarantees the shape
            raise ValueError(f"Unexpected attribute column: {col}")
        role, index = match.group(1), int(match.group(2))
        by_index.setdefault(index, {})[role] = col

    slots = []
    for index in sorted(by_index):
        parts = by_index[index]
        missing = {"LABEL", "VALUE", "UOM"} - parts.keys()
        if missing:
            raise ValueError(f"Attribute slot {index} is missing {sorted(missing)}")
        slots.append(
            AttributeSlot(
                index=index,
                label_column=parts["LABEL"],
                value_column=parts["VALUE"],
                uom_column=parts["UOM"],
            )
        )
    return tuple(slots)


def load_worked_examples(path: Path = DELIVERY_FORMAT_CSV) -> list[dict[str, str]]:
    """The example output rows shipped in the delivery file.

    There are only 2 of them. They are a worked example of the target shape,
    NOT a scored ground-truth set — do not compute accuracy against them.
    """
    with open(path, "r", encoding="utf-8", newline="") as f:
        return [{k.strip(): (v or "") for k, v in row.items()} for row in csv.DictReader(f)]
