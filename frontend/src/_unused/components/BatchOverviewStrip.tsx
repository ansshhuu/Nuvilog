import { Plus } from 'lucide-react'

import { cn } from '@/lib/utils'
import { STATUS_TEXT_CLASS, statusShares, type Status } from '@/lib/status'
import { StatusDotGrid } from '@/components/StatusDotGrid'
import { InlineError, SkeletonBar } from '@/components/Feedback'

export interface BatchSummary {
  id: string
  name: string
  fieldStatuses: Status[]
}

export interface BatchOverviewStripProps {
  batches: BatchSummary[]
  selectedBatchId?: string
  onSelectBatch?: (id: string) => void
  onAddBatch?: () => void
  loading?: boolean
  error?: string | null
  className?: string
}

interface BatchCardProps {
  batch: BatchSummary
  isSelected: boolean
  onSelect?: (id: string) => void
}

function BatchCard({ batch, isSelected, onSelect }: BatchCardProps) {
  const shares = statusShares(batch.fieldStatuses)

  return (
    <button
      type="button"
      aria-pressed={isSelected}
      onClick={() => onSelect?.(batch.id)}
      className={cn(
        'flex w-[124px] shrink-0 flex-col gap-3 border bg-surface p-3 text-left transition-colors',
        isSelected
          ? 'border-selected'
          : 'border-border hover:border-text-muted',
      )}
    >
      <span className="truncate font-mono text-2xs tracking-[0.06em] text-text-primary">
        {batch.name}
      </span>

      <StatusDotGrid statuses={batch.fieldStatuses} columns={9} />

      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        {shares.map(({ status, percent }) => (
          <span
            key={status}
            className={cn(
              'font-mono text-3xs tracking-[0.04em]',
              STATUS_TEXT_CLASS[status],
            )}
          >
            {percent}%
          </span>
        ))}
      </div>
    </button>
  )
}

function AddBatchCard({ onClick }: { onClick?: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-[124px] shrink-0 flex-col items-center justify-center gap-2 border border-dashed border-border bg-transparent p-3 text-text-muted transition-colors hover:border-text-muted hover:text-text-primary"
    >
      <Plus size={14} strokeWidth={1.75} />
      <span className="font-sans text-2xs uppercase tracking-[0.14em]">
        Add Batch
      </span>
    </button>
  )
}

/** Card-shaped placeholder, so the strip keeps its height while loading. */
function SkeletonCard() {
  return (
    <div className="flex w-[124px] shrink-0 flex-col gap-3 border border-border bg-surface p-3">
      <SkeletonBar className="h-2.5 w-4/5" />
      <SkeletonBar className="h-10 w-full" />
      <SkeletonBar className="h-2 w-3/5" />
    </div>
  )
}

export function BatchOverviewStrip({
  batches,
  selectedBatchId,
  onSelectBatch,
  onAddBatch,
  loading = false,
  error = null,
  className,
}: BatchOverviewStripProps) {
  return (
    <section
      aria-label="Batch overview"
      className={cn('min-w-0 border-b border-border px-8 py-5', className)}
    >
      <h2 className="mb-3 font-sans text-2xs uppercase tracking-[0.18em] text-text-muted">
        Batch Overview
      </h2>

      {error ? (
        // No retry here: the product list below owns the same request and
        // offers the retry, so two buttons would fire duplicate fetches.
        <InlineError message={error} className="m-0" />
      ) : (
        /* Scrolls horizontally on overflow — cards never wrap. */
        <div
          className="flex items-stretch gap-3 overflow-x-auto pb-1"
          aria-busy={loading || undefined}
        >
          {loading
            ? Array.from({ length: 8 }, (_, i) => <SkeletonCard key={i} />)
            : batches.map((batch) => (
                <BatchCard
                  key={batch.id}
                  batch={batch}
                  isSelected={batch.id === selectedBatchId}
                  onSelect={onSelectBatch}
                />
              ))}
          <AddBatchCard onClick={onAddBatch} />
        </div>
      )}
    </section>
  )
}
