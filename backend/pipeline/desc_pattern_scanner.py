"""
Step 9b: scan free-text Part_Desc for measurement patterns.

Part_Desc is free text ("3/8 CPLG BRS 150#", 'DBDS12125G01F Diablo 12"x20mm -
Speed Demon Metal Cut-Off Disc'), not structured ATTRIBUTE_VALUE/UOM columns
— those don't exist at scale (extraction has only run on the 2 known rows).
So this module is a new, small extraction step: find numeric+fraction+unit
tokens in the raw text and run them through the ALREADY-BUILT conversion
functions in fraction_converter.py / uom_normalizer.py. It does not add any
new fraction or unit conversion logic of its own.

Four pattern kinds, per the spec:
  * compound       — hyphenated whole+fraction, "24-1/4"
  * bare_fraction  — a standalone fraction, "3/8"
  * known_unit     — a number immediately followed by a unit abbreviation
                      uom_normalizer recognizes (CONFIRMED or INFERRED tier),
                      e.g. "0.5 IN", "115V", '12"' (the quote-mark alias for
                      "in")
  * unknown_unit   — a number immediately followed by something that LOOKS
                      like a unit (short trailing letters, '"', "'", "#")
                      but that uom_normalizer does not recognize, e.g. "150#"
                      (a screw-head size marker in this data, not pounds) or
                      "13'" (feet written as an apostrophe — not in
                      UNIT_REGISTRY at all)

A number is only treated as the start of a candidate token when it is NOT
itself a fragment of an alphanumeric part code — this dataset is full of
SKU segments shaped like "49-94-0013" or "5B-332-080" where a digit sits
directly against a letter with no measurement intended. The token-start
guard (`_TOKEN_START`) requires the digit to be preceded by whitespace,
string-start, or an opening bracket/paren — not by a letter or another
digit-hyphen run. This does not eliminate every false positive (a real
unit abbreviation can still coincide with a part-code fragment, e.g. a
stray "775L"), so `unknown_unit`/`known_unit` counts should be read as a
pattern-shape scan, not a semantic guarantee that every match is a genuine
physical measurement. That imprecision is reported, not hidden.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Optional

from pipeline.fraction_converter import fraction_to_decimal, parse_compound
from pipeline.uom_normalizer import UNIT_REGISTRY, normalize_unit

PatternKind = Literal["compound", "bare_fraction", "known_unit", "unknown_unit"]

# Every canonical abbreviation + every alias in the registry, longest-first
# so e.g. "inches" is tried before "in" and doesn't get cut short.
_ALL_UNIT_STRINGS: list[str] = sorted(
    {abbr for abbr in UNIT_REGISTRY}
    | {alias for unit in UNIT_REGISTRY.values() for alias in unit.aliases},
    key=len,
    reverse=True,
)
_KNOWN_UNIT_ALT = "|".join(re.escape(u) for u in _ALL_UNIT_STRINGS)

# A candidate number must start at a token boundary: string-start,
# whitespace, or an opening bracket — not glued to a preceding letter or to
# another digit-hyphen run (which is how this dataset's SKU segments look,
# e.g. "49-94-0013", "5B-332-080"). 'x'/'X' is exempted: it's the dimension
# connector this dataset writes with no surrounding spaces (`6-1/2"x1/8"`),
# not a SKU-fragment letter.
_TOKEN_START = r"(?<![A-WYZa-wyz0-9-])"

COMPOUND_RE = re.compile(rf"{_TOKEN_START}\d+-\d+/\d+\b")
BARE_FRACTION_RE = re.compile(rf"{_TOKEN_START}\d+/\d+\b")
KNOWN_UNIT_RE = re.compile(
    rf"{_TOKEN_START}\d+(?:\.\d+)?\s?(?:{_KNOWN_UNIT_ALT})(?![A-Za-z])", re.IGNORECASE
)
# Trailing-symbol/short-letters unit candidate that ISN'T a registry match —
# only counted where KNOWN_UNIT_RE didn't already claim the span.
UNKNOWN_UNIT_RE = re.compile(
    rf'{_TOKEN_START}\d+(?:\.\d+)?\s?(?:["\'#]|[A-Za-z]{{1,4}})(?=[\s,;)]|$)'
)


@dataclass(frozen=True)
class MeasurementMatch:
    raw: str
    kind: PatternKind
    clean: bool
    detail: str


@dataclass(frozen=True)
class ScanResult:
    """Per-row scan outcome. `clean` reflects the first match only, since
    that's the one reported per row — see `matches` for every hit found."""

    part_desc: str
    found: bool
    matches: tuple[MeasurementMatch, ...]

    @property
    def primary(self) -> Optional[MeasurementMatch]:
        return self.matches[0] if self.matches else None

    @property
    def clean(self) -> Optional[bool]:
        """None when nothing was found — there's no parse to judge clean or not."""
        primary = self.primary
        return primary.clean if primary else None


def _spans_overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def scan_part_desc(text: str) -> ScanResult:
    """Find measurement-shaped tokens in one Part_Desc string.

    Reuses fraction_converter.fraction_to_decimal/parse_compound and
    uom_normalizer.normalize_unit for every parse judgement — this function
    only locates candidate substrings, it never decides on its own whether a
    fraction or unit is valid.
    """
    if not text:
        return ScanResult(part_desc=text, found=False, matches=())

    candidates: list[tuple[tuple[int, int], MeasurementMatch]] = []

    for m in COMPOUND_RE.finditer(text):
        raw = m.group(0)
        compound = parse_compound(raw)
        clean = compound is not None
        detail = f"decimal={compound.decimal}" if compound else "not on 1/64 grid"
        candidates.append((m.span(), MeasurementMatch(raw, "compound", clean, detail)))

    numeric_spans = [span for span, _ in candidates]  # compound matches so far

    for m in BARE_FRACTION_RE.finditer(text):
        span = m.span()
        if any(_spans_overlap(span, ns) for ns in numeric_spans):
            continue  # already counted as part of a compound match
        raw = m.group(0)
        decimal = fraction_to_decimal(raw)
        clean = decimal is not None
        detail = f"decimal={decimal}" if clean else "not on 1/64 grid"
        candidates.append((span, MeasurementMatch(raw, "bare_fraction", clean, detail)))
        numeric_spans.append(span)

    known_spans: list[tuple[int, int]] = []
    for m in KNOWN_UNIT_RE.finditer(text):
        span = m.span()
        if any(_spans_overlap(span, ns) for ns in numeric_spans):
            continue  # the numeric part is already claimed by a fraction match
        raw = m.group(0)
        unit_text = re.sub(r"^[\d.\s]+", "", raw)
        unit_def = normalize_unit(unit_text)
        clean = unit_def is not None
        detail = f"unit={unit_def.abbreviation} ({unit_def.confidence})" if unit_def else "unit not recognized"
        candidates.append((span, MeasurementMatch(raw, "known_unit", clean, detail)))
        known_spans.append(span)

    for m in UNKNOWN_UNIT_RE.finditer(text):
        span = m.span()
        if any(_spans_overlap(span, ns) for ns in numeric_spans):
            continue  # the numeric part is already claimed by a fraction match
        if any(_spans_overlap(span, ks) for ks in known_spans):
            continue  # already a recognized-unit match
        raw = m.group(0)
        candidates.append((span, MeasurementMatch(raw, "unknown_unit", False, "unit not recognized")))

    candidates.sort(key=lambda item: item[0][0])
    matches = tuple(match for _, match in candidates)
    return ScanResult(part_desc=text, found=bool(matches), matches=matches)
