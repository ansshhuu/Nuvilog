"""
Stage 5: contradiction detection.

Contract:

    def detect_contradictions(
        scored_fields: list[ScoredField],
        raw_doc: RawDocument,
        schema: CategorySchema,
    ) -> list[Contradiction]

Runs on every product in a batch, not just single-product mode (see
batch_runner.py). Two kinds of checks:
  1. Cross-field: does one extracted field conflict with another
     (e.g. two different voltages found in different source sections)?
  2. Range: does a "dimension"-typed field fall outside its schema's
     valid_range (see schema_registry.FieldDef.valid_range)?

Findings are written to the validation_flags table (models/db.py),
issue_type in {"contradiction", "out_of_range"}.

No LLM call happens here. Like the confidence engine (stage 4), findings
are derived from the source text itself, so the same input always
produces the same flags and every flag can be traced to a line the
reviewer can go read. An LLM judging its own extraction would reintroduce
exactly the unverifiable self-assessment stages 4 and 5 exist to avoid.

How the cross-field check works
-------------------------------
Spec sheets state a value by labelling it ("Thread Diameter: 6.35 mm"),
so the source is scanned for every `Label: value` statement — in the
prose and in table rows, where the first cell is the label and the second
is the value. A statement belongs to a field if the field's alias (its
schema name, plus the label the LLM itself cited in source_snippet)
appears in the statement's label.

The extracted value and every statement found for that field are then
grouped by equivalence. More than one group means the source says two
different things about one attribute — or says something different from
what was extracted — and a flag is raised naming every value and where it
came from.

Nothing is auto-resolved. A detector that quietly picked a winner would
be guessing at exactly the moment a human needs to look, so both values
are recorded and the field keeps whatever confidence stage 4 gave it.

Range checks read min/max from the category YAML (schemas/*.yaml), never
from constants in this module: adding a category, or retuning a bound,
stays a data change.
"""
from __future__ import annotations

import re
from typing import Literal, Optional

from pydantic import BaseModel

from pipeline.confidence_engine import ScoredField
from pipeline.schema_registry import CategorySchema, FieldDef
from pipeline.types import RawDocument

# A label is short, starts a line, and is followed by ':'. The cap keeps
# prose sentences that happen to contain a colon from parsing as labels.
LABEL_MAX_CHARS = 40
LABELED_STATEMENT_RE = re.compile(
    r"^[ \t]*(?P<label>[A-Za-z][A-Za-z0-9 ./_()-]{0," + str(LABEL_MAX_CHARS) + r"}?)[ \t]*:"
    r"[ \t]*(?P<value>\S[^\n]*)$",
    re.MULTILINE,
)

NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")

# Numeric values agree within 1%: "25.4 mm" and "25.40 mm" are the same
# measurement, and a spec sheet rounding 6.35 to 6.4 is not a contradiction
# worth a reviewer's time. Anything coarser starts hiding real conflicts.
NUMERIC_TOLERANCE = 0.01

NUMERIC_TYPES = ("dimension", "integer", "number")


class Contradiction(BaseModel):
    field_name: str | None
    issue_type: Literal["contradiction", "out_of_range"]
    message: str


class _Mention(BaseModel):
    """One place a value for some attribute was stated."""

    value: str
    location: str


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _leading_number(text: str) -> Optional[float]:
    """First number in the text.

    First, not all: "1.27 mm (20 TPI)" states a pitch of 1.27, with 20 as a
    restatement in another unit. Taking the last or the largest would read
    the parenthetical as the value.
    """
    match = NUMBER_RE.search(text)
    if not match:
        return None
    try:
        return float(match.group())
    except ValueError:  # pragma: no cover - regex only matches parseable floats
        return None


def _collect_statements(raw_doc: RawDocument) -> list[tuple[str, _Mention]]:
    """Every `Label: value` statement in the document, as (label, mention).

    Table rows are folded in as statements too — a two-column spec table row
    is the same assertion as a labelled prose line, just laid out differently.
    """
    statements: list[tuple[str, _Mention]] = []

    for match in LABELED_STATEMENT_RE.finditer(raw_doc.raw_text):
        line_number = raw_doc.raw_text.count("\n", 0, match.start()) + 1
        statements.append(
            (
                _normalize(match.group("label")),
                _Mention(value=match.group("value").strip(), location=f"line {line_number}"),
            )
        )

    for table_index, table in enumerate(raw_doc.tables, start=1):
        for row_index, row in enumerate(table, start=1):
            # Stage 1 already normalizes empty cells to "" (input_handler),
            # so a row can be short or padded but never carries None.
            cells = [cell.strip() for cell in row if cell.strip()]
            if len(cells) < 2:
                continue
            statements.append(
                (
                    _normalize(cells[0]),
                    _Mention(
                        value=cells[1],
                        location=f"table {table_index}, row {row_index}",
                    ),
                )
            )

    return statements


def _aliases(field_def: FieldDef, scored: ScoredField) -> list[str]:
    """Labels in the source that mean this field.

    The schema name ("thread_pitch" -> "thread pitch") plus the label the LLM
    quoted in its own snippet, which is how a source's wording for a field
    ("Thread Diameter" for `diameter`) gets picked up without this module
    carrying a synonym table it would have to grow per category.

    Names are kept whole rather than split into tokens on purpose: a bare
    "thread" alias would match both "Thread Diameter" and "Thread Pitch" and
    manufacture a contradiction between two unrelated fields.
    """
    found = [field_def.name.replace("_", " ").lower()]

    snippet = scored.source_snippet
    if snippet and ":" in snippet:
        label = _normalize(snippet.split(":", 1)[0])
        if label and len(label) <= LABEL_MAX_CHARS and label not in found:
            found.append(label)

    return found


def _values_agree(first: str, second: str, field_def: FieldDef) -> bool:
    """Whether two statements of the same attribute say the same thing.

    Numeric fields compare by magnitude, so "6.35 mm" matches
    "6.35 mm (1/4 in nominal)". Text fields compare by containment, so
    "Hex" matches "Hex Head" but not "Socket Cap" — a stricter equality
    would flag every source that abbreviates.
    """
    first_norm, second_norm = _normalize(first), _normalize(second)
    if not first_norm or not second_norm:
        return True  # nothing to compare; not evidence of a conflict
    if first_norm == second_norm:
        return True

    if field_def.type in NUMERIC_TYPES:
        first_num, second_num = _leading_number(first_norm), _leading_number(second_norm)
        if first_num is not None and second_num is not None:
            scale = max(abs(first_num), abs(second_num), 1.0)
            return abs(first_num - second_num) <= NUMERIC_TOLERANCE * scale
        # One side has no number at all — fall through and compare as text.

    return first_norm in second_norm or second_norm in first_norm


def _group_mentions(mentions: list[_Mention], field_def: FieldDef) -> list[list[_Mention]]:
    """Cluster mentions into groups that agree with each other.

    Greedy against each group's first member. Containment-based agreement
    isn't transitive, so this is order-dependent by nature; document order is
    used so the result stays deterministic for a given document.
    """
    groups: list[list[_Mention]] = []
    for mention in mentions:
        for group in groups:
            if _values_agree(group[0].value, mention.value, field_def):
                group.append(mention)
                break
        else:
            groups.append([mention])
    return groups


def _describe(groups: list[list[_Mention]]) -> str:
    return " vs ".join(
        f'"{group[0].value}" ({", ".join(m.location for m in group)})' for group in groups
    )


def _check_contradiction(
    scored: ScoredField,
    field_def: FieldDef,
    statements: list[tuple[str, _Mention]],
) -> Optional[Contradiction]:
    aliases = _aliases(field_def, scored)
    mentions = [
        mention for label, mention in statements if any(alias in label for alias in aliases)
    ]

    if scored.value and str(scored.value).strip():
        mentions.insert(0, _Mention(value=str(scored.value).strip(), location="extracted value"))

    groups = _group_mentions(mentions, field_def)
    if len(groups) < 2:
        return None

    return Contradiction(
        field_name=field_def.name,
        issue_type="contradiction",
        message=(
            f"Conflicting values for '{field_def.name}': {_describe(groups)}. "
            "Not auto-resolved — every value is recorded for a human to decide between."
        ),
    )


def _check_range(scored: ScoredField, field_def: FieldDef, category: str) -> Optional[Contradiction]:
    valid_range = field_def.valid_range
    if valid_range is None or not scored.value:
        return None

    number = _leading_number(str(scored.value))
    if number is None:
        # No magnitude to test. Not silently "in range" — just not a range
        # question; a non-numeric value in a numeric field is stage 4's call.
        return None

    below = valid_range.min is not None and number < valid_range.min
    above = valid_range.max is not None and number > valid_range.max
    if not (below or above):
        return None

    bounds = []
    if valid_range.min is not None:
        bounds.append(f"min {valid_range.min:g}")
    if valid_range.max is not None:
        bounds.append(f"max {valid_range.max:g}")
    unit = f" {field_def.unit}" if field_def.unit else ""

    return Contradiction(
        field_name=field_def.name,
        issue_type="out_of_range",
        message=(
            f"'{field_def.name}' value \"{scored.value}\" reads as {number:g}{unit}, outside the "
            f"valid range for {category} ({', '.join(bounds)}) declared in "
            f"schemas/{category}.yaml."
        ),
    )


def detect_contradictions(
    scored_fields: list[ScoredField],
    raw_doc: RawDocument,
    schema: CategorySchema,
) -> list[Contradiction]:
    """Flag values the source disagrees with, and values outside schema range.

    Returns findings in schema field order, contradiction before out_of_range
    for the same field. Fields the schema doesn't define are skipped: there is
    no range to test and no reliable label to search for.
    """
    statements = _collect_statements(raw_doc)
    field_defs = {field.name: field for field in schema.fields}

    findings: list[Contradiction] = []
    for scored in scored_fields:
        field_def = field_defs.get(scored.field_name)
        if field_def is None:
            continue

        contradiction = _check_contradiction(scored, field_def, statements)
        if contradiction:
            findings.append(contradiction)

        out_of_range = _check_range(scored, field_def, schema.category)
        if out_of_range:
            findings.append(out_of_range)

    return findings
