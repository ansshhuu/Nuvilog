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
  /** Approval request in flight — the button is disabled while true. */
  approving?: boolean
  /** The selected product's status is already "approved". */
  approved?: boolean
  /** Mark-for-review request in flight. */
  marking?: boolean
  /** The selected product's status is already "needs_review". */
  markedForReview?: boolean
  /** Shared by both transitions — only one can be in flight at a time. */
  actionError?: string | null
  /** No product selected yet, so the actions have nothing to act on. */
  disabled?: boolean
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
  disabled,
  active = false,
}: {
  icon: typeof Flag
  label: string
  onClick?: () => void
  disabled?: boolean
  /** The state this button sets is the product's current state. */
  active?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'flex shrink-0 items-center gap-2 whitespace-nowrap border bg-transparent px-4 py-2.5 font-sans text-2xs uppercase tracking-[0.14em] transition-colors disabled:hover:bg-transparent',
        // Outlined in the inferred amber rather than filled: this is a flag
        // asking for attention, not a completed action like approval, so it
        // should not carry the same visual weight as the primary button.
        active
          ? 'border-status-inferred text-status-inferred disabled:opacity-100'
          : 'border-border text-text-primary hover:border-text-muted hover:bg-surface disabled:opacity-40 disabled:hover:border-border',
      )}
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
  approving = false,
  approved = false,
  marking = false,
  markedForReview = false,
  actionError = null,
  disabled = false,
  className,
}: BottomActionBarProps) {
  const total = STATUSES.reduce((sum, status) => sum + counts[status], 0)

  return (
    // Two bands, as in the mockup: the read-only tallies read left to right on
    // top, and the actions sit on their own row at the right so the primary
    // button lands in the bottom-right corner instead of competing with the
    // legend for the same line. Each band wraps independently.
    <div
      className={cn(
        'border-t border-border bg-background px-8 py-4',
        className,
      )}
    >
      {/* Baseline across the two zones too. Each zone is a flex container whose
          own baseline comes from its first item — the ZoneLabel — so aligning
          them on the baseline lines the two headings up exactly, regardless of
          the zones ending up different heights. */}
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-3">
        <div className="flex min-w-0 flex-wrap items-baseline gap-x-4 gap-y-2">
          <ZoneLabel>Confidence Legend</ZoneLabel>
          <div className="flex items-baseline gap-4">
            {STATUSES.map((status) => (
              <span key={status} className="flex items-baseline gap-2">
                {/* self-center takes the dot out of baseline alignment, so the
                    pair's baseline is taken from the label text instead of a
                    circle with no text in it — while the dot still sits
                    optically centred against that text. */}
                <StatusDot status={status} className="self-center" />
                <span className="font-mono text-3xs leading-none tracking-[0.06em] text-text-muted">
                  {STATUS_LABEL[status]}
                </span>
              </span>
            ))}
          </div>
        </div>

        {/* self-center: the rule has no text, so a baseline would pin its
            bottom edge to the text baseline and hang it above the row. */}
        <span
          aria-hidden
          className="hidden h-4 w-px shrink-0 self-center bg-border lg:block"
        />

        <div className="flex min-w-0 flex-wrap items-baseline gap-x-4 gap-y-2">
          <ZoneLabel>Field Summary</ZoneLabel>
          {/* items-baseline, not items-center: each pair sets an 11px count
              beside a 9px label, and centering two different type sizes leaves
              them visibly off by a pixel. Sitting them on a shared baseline is
              what makes the row read as one grid line. leading-none keeps each
              line box tight to the glyphs so the baselines the browser solves
              for are the ones you can see. */}
          <div className="flex items-baseline gap-4 font-mono text-3xs leading-none tracking-[0.06em]">
            {STATUSES.map((status) => (
              <span key={status} className="flex items-baseline gap-1.5">
                <span
                  className={cn('text-xs leading-none', STATUS_TEXT_CLASS[status])}
                >
                  {counts[status]}
                </span>
                <span className="leading-none text-text-muted">
                  {/* Pluralised only for contradictions, as in the mockup. */}
                  {status === 'contradiction'
                    ? 'CONTRADICTIONS'
                    : STATUS_LABEL[status]}
                </span>
              </span>
            ))}
            <span className="flex items-baseline gap-1.5">
              <span className="text-xs leading-none text-text-primary">
                {total}
              </span>
              <span className="leading-none text-text-muted">TOTAL</span>
            </span>
          </div>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-end gap-3">
        {actionError && (
          <p
            role="alert"
            className="mr-auto font-mono text-3xs leading-relaxed text-status-unverified"
          >
            {actionError}
          </p>
        )}

        <OutlineButton
          icon={Flag}
          label={
            markedForReview
              ? 'Marked for Review'
              : marking
                ? 'Marking…'
                : 'Mark for Review'
          }
          onClick={onMarkForReview}
          // Also blocked while approving: both write the same column, so
          // letting them race would leave the row on whichever landed last.
          disabled={disabled || marking || approving || markedForReview}
          active={markedForReview}
        />
        <OutlineButton
          icon={Download}
          label="Export"
          onClick={onExport}
          disabled={disabled}
        />
        <button
          type="button"
          onClick={onApprove}
          disabled={disabled || approving || marking || approved}
          className={cn(
            'flex shrink-0 items-center gap-2 whitespace-nowrap border px-5 py-2.5 font-sans text-2xs font-medium uppercase tracking-[0.14em] transition-opacity',
            // Approved is a state, not a disabled action: it keeps a solid fill
            // in the verbatim green so the bar reads as "done", rather than
            // going grey and looking like the button failed.
            approved
              ? 'border-status-verbatim bg-status-verbatim text-background'
              : 'border-accent bg-accent text-background hover:opacity-90 disabled:opacity-50',
          )}
        >
          <Check size={12} strokeWidth={2.25} />
          {approved
            ? 'Approved'
            : approving
              ? 'Approving…'
              : 'Approve Product'}
        </button>
      </div>
    </div>
  )
}
