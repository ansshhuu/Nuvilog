/**
 * The four confidence statuses the pipeline assigns to every extracted field.
 * Colors live in index.css as CSS custom properties so inline SVG and any
 * dynamically computed color can read them without duplicating hex values.
 */
export const STATUSES = [
  'verbatim',
  'inferred',
  'unverified',
  'contradiction',
] as const

export type Status = (typeof STATUSES)[number]

export const STATUS_VAR: Record<Status, string> = {
  verbatim: 'var(--color-status-verbatim)',
  inferred: 'var(--color-status-inferred)',
  unverified: 'var(--color-status-unverified)',
  contradiction: 'var(--color-status-contradiction)',
}

export const STATUS_TEXT_CLASS: Record<Status, string> = {
  verbatim: 'text-status-verbatim',
  inferred: 'text-status-inferred',
  unverified: 'text-status-unverified',
  contradiction: 'text-status-contradiction',
}

export type StatusCounts = Record<Status, number>

/** Tallies a status list into per-status counts, zeros included. */
export function countStatuses(statuses: Status[]): StatusCounts {
  const counts = Object.fromEntries(
    STATUSES.map((s) => [s, 0]),
  ) as StatusCounts

  for (const status of statuses) counts[status] += 1
  return counts
}

export interface StatusShare {
  status: Status
  count: number
  /** Whole-number percent; shares always total exactly 100. */
  percent: number
}

/**
 * Percent breakdown of a status list, in STATUSES order, omitting statuses
 * that never occur. Uses largest-remainder rounding so the displayed numbers
 * add up to 100 rather than 99 or 101.
 */
export function statusShares(statuses: Status[]): StatusShare[] {
  const total = statuses.length
  if (total === 0) return []

  const present = STATUSES.map((status) => ({
    status,
    count: statuses.filter((s) => s === status).length,
  })).filter((s) => s.count > 0)

  const exact = present.map((s) => (s.count / total) * 100)
  const floors = exact.map(Math.floor)
  let remainder = 100 - floors.reduce((a, b) => a + b, 0)

  // Hand the leftover points to the largest fractional parts first.
  const order = exact
    .map((value, i) => ({ i, frac: value - floors[i] }))
    .sort((a, b) => b.frac - a.frac)

  const percents = [...floors]
  for (const { i } of order) {
    if (remainder <= 0) break
    percents[i] += 1
    remainder -= 1
  }

  return present.map((s, i) => ({ ...s, percent: percents[i] }))
}

export const STATUS_LABEL: Record<Status, string> = {
  verbatim: 'VERBATIM',
  inferred: 'INFERRED',
  unverified: 'UNVERIFIED',
  contradiction: 'CONTRADICTION',
}
