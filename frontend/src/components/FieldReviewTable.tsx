import { ChevronRight, FileText } from 'lucide-react'

import { cn } from '@/lib/utils'
import { STATUS_LABEL, STATUS_TEXT_CLASS } from '@/lib/status'
import { formatFieldName, type ReviewField } from '@/lib/fields'
import { StatusDot } from './StatusDot'

export interface FieldReviewTableProps {
  fields: ReviewField[]
  /** `key` of the field currently shown in the right-hand source panel. */
  selectedFieldKey?: string
  onFieldSelect?: (field: ReviewField) => void
  /** Opens the contradiction detail for a contradicted field. */
  onInspectContradiction?: (field: ReviewField) => void
  className?: string
}

/**
 * Proportional tracks, every one minmax(0, …) so cells can shrink and
 * truncate rather than pushing the table wider than its column. Fixed px
 * widths here were what forced a horizontal scrollbar and let the headers
 * run together at 100% zoom.
 */
const COL =
  'grid grid-cols-[minmax(0,0.9fr)_minmax(0,1.5fr)_minmax(0,1.1fr)_minmax(0,2.1fr)] items-start gap-x-4'

function HeaderRow() {
  return (
    <div
      role="row"
      className={cn(
        COL,
        'border-b border-border px-5 py-3 font-sans text-3xs uppercase tracking-[0.16em] text-text-muted',
      )}
    >
      <span role="columnheader" className="min-w-0 truncate">
        Field
      </span>
      <span role="columnheader" className="min-w-0 truncate">
        Extracted Value
      </span>
      <span role="columnheader" className="min-w-0 truncate">
        Confidence
      </span>
      <span role="columnheader" className="min-w-0 truncate">
        Source
      </span>
    </div>
  )
}

interface FieldRowProps {
  field: ReviewField
  isSelected: boolean
  onSelect?: (field: ReviewField) => void
  onInspectContradiction?: (field: ReviewField) => void
}

function FieldRow({
  field,
  isSelected,
  onSelect,
  onInspectContradiction,
}: FieldRowProps) {
  const { status, reason, sourceLabel } = field

  const isContradiction = status === 'contradiction'

  return (
    // A div rather than a button: contradicted rows carry their own nested
    // button, and interactive content cannot be nested inside a button. The
    // role, tabIndex and key handler keep the row itself operable.
    <div
      role="row"
      tabIndex={0}
      aria-current={isSelected ? 'true' : undefined}
      onClick={() => onSelect?.(field)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSelect?.(field)
        }
      }}
      className={cn(
        COL,
        'w-full min-w-0 cursor-pointer border-b border-border px-5 py-3 text-left transition-colors',
        isSelected ? 'bg-surface' : 'hover:bg-surface/60',
      )}
    >
      <span
        role="cell"
        className="min-w-0 truncate pt-0.5 font-mono text-2xs uppercase tracking-[0.08em] text-text-muted"
      >
        {formatFieldName(field.fieldName)}
      </span>

      <span
        role="cell"
        className="min-w-0 break-words font-mono text-sm leading-snug text-text-primary"
      >
        {field.value ?? <span className="text-text-muted">—</span>}
      </span>

      <span role="cell" className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 pt-0.5">
        <StatusDot status={status} />
        <span
          className={cn(
            'min-w-0 truncate font-mono text-2xs tracking-[0.08em]',
            STATUS_TEXT_CLASS[status],
          )}
        >
          {STATUS_LABEL[status]}
        </span>

        {/* A separate affordance rather than repurposing the row click: the
            row already means "show me the source", and a contradicted field
            needs both — the evidence panel and the side-by-side comparison. */}
        {isContradiction && onInspectContradiction && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              onInspectContradiction(field)
            }}
            aria-label={`Inspect contradiction in ${formatFieldName(field.fieldName)}`}
            className="shrink-0 border border-status-contradiction/50 px-1.5 py-px font-sans text-3xs uppercase tracking-[0.12em] text-status-contradiction transition-colors hover:bg-status-contradiction/10"
          >
            Resolve
          </button>
        )}
      </span>

      <span role="cell" className="flex min-w-0 items-start gap-2">
        <FileText
          size={12}
          strokeWidth={1.75}
          className="mt-[2px] shrink-0 text-text-muted"
        />
        <span className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="truncate font-mono text-2xs text-text-primary">
            {sourceLabel ?? <span className="text-text-muted">No source</span>}
          </span>
          {reason && (
            <span className="font-mono text-3xs leading-snug text-text-muted">
              {reason}
            </span>
          )}
        </span>
        <ChevronRight
          size={12}
          strokeWidth={1.75}
          className="mt-[1px] shrink-0 text-text-muted"
        />
      </span>
    </div>
  )
}

export function FieldReviewTable({
  fields,
  selectedFieldKey,
  onFieldSelect,
  onInspectContradiction,
  className,
}: FieldReviewTableProps) {
  return (
    <div role="table" aria-label="Field review" className={cn('w-full', className)}>
      <HeaderRow />
      <div role="rowgroup">
        {fields.map((field) => (
          <FieldRow
            key={field.key}
            field={field}
            isSelected={field.key === selectedFieldKey}
            onSelect={onFieldSelect}
            onInspectContradiction={onInspectContradiction}
          />
        ))}
      </div>
      {fields.length === 0 && (
        <p className="px-5 py-8 font-mono text-2xs text-text-muted">
          No fields extracted for this product.
        </p>
      )}
    </div>
  )
}
