import { cn } from '@/lib/utils'
import type { Status } from '@/lib/status'
import { StatusDot } from './StatusDot'

export interface StatusDotGridProps {
  statuses: Status[]
  /** Dots per row before wrapping. */
  columns?: number
  className?: string
}

/**
 * One literal circle per field status, wrapping into a fixed-column grid.
 * Not a chart — the dots are the data, one per extracted field.
 */
export function StatusDotGrid({
  statuses,
  columns = 9,
  className,
}: StatusDotGridProps) {
  return (
    // w-full, not w-fit: the 1fr tracks then distribute the card's inner width
    // evenly, so the matrix fills the card edge to edge instead of clumping
    // into a narrow block on the left.
    <div
      className={cn('grid w-full justify-items-start gap-y-[3px]', className)}
      style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
    >
      {statuses.map((status, i) => (
        <StatusDot key={i} status={status} size="sm" />
      ))}
    </div>
  )
}
