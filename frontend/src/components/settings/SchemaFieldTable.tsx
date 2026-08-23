import { useState } from 'react'
import { Group, Panel, Separator, type Layout } from 'react-resizable-panels'

import { cn } from '@/lib/utils'
import { OverflowMenu } from './OverflowMenu'
import type { DishwasherFieldDTO } from '@/lib/api-types'

const NO_REQUIRED_CONCEPT =
  'dishwasher_schema.py carries no required-field concept — every label ' +
  'stays populated even when its value is unknown (see blank_dishwasher_scaffold()).'

// Slot and the trailing overflow-menu column stay fixed width; the four
// text columns between them resize — same react-resizable-panels primitives
// as the dashboard's 3-panel split (_unused/views/DashboardView.tsx), just
// applied to table columns instead of full panes.
const OUTER_COL = 'grid grid-cols-[48px_minmax(0,1fr)_32px] items-start gap-x-4'

/** Must match ResizeHandle's rendered width so header and data rows reserve
 * the same fixed space and line up. */
const SEPARATOR_WIDTH_PX = 13

/** Starting split, in percent — approximates the old fixed-width columns. */
const DEFAULT_LAYOUT: Layout = { label: 24, unit: 12, required: 14, evidence: 50 }

/** Pixel floors so no column can be dragged to unreadable width. Label and
 * Unit hold short tokens and can go narrower; Evidence carries the most
 * text and needs the largest floor. */
const MIN_SIZES = { label: 100, unit: 56, required: 64, evidence: 180 }

/** Drag handle between two columns — identical style to the dashboard's
 * ResizeHandle (thin line, accent on hover/active/focus). */
function ResizeHandle() {
  return (
    <Separator className="group flex w-[13px] shrink-0 cursor-col-resize items-stretch justify-center outline-none">
      <span
        aria-hidden
        className="w-px bg-border transition-colors duration-100 group-hover:w-0.5 group-hover:bg-accent group-focus-visible:bg-accent group-active:bg-accent"
      />
    </Separator>
  )
}

/**
 * The same column track list the header's flex Group produces, expressed as
 * a CSS grid template. `fr` tracks split remaining space proportionally
 * after fixed-width siblings — identical math to flex-grow after
 * flex-shrink:0 separators — so a plain-grid data row lines up with the
 * flex-based header without every row needing its own Group instance.
 */
function gridTemplateFrom(layout: Layout): string {
  const gap = `${SEPARATOR_WIDTH_PX}px`
  return `${layout.label}fr ${gap} ${layout.unit}fr ${gap} ${layout.required}fr ${gap} ${layout.evidence}fr`
}

function HeaderRow({
  layout,
  onLayoutChange,
}: {
  layout: Layout
  onLayoutChange: (layout: Layout) => void
}) {
  return (
    <div
      role="row"
      className={cn(
        OUTER_COL,
        'border-b border-border px-5 py-2.5 font-sans text-3xs uppercase tracking-[0.16em] text-text-muted',
      )}
    >
      <span role="columnheader" className="min-w-0 truncate">
        Slot
      </span>

      <Group
        orientation="horizontal"
        className="min-w-0"
        defaultLayout={layout}
        onLayoutChange={onLayoutChange}
      >
        <Panel id="label" minSize={MIN_SIZES.label} defaultSize={String(DEFAULT_LAYOUT.label)} className="min-w-0">
          <span role="columnheader" className="block min-w-0 truncate">
            Label
          </span>
        </Panel>
        <ResizeHandle />
        <Panel id="unit" minSize={MIN_SIZES.unit} defaultSize={String(DEFAULT_LAYOUT.unit)} className="min-w-0">
          <span role="columnheader" className="block min-w-0 truncate">
            Unit
          </span>
        </Panel>
        <ResizeHandle />
        <Panel
          id="required"
          minSize={MIN_SIZES.required}
          defaultSize={String(DEFAULT_LAYOUT.required)}
          className="min-w-0"
        >
          <span role="columnheader" className="block min-w-0 truncate" title={NO_REQUIRED_CONCEPT}>
            Required
          </span>
        </Panel>
        <ResizeHandle />
        <Panel
          id="evidence"
          minSize={MIN_SIZES.evidence}
          defaultSize={String(DEFAULT_LAYOUT.evidence)}
          className="min-w-0"
        >
          <span role="columnheader" className="block min-w-0 truncate">
            Evidence
          </span>
        </Panel>
      </Group>

      {/* Overflow menu column carries no label — same as an actions column
          with no heading elsewhere in this codebase. */}
      <span role="columnheader" aria-hidden className="min-w-0" />
    </div>
  )
}

function FieldRow({ field, layout }: { field: DishwasherFieldDTO; layout: Layout }) {
  return (
    <div role="row" className={cn(OUTER_COL, 'border-b border-border px-5 py-2.5 last:border-b-0')}>
      <span role="cell" className="min-w-0 font-mono text-2xs text-text-muted">
        {field.index}
      </span>

      <div className="grid min-w-0 items-start" style={{ gridTemplateColumns: gridTemplateFrom(layout) }}>
        <span role="cell" className="min-w-0 break-words font-mono text-2xs text-text-primary">
          {field.label}
        </span>
        <span aria-hidden />

        <span role="cell" className="min-w-0 font-mono text-2xs text-text-muted">
          {field.unit ?? '—'}
        </span>
        <span aria-hidden />

        {/* No required-field concept on this scaffold at all — not "false",
            just absent. Honest placeholder, not a fabricated boolean. */}
        <span role="cell" className="min-w-0 font-mono text-2xs text-text-muted" title={NO_REQUIRED_CONCEPT}>
          —
        </span>
        <span aria-hidden />

        <span
          role="cell"
          className="min-w-0 whitespace-normal break-words font-mono text-2xs leading-relaxed text-text-muted"
        >
          {field.evidence}
        </span>
      </div>

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

/** The field-definition table inside an expanded schema row. Columns
 * between Slot and the overflow menu are drag-resizable; widths live in
 * React state only (not localStorage) and reset on reload, same as the
 * dashboard's panel split. */
export function SchemaFieldTable({ fields, className }: SchemaFieldTableProps) {
  const [layout, setLayout] = useState<Layout>(DEFAULT_LAYOUT)

  if (fields.length === 0) {
    return (
      <p className="px-5 py-6 font-mono text-2xs text-text-muted">
        No fields defined for this category yet.
      </p>
    )
  }

  return (
    <div role="table" aria-label="Field definitions" className={cn('w-full', className)}>
      <HeaderRow layout={layout} onLayoutChange={setLayout} />
      <div role="rowgroup">
        {fields.map((field) => (
          <FieldRow key={field.index} field={field} layout={layout} />
        ))}
      </div>
    </div>
  )
}
