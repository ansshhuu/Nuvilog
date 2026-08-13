import { useState } from 'react'
import { ChevronDown, ChevronRight, FileSpreadsheet, FileText } from 'lucide-react'

import { cn } from '@/lib/utils'
import { StatusDot } from '@/components/StatusDot'
import type { Status } from '@/lib/status'

/**
 * One row of ingest history.
 *
 * Nothing currently produces these: there is no jobs table and no endpoint
 * that lists past ingests (see the panel's empty state). The shape is defined
 * so the list is ready to render the moment one exists, not because data is
 * being invented to fill it.
 */
export interface RecentIngest {
  id: string
  filename: string
  /** pdf | csv | xlsx — drives the icon and its colour. */
  kind: string
  /** Preformatted for display; the backend has no timestamp for this yet. */
  timestamp: string
  /** e.g. "Processed · 128 products" */
  statusLine: string
  /** Maps onto the existing four-way status vocabulary. */
  status: Status
}

export interface RecentIngestsPanelProps {
  ingests?: RecentIngest[]
  onViewAll?: () => void
  className?: string
}

/** Colour per file type. Purely a visual key, not a status. */
const KIND_CLASS: Record<string, string> = {
  pdf: 'text-status-unverified',
  csv: 'text-status-verbatim',
  xlsx: 'text-status-inferred',
}

function KindIcon({ kind }: { kind: string }) {
  const Icon = kind === 'csv' || kind === 'xlsx' ? FileSpreadsheet : FileText
  return (
    <Icon
      size={13}
      strokeWidth={1.75}
      className={cn('mt-px shrink-0', KIND_CLASS[kind] ?? 'text-text-muted')}
    />
  )
}

function IngestRow({ ingest }: { ingest: RecentIngest }) {
  return (
    <li className="flex items-start gap-3 border-b border-border px-4 py-3">
      <KindIcon kind={ingest.kind} />

      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="truncate font-mono text-2xs text-text-primary">
          {ingest.filename}
        </span>
        <span className="font-mono text-3xs text-text-muted">
          {ingest.timestamp}
        </span>
        <span className="font-mono text-3xs text-text-muted">
          {ingest.statusLine}
        </span>
      </div>

      {/* Reuses the dashboard's dot rather than a second status vocabulary. */}
      <StatusDot status={ingest.status} className="mt-1" />
    </li>
  )
}

export function RecentIngestsPanel({
  ingests,
  onViewAll,
  className,
}: RecentIngestsPanelProps) {
  const [open, setOpen] = useState(true)
  const rows = ingests ?? []

  return (
    <aside
      aria-label="Recent ingests"
      className={cn(
        'flex min-h-0 min-w-0 flex-col border border-border bg-background',
        className,
      )}
    >
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 className="font-sans text-3xs uppercase tracking-[0.18em] text-text-muted">
          Recent Ingests
        </h2>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-label={open ? 'Collapse recent ingests' : 'Expand recent ingests'}
          className="text-text-muted transition-colors hover:text-text-primary"
        >
          <ChevronDown
            size={12}
            strokeWidth={1.75}
            className={cn('transition-transform', !open && '-rotate-90')}
          />
        </button>
      </div>

      {open && (
        <>
          {rows.length === 0 ? (
            /* Deliberately empty. The backend exposes no ingest-history
               endpoint — there is no jobs table and POST /api/ingest returns
               only the product it just created — so there is nothing truthful
               to list here yet. */
            <p className="px-4 py-8 text-center font-mono text-2xs leading-relaxed text-text-muted">
              No recent ingests yet.
            </p>
          ) : (
            <ul className="min-h-0 flex-1 overflow-y-auto">
              {rows.map((ingest) => (
                <IngestRow key={ingest.id} ingest={ingest} />
              ))}
            </ul>
          )}

          <button
            type="button"
            onClick={onViewAll}
            disabled={rows.length === 0}
            className="flex items-center justify-center gap-1.5 border-t border-border px-4 py-3 font-sans text-3xs uppercase tracking-[0.16em] text-text-muted transition-colors hover:text-text-primary disabled:opacity-40 disabled:hover:text-text-muted"
          >
            View All Ingests
            <ChevronRight size={11} strokeWidth={1.75} />
          </button>
        </>
      )}
    </aside>
  )
}
