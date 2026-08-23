/**
 * Explanatory copy for the precise/technical status terms used across all 4
 * screens. Applied via the app's existing tooltip idiom — a `title`
 * attribute — never a new tooltip mechanism.
 */
export const TERM_TOOLTIPS = {
  VERBATIM: 'Found exactly as written in the source document.',
  INFERRED: 'Not stated directly, but reasonably derived from context.',
  UNVERIFIED: 'No supporting evidence found — flagged for review, not a guess.',
  CONTRADICTION: 'Two sources disagree on this value.',
  NOT_BUILT:
    "No ground truth available to verify against — intentionally not generated rather than guessed.",
  TIER_1: 'Exact match against verified ground truth.',
  TIER_2: 'Compliance with the generation rules, independent of ground truth.',
  TIER_3: 'Honesty check — flags fabricated values not backed by evidence.',
} as const
