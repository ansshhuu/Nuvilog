import { AlertCircle, RotateCw } from 'lucide-react'

import { cn } from '@/lib/utils'

/** A single shimmering placeholder bar. */
export function SkeletonBar({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn('block h-3 animate-pulse bg-surface', className)}
    />
  )
}

/**
 * Placeholder rows shaped like the content they stand in for, so the panel
 * does not visibly change size when the real data lands.
 *
 * aria-busy + a live label rather than silent bars: a screen reader user gets
 * told the panel is loading instead of hearing nothing at all.
 */
export function SkeletonRows({
  rows = 5,
  className,
  label = 'Loading',
}: {
  rows?: number
  className?: string
  label?: string
}) {
  return (
    <div role="status" aria-busy="true" aria-label={label} className={cn('px-5 py-4', className)}>
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-4 border-b border-border py-3">
          <SkeletonBar className="w-[18%]" />
          <SkeletonBar className="w-[26%]" />
          <SkeletonBar className="w-[16%]" />
          <SkeletonBar className="w-[30%]" />
        </div>
      ))}
    </div>
  )
}

/**
 * A failure that stays inside its panel. The rest of the app keeps working —
 * a product list that failed to load should not take the review panel with it.
 */
export function InlineError({
  message,
  onRetry,
  className,
}: {
  message: string
  onRetry?: () => void
  className?: string
}) {
  return (
    <div
      role="alert"
      className={cn(
        'm-4 flex items-start gap-3 border border-status-unverified/40 bg-status-unverified/5 px-4 py-3',
        className,
      )}
    >
      <AlertCircle
        size={13}
        strokeWidth={1.75}
        className="mt-px shrink-0 text-status-unverified"
      />
      <div className="flex min-w-0 flex-col items-start gap-2">
        <p className="font-mono text-2xs leading-relaxed text-text-primary">
          {message}
        </p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="flex items-center gap-1.5 border border-border px-2.5 py-1 font-sans text-3xs uppercase tracking-[0.14em] text-text-muted transition-colors hover:border-text-muted hover:text-text-primary"
          >
            <RotateCw size={10} strokeWidth={1.75} />
            Retry
          </button>
        )}
      </div>
    </div>
  )
}

/** Neutral "nothing here" state, for an empty but successful response. */
export function EmptyNotice({
  message,
  className,
}: {
  message: string
  className?: string
}) {
  return (
    <p
      className={cn(
        'px-5 py-8 text-center font-mono text-2xs leading-relaxed text-text-muted',
        className,
      )}
    >
      {message}
    </p>
  )
}
