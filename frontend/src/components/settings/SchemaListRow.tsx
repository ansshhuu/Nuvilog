import { ChevronRight } from 'lucide-react'

import { cn } from '@/lib/utils'
import { categoryIcon } from '@/lib/categoryIcons'
import { OverflowMenu } from './OverflowMenu'
import { SchemaFieldTable } from './SchemaFieldTable'
import type { SchemaFieldDTO } from '@/lib/api-types'

export interface SchemaSummary {
  id: string
  displayName: string
  description: string
  fields: SchemaFieldDTO[]
  /**
   * Null rather than a fabricated date — the schema registry loads from
   * YAML on process start and does not track per-file edit history, so
   * there is no real timestamp to show yet.
   */
  lastUpdated: string | null
}

/**
 * Shared grid so the header row (below) and every data row line up. Fixed px
 * tracks for the narrow numeric column, fr tracks for the two that hold free
 * text — same split FieldReviewTable uses for the same reason.
 *
 * No Status column: confirmed against schema_registry.py that a schema has
 * no activation state at all — `all_schemas()` returns whatever loaded from
 * YAML at process start, nothing more. A hardcoded "Active" on every row
 * would assert a distinction that does not exist server-side.
 */
const COL =
  'grid grid-cols-[minmax(0,2.2fr)_minmax(0,2.4fr)_72px_140px_32px] items-center gap-x-4'

export function SchemaListHeaderRow() {
  return (
    <div
      role="row"
      className={cn(
        COL,
        'border-b border-border px-5 py-3 font-sans text-3xs uppercase tracking-[0.16em] text-text-muted',
      )}
    >
      <span role="columnheader" className="min-w-0 truncate">
        Category Schema
      </span>
      <span role="columnheader" className="min-w-0 truncate">
        Description
      </span>
      <span role="columnheader" className="min-w-0 truncate">
        Fields
      </span>
      <span role="columnheader" className="min-w-0 truncate">
        Last Updated
      </span>
      {/* Overflow menu column carries no label — same as an actions column
          with no heading elsewhere in this codebase. */}
      <span role="columnheader" aria-hidden className="min-w-0" />
    </div>
  )
}

export interface SchemaListRowProps {
  schema: SchemaSummary
  expanded: boolean
  onToggle: () => void
  className?: string
}

export function SchemaListRow({
  schema,
  expanded,
  onToggle,
  className,
}: SchemaListRowProps) {
  const Icon = categoryIcon(schema.id)

  return (
    <div className={cn('border-b border-border last:border-b-0', className)}>
      <div
        role="row"
        tabIndex={0}
        aria-expanded={expanded}
        onClick={onToggle}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            onToggle()
          }
        }}
        className={cn(
          COL,
          'w-full cursor-pointer px-5 py-3.5 text-left transition-colors hover:bg-surface/60',
        )}
      >
        <span role="cell" className="flex min-w-0 items-center gap-3">
          <ChevronRight
            size={13}
            strokeWidth={1.75}
            className={cn(
              'shrink-0 text-text-muted transition-transform duration-150',
              expanded && 'rotate-90',
            )}
          />
          <Icon size={14} strokeWidth={1.75} className="shrink-0 text-text-muted" />
          <span className="truncate font-sans text-2xs font-semibold uppercase tracking-[0.1em] text-text-primary">
            {schema.displayName}
          </span>
        </span>

        <span role="cell" className="min-w-0 truncate font-mono text-2xs text-text-muted">
          {schema.description || '—'}
        </span>

        <span role="cell" className="min-w-0 font-mono text-2xs text-text-primary">
          {schema.fields.length}
        </span>

        <span role="cell" className="min-w-0 truncate font-mono text-2xs text-text-muted">
          {schema.lastUpdated ?? '—'}
        </span>

        <OverflowMenu label={schema.displayName} />
      </div>

      {expanded && (
        <div className="border-t border-border bg-surface/40">
          <SchemaFieldTable fields={schema.fields} />
        </div>
      )}
    </div>
  )
}
