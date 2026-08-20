import { cn } from '@/lib/utils'
import { OverflowMenu } from './OverflowMenu'
import type { DishwasherFieldDTO } from '@/lib/api-types'

const NO_REQUIRED_CONCEPT =
  'dishwasher_schema.py carries no required-field concept — every label ' +
  'stays populated even when its value is unknown (see blank_dishwasher_scaffold()).'

const COL =
  'grid grid-cols-[48px_minmax(0,1.2fr)_84px_96px_minmax(0,2.6fr)_32px] items-start gap-x-4'

function HeaderRow() {
  return (
    <div
      role="row"
      className={cn(
        COL,
        'border-b border-border px-5 py-2.5 font-sans text-3xs uppercase tracking-[0.16em] text-text-muted',
      )}
    >
      <span role="columnheader" className="min-w-0 truncate">
        Slot
      </span>
      <span role="columnheader" className="min-w-0 truncate">
        Label
      </span>
      <span role="columnheader" className="min-w-0 truncate">
        Unit
      </span>
      <span role="columnheader" className="min-w-0 truncate" title={NO_REQUIRED_CONCEPT}>
        Required
      </span>
      <span role="columnheader" className="min-w-0 truncate">
        Evidence
      </span>
      <span role="columnheader" aria-hidden className="min-w-0" />
    </div>
  )
}

function FieldRow({ field }: { field: DishwasherFieldDTO }) {
  return (
    <div
      role="row"
      className={cn(COL, 'border-b border-border px-5 py-2.5 last:border-b-0')}
    >
      <span role="cell" className="min-w-0 font-mono text-2xs text-text-muted">
        {field.index}
      </span>

      <span role="cell" className="min-w-0 break-words font-mono text-2xs text-text-primary">
        {field.label}
      </span>

      <span role="cell" className="min-w-0 font-mono text-2xs text-text-muted">
        {field.unit ?? '—'}
      </span>

      {/* No required-field concept on this scaffold at all — not "false",
          just absent. Honest placeholder, not a fabricated boolean. */}
      <span role="cell" className="min-w-0 font-mono text-2xs text-text-muted" title={NO_REQUIRED_CONCEPT}>
        —
      </span>

      <span
        role="cell"
        className="min-w-0 whitespace-normal break-words font-mono text-2xs leading-relaxed text-text-muted"
      >
        {field.evidence}
      </span>

      <OverflowMenu
        label={field.label}
        iconSize={13}
        reason="Not yet implemented — the scaffold lives in dishwasher_schema.py, not an editable file"
      />
    </div>
  )
}

export interface SchemaFieldTableProps {
  fields: DishwasherFieldDTO[]
  className?: string
}

/** The field-definition table inside an expanded schema row. */
export function SchemaFieldTable({ fields, className }: SchemaFieldTableProps) {
  if (fields.length === 0) {
    return (
      <p className="px-5 py-6 font-mono text-2xs text-text-muted">
        No fields defined for this category yet.
      </p>
    )
  }

  return (
    <div role="table" aria-label="Field definitions" className={cn('w-full', className)}>
      <HeaderRow />
      <div role="rowgroup">
        {fields.map((field) => (
          <FieldRow key={field.index} field={field} />
        ))}
      </div>
    </div>
  )
}
