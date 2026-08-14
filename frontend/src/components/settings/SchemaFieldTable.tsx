import { Check } from 'lucide-react'

import { cn } from '@/lib/utils'
import { OverflowMenu } from './OverflowMenu'
import type { SchemaFieldDTO } from '@/lib/api-types'

/**
 * "1 - 100 mm" from `valid_range` + `unit` — both live on FieldDef in
 * backend/pipeline/schema_registry.py, so this only formats what the
 * registry actually stores.
 */
function formatRange(field: SchemaFieldDTO): string {
  const { valid_range, unit } = field
  if (!valid_range || (valid_range.min === null && valid_range.max === null)) {
    return '—'
  }
  const { min, max } = valid_range
  const suffix = unit ? ` ${unit}` : ''
  if (min !== null && max !== null) return `${min} - ${max}${suffix}`
  if (min !== null) return `≥ ${min}${suffix}`
  return `≤ ${max}${suffix}`
}

const COL =
  'grid grid-cols-[minmax(0,1.3fr)_100px_88px_minmax(0,1.1fr)_minmax(0,1.6fr)_minmax(0,1.6fr)_32px] items-start gap-x-4'

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
        Field Name
      </span>
      <span role="columnheader" className="min-w-0 truncate">
        Type
      </span>
      <span role="columnheader" className="min-w-0 truncate">
        Required
      </span>
      <span role="columnheader" className="min-w-0 truncate">
        Valid Range
      </span>
      <span role="columnheader" className="min-w-0 truncate">
        Valid Values
      </span>
      <span role="columnheader" className="min-w-0 truncate">
        Description
      </span>
      <span role="columnheader" aria-hidden className="min-w-0" />
    </div>
  )
}

function FieldRow({ field }: { field: SchemaFieldDTO }) {
  return (
    <div
      role="row"
      className={cn(COL, 'border-b border-border px-5 py-2.5 last:border-b-0')}
    >
      <span role="cell" className="min-w-0 break-words font-mono text-2xs text-text-primary">
        {field.name}
      </span>

      <span role="cell" className="min-w-0 font-mono text-2xs uppercase text-text-muted">
        {field.type}
      </span>

      <span role="cell" className="min-w-0">
        {field.required ? (
          <Check
            size={13}
            strokeWidth={2}
            aria-label="Required"
            className="text-status-verbatim"
          />
        ) : (
          <span aria-label="Not required" className="text-text-muted">
            —
          </span>
        )}
      </span>

      <span role="cell" className="min-w-0 font-mono text-2xs text-text-muted">
        {formatRange(field)}
      </span>

      {/* schema_registry.py's FieldDef has no enum/allowed-values concept —
          only `valid_range` — so this column has nothing real to show yet.
          Left in place (rather than dropped) so the row shape matches the
          spec and starts rendering real data the day the registry gains it. */}
      <span role="cell" className="min-w-0 whitespace-normal break-words font-mono text-2xs leading-relaxed text-text-muted">
        —
      </span>

      <span
        role="cell"
        title={field.description}
        className="min-w-0 truncate font-sans text-2xs leading-relaxed text-text-muted"
      >
        {field.description || '—'}
      </span>

      <OverflowMenu label={field.name} iconSize={13} />
    </div>
  )
}

export interface SchemaFieldTableProps {
  fields: SchemaFieldDTO[]
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
          <FieldRow key={field.name} field={field} />
        ))}
      </div>
    </div>
  )
}
