import { FileSearch, X } from 'lucide-react'

import { cn } from '@/lib/utils'
import { STATUS_VAR } from '@/lib/status'
import {
  confidenceRationale,
  sourceContext,
  type ReviewField,
} from '@/lib/fields'
import { InlineError, SkeletonBar } from './Feedback'

export interface SourceTableRow {
  item: string
  specification: string
  /** Links the row back to a product field so it can be highlighted. */
  fieldName?: string
}

export interface SourceTable {
  /** e.g. "Page 1 - Table 1" */
  label: string | null
  rows: SourceTableRow[]
}

export interface SourceSnippetPanelProps {
  /** Null renders the empty state. */
  field: ReviewField | null
  sourceTable?: SourceTable | null
  onClose?: () => void
  loading?: boolean
  error?: string | null
  className?: string
}

function SectionHeading({ children }: { children: string }) {
  return (
    <h3 className="mb-2 font-sans text-3xs uppercase tracking-[0.18em] text-text-muted">
      {children}
    </h3>
  )
}

function EmptyState() {
  return (
    // py-12 rather than flex-1: the panel sizes to its content now, and an
    // unpadded empty state would collapse into a thin sliver.
    <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 py-12 text-center">
      <FileSearch size={16} strokeWidth={1.5} className="text-text-muted" />
      <p className="font-mono text-2xs leading-relaxed text-text-muted">
        Select a field to see its source
      </p>
    </div>
  )
}

function SnippetTable({
  table,
  activeFieldName,
  statusColor,
}: {
  table: SourceTable
  activeFieldName: string
  statusColor: string
}) {
  return (
    <table className="w-full table-fixed border-collapse border border-border font-mono text-3xs">
      <thead>
        <tr className="bg-surface text-text-muted">
          <th className="border-b border-r border-border px-1.5 py-1.5 text-left font-normal uppercase tracking-[0.04em]">
            Item
          </th>
          <th className="border-b border-border px-1.5 py-1.5 text-left font-normal uppercase tracking-[0.04em]">
            Specification
          </th>
        </tr>
      </thead>
      <tbody>
        {table.rows.map((row, i) => {
          const isActive = row.fieldName === activeFieldName
          return (
            <tr
              key={`${row.item}-${i}`}
              // Subtle tint in the field's own status color; the solid left
              // edge carries the signal for anyone who can't see the tint.
              style={
                isActive
                  ? {
                      backgroundColor: `color-mix(in srgb, ${statusColor} 14%, transparent)`,
                      boxShadow: `inset 2px 0 0 0 ${statusColor}`,
                    }
                  : undefined
              }
            >
              <td
                className={cn(
                  'border-b border-r border-border break-words px-2 py-1.5 align-top',
                  isActive ? 'text-text-primary' : 'text-text-muted',
                )}
              >
                {row.item}
              </td>
              <td
                className={cn(
                  'border-b border-border break-words px-2 py-1.5 align-top',
                  isActive ? 'text-text-primary' : 'text-text-muted',
                )}
              >
                {row.specification}
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

export function SourceSnippetPanel({
  field,
  sourceTable,
  onClose,
  loading = false,
  error = null,
  className,
}: SourceSnippetPanelProps) {
  const context = field ? sourceContext(field) : null

  return (
    <aside
      aria-label="Source snippet"
      // min-h-0 so the scrolling body below can actually shrink: without it a
      // flex child defaults to min-height:auto and refuses to go below its
      // content, which turns `overflow-y-auto` into clipping instead of scroll.
      className={cn(
        'flex min-h-0 min-w-0 flex-col border border-border bg-background',
        className,
      )}
    >
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 className="font-sans text-3xs uppercase tracking-[0.18em] text-text-muted">
          Source Snippet
        </h2>
        <button
          type="button"
          aria-label="Close source panel"
          onClick={onClose}
          disabled={!field}
          className="text-text-muted transition-colors hover:text-text-primary disabled:opacity-30 disabled:hover:text-text-muted"
        >
          <X size={12} strokeWidth={1.75} />
        </button>
      </div>

      {error ? (
        <InlineError message={error} />
      ) : loading ? (
        <div
          role="status"
          aria-busy="true"
          aria-label="Loading source"
          className="flex flex-col gap-2 px-4 py-4"
        >
          <span className="sr-only">Loading source</span>
          <SkeletonBar className="mb-2 h-2 w-1/2" />
          <SkeletonBar className="h-16 w-full" />
          <SkeletonBar className="mt-4 h-2 w-1/3" />
          <SkeletonBar className="h-2 w-full" />
          <SkeletonBar className="h-2 w-4/5" />
        </div>
      ) : !field ? (
        <EmptyState />
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
          <p className="mb-3 break-words font-mono text-3xs text-text-muted">
            {field.sourceLabel ?? 'Source location unavailable'}
          </p>

          {sourceTable && sourceTable.rows.length > 0 ? (
            <SnippetTable
              table={sourceTable}
              activeFieldName={field.fieldName}
              statusColor={STATUS_VAR[field.status]}
            />
          ) : (
            <p className="border border-border bg-surface px-3 py-3 font-mono text-3xs leading-relaxed text-text-muted">
              No source table available for this field.
            </p>
          )}

          <div className="mt-6">
            <SectionHeading>Context</SectionHeading>
            {context ? (
              <p className="font-mono text-2xs leading-relaxed text-text-primary">
                {context}
              </p>
            ) : (
              <p className="font-mono text-2xs leading-relaxed text-text-muted">
                No supporting text was found in the source document.
              </p>
            )}
          </div>

          <div className="mt-6">
            <SectionHeading>Confidence Rationale</SectionHeading>
            <p className="font-mono text-2xs leading-relaxed text-text-primary">
              {confidenceRationale(field)}
            </p>
          </div>
        </div>
      )}
    </aside>
  )
}
