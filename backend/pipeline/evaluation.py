"""
Step 2: evaluation harness.

The original brief assumed ~200 known-correct rows to score field accuracy
against. Reality is 2. That changes what "evaluation" can mean here — this
module does NOT produce a single accuracy percentage. It produces three
independent tiers of checks, each honest about what it can and can't prove:

  TIER 1 — exact match against a known row. Only runs when `expected` is one
  of the 2 worked examples. Field-by-field, not aggregated — a percentage
  would hide which fields are wrong.

  TIER 2 — rule compliance. Runs on ANY generated row, known or not, by
  re-checking the assertable subset of `inferred_rules.RULES` against the
  single row (as opposed to inferred_rules.verify_rules(), which checks a
  rule's pattern holds *across* the 2 examples — a different question).
  HIGH-confidence rules are hard failures; MEDIUM/LOW are warnings, because
  a rule inferred from n=2 evidence is not something to fail a row over.

  TIER 3 — the honesty check. For every delivery column that is blank in
  BOTH worked examples (computed from the examples themselves, not
  hand-copied), a generated row must leave it blank too. A plausible-looking
  fabricated UNSPSC code is worse than a missing one — this tier exists to
  catch exactly that, loudly, and it is a hard failure with no warning tier.

Nothing here computes a single score. `EvalResult` carries the full list of
individual checks so a caller can render a table, filter to failures, or
count by tier — collapsing it to one number is a decision for the caller,
not this module.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Literal, Optional

from pipeline.delivery_format import DeliveryFormat, load_delivery_format, load_worked_examples
from pipeline.description_builder import DESCRIPTION_FIELDS, find_invented_numbers
from pipeline.dishwasher_schema import DISHWASHER_ATTRIBUTE_LABELS, is_dishwasher
from pipeline.inferred_rules import RULES_BY_ID
from pipeline.manufacturer_normalizer import resolve_manufacturer
from pipeline.uom_normalizer import (
    SPACING_RULE_EXEMPT_FIELDS,
    find_spacing_violations,
    is_compound_dimension,
)

Status = Literal["pass", "warn", "fail", "skip"]


@dataclass(frozen=True)
class CheckResult:
    """One individual check outcome — the smallest reportable unit."""

    tier: Literal[1, 2, 3]
    check_id: str  # column name (tier 1/3) or rule id (tier 2)
    status: Status
    reason: str
    expected: Optional[str] = None
    actual: Optional[str] = None

    @property
    def is_failure(self) -> bool:
        return self.status == "fail"


@dataclass(frozen=True)
class EvalResult:
    """All checks run for one row. Renderable, not pre-aggregated."""

    row_id: str
    checks: tuple[CheckResult, ...]

    def tier(self, n: int) -> tuple[CheckResult, ...]:
        return tuple(c for c in self.checks if c.tier == n)

    def by_status(self, status: Status) -> tuple[CheckResult, ...]:
        return tuple(c for c in self.checks if c.status == status)

    @property
    def failures(self) -> tuple[CheckResult, ...]:
        return self.by_status("fail")

    @property
    def warnings(self) -> tuple[CheckResult, ...]:
        return self.by_status("warn")

    @property
    def honesty_violations(self) -> tuple[CheckResult, ...]:
        """Tier 3 failures specifically — fabricated zero-evidence fields."""
        return tuple(c for c in self.tier(3) if c.status == "fail")

    @property
    def passed(self) -> bool:
        """True only if there are zero hard failures. Warnings don't block this."""
        return not self.failures

    def counts(self) -> dict[Status, int]:
        out: dict[Status, int] = {"pass": 0, "warn": 0, "fail": 0, "skip": 0}
        for c in self.checks:
            out[c.status] += 1
        return out


# --------------------------------------------------------------------------
# Tier 3 support: which columns have zero evidence, derived from the
# examples themselves rather than hand-copied — stays correct if the
# delivery file or the examples change.
# --------------------------------------------------------------------------

def derive_zero_evidence_columns(
    examples: list[dict[str, str]], fmt: Optional[DeliveryFormat] = None
) -> frozenset[str]:
    """Columns that are blank in every one of the worked example rows."""
    fmt = fmt or load_delivery_format()
    zero_evidence = set()
    for col in fmt.columns:
        if all(not (row.get(col, "") or "").strip() for row in examples):
            zero_evidence.add(col)
    return frozenset(zero_evidence)


# Columns that must always be populated by generation (echoed straight from
# input) — used for the structural-completeness half of tier 3.
_REQUIRED_PASSTHROUGH = ("Mfg_Part_Num", "Part_Desc")

_UNICODE_FRACTION_RE = re.compile(r"[¼-¾⅐-⅞]")
_BARE_NUMERIC_RE = re.compile(r"^\d+(-\d+/\d+)?(\.\d+)?$")


def _nonblank(row: dict[str, str], key: str) -> str:
    return (row.get(key, "") or "").strip()


# --------------------------------------------------------------------------
# Tier 2: single-row rule checks. Each function takes the generated row
# (and, where the rule needs it, the source input row) and returns
# (ok, reason). Registered against the rule id in inferred_rules.RULES so
# severity and the rule's own text travel with the check automatically.
# --------------------------------------------------------------------------

RuleChecker = Callable[[dict[str, str], Optional[dict[str, str]]], tuple[bool, str]]


def _check_invoice_max_len(row: dict[str, str], _src: Optional[dict[str, str]]) -> tuple[bool, str]:
    value = _nonblank(row, "INVOICE_DESC")
    if not value:
        return True, "INVOICE_DESC is blank, nothing to violate"
    return len(value) <= 40, f"INVOICE_DESC is {len(value)} chars (max 40): {value!r}"


def _check_invoice_uppercase(row: dict[str, str], _src: Optional[dict[str, str]]) -> tuple[bool, str]:
    value = _nonblank(row, "INVOICE_DESC")
    if not value:
        return True, "INVOICE_DESC is blank, nothing to violate"
    return value == value.upper(), f"INVOICE_DESC is not all-caps: {value!r}"


def _check_classpath_separator(row: dict[str, str], _src: Optional[dict[str, str]]) -> tuple[bool, str]:
    value = _nonblank(row, "Classpath")
    if not value:
        return True, "Classpath is blank, nothing to violate"
    parts = value.split(">")
    ok = ">" in value and " > " not in value and len(parts) == 3
    return ok, f"Classpath is not 3 levels joined by '>' with no surrounding spaces: {value!r}"


def _check_classpath_not_naive_join(row: dict[str, str], _src: Optional[dict[str, str]]) -> tuple[bool, str]:
    classpath = _nonblank(row, "Classpath")
    dept, cls, fine = _nonblank(row, "Dept"), _nonblank(row, "Class"), _nonblank(row, "Fine")
    if not (classpath and dept and cls and fine):
        return True, "Classpath or Dept/Class/Fine incomplete, nothing to compare"
    naive = f"{dept}>{cls}>{fine}"
    ok = classpath != naive
    return ok, f"Classpath looks like a naive Dept>Class>Fine join rather than real category taxonomy: {classpath!r}"


def _check_attribute_uom_bare_numeric(row: dict[str, str], _src: Optional[dict[str, str]]) -> tuple[bool, str]:
    bad_slots = []
    for i in range(1, 51):
        uom = _nonblank(row, f"ATTRIBUTE_UOM {i}")
        value = _nonblank(row, f"ATTRIBUTE_VALUE {i}")
        if uom and not _BARE_NUMERIC_RE.match(value):
            bad_slots.append((i, value, uom))
    if not bad_slots:
        return True, "no violations"
    detail = "; ".join(f"slot {i}: value={v!r} uom={u!r}" for i, v, u in bad_slots)
    return False, f"ATTRIBUTE_UOM set for a non-bare-numeric VALUE: {detail}"


def _check_ascii_fractions(row: dict[str, str], _src: Optional[dict[str, str]]) -> tuple[bool, str]:
    hits = [v for v in row.values() if v and _UNICODE_FRACTION_RE.search(v)]
    if not hits:
        return True, "no unicode vulgar fractions found"
    return False, f"found unicode vulgar fraction character(s) in: {hits[:3]!r}"


def _check_passthrough_placeholders_preserved(
    row: dict[str, str], src: Optional[dict[str, str]]
) -> tuple[bool, str]:
    if src is None:
        return True, "no source input row provided, skipping"
    for col in ("E1_Brand", "Unilog_Brand", "DIB_Brand"):
        expected = (src.get(col, "") or "").strip()
        actual = _nonblank(row, col)
        if expected and actual != expected:
            return False, f"{col} was altered: input {expected!r} -> output {actual!r}"
    return True, "brand passthrough columns unchanged from input"


def _check_attribute_labels_no_holes(row: dict[str, str], _src: Optional[dict[str, str]]) -> tuple[bool, str]:
    filled = [i for i in range(1, 51) if _nonblank(row, f"ATTRIBUTE_LABEL {i}")]
    expected_run = list(range(1, len(filled) + 1))
    ok = not filled or filled == expected_run
    return ok, f"filled attribute slots are not contiguous from 1: {filled}"


def _check_number_unit_spacing(row: dict[str, str], _src: Optional[dict[str, str]]) -> tuple[bool, str]:
    violations = []
    for field_name, value in row.items():
        if field_name in SPACING_RULE_EXEMPT_FIELDS or not value:
            continue
        hits = find_spacing_violations(value)
        if hits:
            violations.append(f"{field_name}={value!r} ({hits})")
    if not violations:
        return True, "no number-unit spacing violations"
    return False, f"missing space between number and unit: {'; '.join(violations[:5])}"


def _check_dishwasher_attribute_scaffold(
    row: dict[str, str], src: Optional[dict[str, str]]
) -> tuple[bool, str]:
    part_desc = (src or {}).get("Part_Desc", "") if src is not None else row.get("Part_Desc", "")
    if not is_dishwasher(part_desc):
        return True, "not a dishwasher row, scaffold check not applicable"
    actual = tuple(_nonblank(row, f"ATTRIBUTE_LABEL {i}") for i in range(1, 16))
    if actual != DISHWASHER_ATTRIBUTE_LABELS:
        return False, (
            f"dishwasher ATTRIBUTE_LABEL 1-15 does not match the confirmed scaffold: "
            f"{actual} != {DISHWASHER_ATTRIBUTE_LABELS}"
        )
    extra = [i for i in range(16, 51) if _nonblank(row, f"ATTRIBUTE_LABEL {i}")]
    if extra:
        return False, f"dishwasher row has labels beyond the confirmed 15-slot scaffold at slots {extra}"
    return True, "matches the confirmed dishwasher attribute scaffold"


def _check_compound_dimension_uom_blank(row: dict[str, str], _src: Optional[dict[str, str]]) -> tuple[bool, str]:
    violations = []
    for i in range(1, 51):
        value = _nonblank(row, f"ATTRIBUTE_VALUE {i}")
        uom = _nonblank(row, f"ATTRIBUTE_UOM {i}")
        if value and uom and is_compound_dimension(value):
            violations.append(f"slot {i}: value={value!r} uom={uom!r}")
    if not violations:
        return True, "no compound-dimension values with a populated UOM"
    return False, f"UOM should be blank for compound dimension values: {'; '.join(violations)}"


# Rule id -> checker. Severity comes from RULES_BY_ID[rule_id].confidence:
# high == fail, medium/low == warn. A rule id here that isn't in
# inferred_rules.RULES is a bug, so this is asserted at import time below.
TIER2_CHECKS: dict[str, RuleChecker] = {
    "invoice_desc.max_len_40": _check_invoice_max_len,
    "invoice_desc.uppercase": _check_invoice_uppercase,
    "classpath.gt_separator": _check_classpath_separator,
    "classpath.differs_from_dept_class_fine": _check_classpath_not_naive_join,
    "attributes.uom_only_for_bare_numeric_values": _check_attribute_uom_bare_numeric,
    "formatting.ascii_fractions": _check_ascii_fractions,
    "passthrough.placeholders_preserved": _check_passthrough_placeholders_preserved,
    "attributes.slots_contiguous": _check_attribute_labels_no_holes,
    "uom.number_unit_spacing": _check_number_unit_spacing,
    "uom.compound_dimension_uom_blank": _check_compound_dimension_uom_blank,
    "attributes.dishwasher_scaffold_15_labels": _check_dishwasher_attribute_scaffold,
}

_unknown_rule_ids = set(TIER2_CHECKS) - set(RULES_BY_ID)
if _unknown_rule_ids:  # pragma: no cover - guards against drift, not a runtime path
    raise RuntimeError(f"TIER2_CHECKS references unknown rule ids: {_unknown_rule_ids}")

_SEVERITY_FOR_CONFIDENCE: dict[str, Status] = {"high": "fail", "medium": "warn", "low": "warn"}


# --------------------------------------------------------------------------
# Public entry point.
# --------------------------------------------------------------------------

def evaluate_row(
    generated: dict[str, str],
    expected: Optional[dict[str, str]] = None,
    source_input: Optional[dict[str, str]] = None,
    row_id: str = "",
    fmt: Optional[DeliveryFormat] = None,
    zero_evidence_columns: Optional[frozenset[str]] = None,
) -> EvalResult:
    """Run all applicable tiers against one generated delivery-format row.

    `expected`       — one of the 2 known example rows, if this row is one of
                        them. Enables tier 1. None for the other 998.
    `source_input`    — the original 6-column input row this was generated
                         from. Enables the passthrough/completeness checks.
    `zero_evidence_columns` — precomputed via derive_zero_evidence_columns();
                         computed on the fly from load_worked_examples() if
                         omitted (costs one extra CSV read per call — pass it
                         in for batch runs).
    """
    fmt = fmt or load_delivery_format()
    checks: list[CheckResult] = []

    # --- Tier 1: exact match against a known row ---
    if expected is not None:
        for col in fmt.columns:
            exp_val = (expected.get(col, "") or "").strip()
            act_val = (generated.get(col, "") or "").strip()
            if exp_val == act_val:
                checks.append(CheckResult(tier=1, check_id=col, status="pass", reason="exact match"))
            else:
                checks.append(
                    CheckResult(
                        tier=1,
                        check_id=col,
                        status="fail",
                        reason="value does not match known example",
                        expected=exp_val,
                        actual=act_val,
                    )
                )

    # --- Tier 2: rule compliance, single row ---
    for rule_id, checker in TIER2_CHECKS.items():
        rule = RULES_BY_ID[rule_id]
        ok, reason = checker(generated, source_input)
        if ok:
            checks.append(CheckResult(tier=2, check_id=rule_id, status="pass", reason=reason))
        else:
            severity = _SEVERITY_FOR_CONFIDENCE[rule.confidence]
            checks.append(
                CheckResult(
                    tier=2,
                    check_id=rule_id,
                    status=severity,
                    reason=f"[{rule.rule}] {reason}",
                )
            )

    # --- Tier 3: honesty check ---
    zero_evidence = zero_evidence_columns
    if zero_evidence is None:
        zero_evidence = derive_zero_evidence_columns(load_worked_examples(), fmt)

    for col in sorted(zero_evidence):
        value = _nonblank(generated, col)
        if value:
            checks.append(
                CheckResult(
                    tier=3,
                    check_id=col,
                    status="fail",
                    reason=(
                        f"'{col}' has ZERO evidence in either worked example but the "
                        f"generated row filled it in — this looks fabricated"
                    ),
                    actual=value,
                )
            )
        else:
            checks.append(CheckResult(tier=3, check_id=col, status="pass", reason="correctly left blank"))

    if source_input is not None:
        for col in _REQUIRED_PASSTHROUGH:
            value = _nonblank(generated, col)
            expected_value = _nonblank(source_input, col)
            if not value and expected_value:
                checks.append(
                    CheckResult(
                        tier=3,
                        check_id=f"required:{col}",
                        status="fail",
                        reason=f"'{col}' has real input data but was left blank in generation",
                        expected=expected_value,
                    )
                )
            else:
                checks.append(
                    CheckResult(tier=3, check_id=f"required:{col}", status="pass", reason="populated")
                )

    # --- Tier 3 (continued): manufacturer/brand honesty ---
    # Only applicable when there's no known ground truth for this row (expected
    # is None) — the 2 known rows DO have real MANUFACTURER_NAME/BRAND_NAME
    # values (from external lookup, see inferred_rules.
    # manufacturer.not_derivable_from_part_manuf), so this check would be wrong
    # to apply to them. For every other row, no lookup mechanism exists, so a
    # populated MANUFACTURER_NAME/BRAND_NAME is a fabrication by construction.
    if source_input is not None and expected is None:
        resolution = resolve_manufacturer(source_input)
        fabricated = [c for c in ("MANUFACTURER_NAME", "BRAND_NAME") if _nonblank(generated, c)]
        if fabricated:
            checks.append(
                CheckResult(
                    tier=3,
                    check_id="manufacturer_brand.unresolved_without_lookup",
                    status="fail",
                    reason=(
                        f"{', '.join(fabricated)} populated for a row with no known ground "
                        f"truth and no external lookup performed ({resolution.confidence_label})"
                        " — this looks fabricated"
                    ),
                    actual="; ".join(f"{c}={_nonblank(generated, c)!r}" for c in fabricated),
                )
            )
        else:
            checks.append(
                CheckResult(
                    tier=3,
                    check_id="manufacturer_brand.unresolved_without_lookup",
                    status="pass",
                    reason=f"manufacturer/brand correctly left blank ({resolution.confidence_label})",
                )
            )

    # --- Tier 3 (continued): description factual consistency ---
    # A description field asserting a number nowhere else on this row (no
    # ATTRIBUTE_VALUE, no Mfg_Part_Num/Part_Desc, no BRAND_NAME/
    # MANUFACTURER_NAME) is a number the generator invented — the same
    # self-consistency logic description_builder.generate_descriptions()
    # already runs against its own prompt inputs, re-applied here at the
    # row level so it catches ANY generated row, not only ones produced by
    # that module. See description_builder.find_invented_numbers.
    row_trusted_fields: dict[str, str] = {
        "Mfg_Part_Num": _nonblank(generated, "Mfg_Part_Num"),
        "Part_Desc": _nonblank(generated, "Part_Desc"),
        "BRAND_NAME": _nonblank(generated, "BRAND_NAME"),
        "MANUFACTURER_NAME": _nonblank(generated, "MANUFACTURER_NAME"),
    }
    for i in range(1, 51):
        value = _nonblank(generated, f"ATTRIBUTE_VALUE {i}")
        if value:
            row_trusted_fields[f"ATTRIBUTE_VALUE {i}"] = value

    number_violations = find_invented_numbers(generated, row_trusted_fields)
    if number_violations:
        detail = "; ".join(f"{field}={nums}" for field, nums in number_violations.items())
        checks.append(
            CheckResult(
                tier=3,
                check_id="description.no_invented_numbers",
                status="fail",
                reason=(
                    "a description field states a number not traceable to any "
                    f"ATTRIBUTE_VALUE, Mfg_Part_Num, Part_Desc, BRAND_NAME or "
                    f"MANUFACTURER_NAME on this row: {detail}"
                ),
            )
        )
    else:
        checked_fields = [f for f in DESCRIPTION_FIELDS if _nonblank(generated, f)]
        checks.append(
            CheckResult(
                tier=3,
                check_id="description.no_invented_numbers",
                status="pass",
                reason=(
                    f"every number in {checked_fields} traces back to a real field on this row"
                    if checked_fields
                    else "no description fields populated, nothing to check"
                ),
            )
        )

    return EvalResult(row_id=row_id or generated.get("Mfg_Part_Num", ""), checks=tuple(checks))


def evaluate_rows(
    rows: list[tuple[dict[str, str], Optional[dict[str, str]], Optional[dict[str, str]], str]],
    fmt: Optional[DeliveryFormat] = None,
) -> list[EvalResult]:
    """Batch form of evaluate_row. Each item is (generated, expected, source_input, row_id)."""
    fmt = fmt or load_delivery_format()
    zero_evidence = derive_zero_evidence_columns(load_worked_examples(), fmt)
    return [
        evaluate_row(
            generated=generated,
            expected=expected,
            source_input=source_input,
            row_id=row_id,
            fmt=fmt,
            zero_evidence_columns=zero_evidence,
        )
        for generated, expected, source_input, row_id in rows
    ]
