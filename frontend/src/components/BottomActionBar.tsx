import { Check, Download, Flag } from 'lucide-react'

import { cn } from '@/lib/utils'
import {
  STATUSES,
  STATUS_LABEL,
  STATUS_TEXT_CLASS,
  type StatusCounts,
} from '@/lib/status'
import { StatusDot } from './StatusDot'

export interface BottomActionBarProps {
  /** Per-status tallies for the selected product's fields. */
  counts: StatusCounts
  onMarkForReview?: () => void
  onExport?: () => void
  onApprove?: () => void
  className?: string
}

function ZoneLabel({ children }: { children: string }) {
  return (
    <span className="font-sans text-3xs uppercase tracking-[0.18em] text-text-muted">
      {children}
    </span>
  )
}

function OutlineButton({
  icon: Icon,
  label,
  onClick,
}: {
  icon: typeof Flag
  label: string
  onClick?: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex shrink-0 items-center gap-2 whitespace-nowrap border border-border bg-transparent px-4 py-2.5 font-sans text-2xs uppercase tracking-[0.14em] text-text-primary transition-colors hover:border-text-muted hover:bg-surface"
    >
      <Icon size={12} strokeWidth={1.75} />
      {label}
    </button>
  )
}

export function BottomActionBar({
  counts,
  onMarkForReview,
  onExport,
  onApprove,
  className,
}: BottomActionBarProps) {
  const total = STATUSES.reduce((sum, status) => sum + counts[status], 0)

  return (
    <div
      className={cn(
        // Wraps rather than overflowing when the viewport is too narrow for
        // all three zones on one line.
        'flex flex-wrap items-center justify-between gap-x-8 gap-y-3 border-t border-border bg-background px-8 py-4',
        className,
      )}
    >
      <div className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-2">
        <ZoneLabel>Confidence Legend</ZoneLabel>
        <div className="flex items-center gap-4">
          {STATUSES.map((status) => (
            <span key={status} className="flex items-center gap-2">
              <StatusDot status={status} />
              <span className="font-mono text-3xs tracking-[0.06em] text-text-muted">
                {STATUS_LABEL[status]}
              </span>
            </span>
          ))}
        </div>
      </div>

      <div className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-2">
        <ZoneLabel>Field Summary</ZoneLabel>
        <div className="flex items-center gap-4 font-mono text-3xs tracking-[0.06em]">
          {STATUSES.map((status) => (
            <span key={status} className="flex items-center gap-1.5">
              <span className={cn('text-xs', STATUS_TEXT_CLASS[status])}>
                {counts[status]}
              </span>
              <span className="text-text-muted">
                {/* Pluralised only for contradictions, as in the mockup. */}
                {status === 'contradiction'
                  ? 'CONTRADICTIONS'
                  : STATUS_LABEL[status]}
              </span>
            </span>
          ))}
          <span className="flex items-center gap-1.5">
            <span className="text-xs text-text-primary">{total}</span>
            <span className="text-text-muted">TOTAL</span>
          </span>
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-3">
        <OutlineButton
          icon={Flag}
          label="Mark for Review"
          onClick={onMarkForReview}
        />
        <OutlineButton icon={Download} label="Export" onClick={onExport} />
        <button
          type="button"
          onClick={onApprove}
          className="flex shrink-0 items-center gap-2 whitespace-nowrap border border-accent bg-accent px-5 py-2.5 font-sans text-2xs font-medium uppercase tracking-[0.14em] text-background transition-opacity hover:opacity-90"
        >
          <Check size={12} strokeWidth={2.25} />
          Approve Product
        </button>
      </div>
    </div>
  )
}
