import type { Status } from '@/lib/status'

/** [verbatim, inferred, unverified, contradiction] field counts. */
export type StatusCounts = [number, number, number, number]

const ORDER: Status[] = [
  'verbatim',
  'inferred',
  'unverified',
  'contradiction',
]

/** Expands per-status counts into the flat status array the UI consumes. */
export function buildStatuses(counts: StatusCounts): Status[] {
  return ORDER.flatMap((status, i) =>
    Array.from({ length: counts[i] }, () => status),
  )
}
