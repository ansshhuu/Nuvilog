import { useState } from 'react'
import { Bolt, Hexagon } from 'lucide-react'

import { cn } from '@/lib/utils'
import type { ReviewField } from '@/lib/fields'
import { FieldReviewTable } from './FieldReviewTable'
import { ProductSchematic } from './ProductSchematic'
import { InlineError, SkeletonRows } from './Feedback'

const TABS = [
  { id: 'fields', label: 'Field Review' },
  { id: 'sources', label: 'Sources' },
  { id: 'notes', label: 'Notes' },
  { id: 'activity', label: 'Activity' },
] as const

type TabId = (typeof TABS)[number]['id']

export interface ProductReviewPanelProps {
  productId: string
  productName: string
  category: string
  templateName: string
  fields: ReviewField[]
  sourceCount?: number
  noteCount?: number
  selectedFieldName?: string
  onFieldSelect?: (field: ReviewField) => void
  loading?: boolean
  error?: string | null
  onRetry?: () => void
  className?: string
}

function StubPanel({ label }: { label: string }) {
  return (
    <p className="px-5 py-10 font-mono text-2xs text-text-muted">
      {label} — not built yet.
    </p>
  )
}

export function ProductReviewPanel({
  productId,
  productName,
  category,
  templateName,
  fields,
  sourceCount,
  noteCount,
  selectedFieldName,
  onFieldSelect,
  loading = false,
  error = null,
  onRetry,
  className,
}: ProductReviewPanelProps) {
  const [activeTab, setActiveTab] = useState<TabId>('fields')

  const tabCounts: Partial<Record<TabId, number | undefined>> = {
    sources: sourceCount,
    notes: noteCount,
  }

  return (
    <section
      aria-label="Product review"
      className={cn(
        'flex min-h-0 min-w-0 flex-col border border-border bg-background',
        className,
      )}
    >
      <div className="px-5 pb-4 pt-4">
        {/* Metadata row. The template and the schematic live up here with
            "REVIEWING" rather than beside the title: they are fixed-width and
            were taking roughly 370px of a ~585px header, which squeezed the
            title into ~130px and truncated it after two words. Moving them off
            that row is what actually gives the name room — shrinking the
            drawing alone could not free enough. */}
        {/* Wraps rather than crushing: the panel is drag-resizable down to
            320px, and on one line the template label was truncating to nothing
            and butting against the drawing. Given its own line it stays
            legible at any width. */}
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <div className="flex min-w-0 items-center gap-2 text-text-muted">
            <Hexagon size={12} strokeWidth={1.75} className="shrink-0" />
            <span className="shrink-0 font-sans text-3xs uppercase tracking-[0.18em]">
              Reviewing:
            </span>
            <span className="truncate font-mono text-2xs tracking-[0.06em] text-text-primary">
              {productId}
            </span>
          </div>

          <div className="flex min-w-0 items-center gap-4">
            <div className="flex min-w-0 items-center gap-2 text-text-muted">
              <Bolt size={12} strokeWidth={1.75} className="shrink-0" />
              <span className="truncate font-sans text-3xs uppercase tracking-[0.16em]">
                Template Applied:
              </span>
              <span className="shrink-0 font-mono text-3xs text-text-primary">
                {templateName}
              </span>
            </div>
            {/* Visible from `lg` up. It was `xl` (1280px), which sat exactly on
                the width of a common laptop viewport — so the drawing flickered
                in and out at the one size most people actually run. Only truly
                narrow viewports drop it now, where the header has no room. */}
            <ProductSchematic className="hidden lg:flex" />
          </div>
        </div>

        <div className="mt-3 flex items-start gap-4">
          {/* Wraps to a second line before truncating. Real extracted names run
              long ("Hex Head Cap Screw, 1/4-20 x 1 in, Stainless Steel 18-8")
              and a single truncated line cut them at the first few words, which
              is exactly where the distinguishing detail lives. line-clamp-2
              still caps the header height, so a pathological name cannot push
              the tabs off screen — and `title` carries the full string for that
              case. */}
          <h1
            title={productName}
            className="line-clamp-2 min-w-0 flex-1 font-mono text-xl font-medium leading-snug tracking-[0.01em] text-text-primary"
          >
            {productName}
          </h1>
          {/* Pill is fine here — it is a tag, not a card surface. mt aligns it
              optically to the first line, not the block's centre. */}
          <span className="mt-0.5 shrink-0 rounded-full border border-status-verbatim/50 px-3 py-1 font-sans text-3xs uppercase tracking-[0.14em] text-status-verbatim">
            {category}
          </span>
        </div>
      </div>

      <div role="tablist" aria-label="Product sections" className="flex gap-6 border-b border-border px-5">
        {TABS.map(({ id, label }) => {
          const isActive = id === activeTab
          const count = tabCounts[id]
          return (
            <button
              key={id}
              type="button"
              role="tab"
              id={`tab-${id}`}
              aria-selected={isActive}
              aria-controls={`panel-${id}`}
              onClick={() => setActiveTab(id)}
              className={cn(
                'relative -mb-px border-b-2 pb-3 pt-1 font-sans text-2xs uppercase tracking-[0.14em] transition-colors',
                isActive
                  ? 'border-selected text-text-primary'
                  : 'border-transparent text-text-muted hover:text-text-primary',
              )}
            >
              {label}
              {count !== undefined && ` (${count})`}
            </button>
          )
        })}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {activeTab === 'fields' && (
          <div role="tabpanel" id="panel-fields" aria-labelledby="tab-fields">
            {error ? (
              <InlineError message={error} onRetry={onRetry} />
            ) : loading ? (
              <SkeletonRows rows={7} label="Loading field review" />
            ) : (
              <FieldReviewTable
                fields={fields}
                selectedFieldName={selectedFieldName}
                onFieldSelect={onFieldSelect}
              />
            )}
          </div>
        )}
        {activeTab === 'sources' && (
          <div role="tabpanel" id="panel-sources" aria-labelledby="tab-sources">
            <StubPanel label="Sources" />
          </div>
        )}
        {activeTab === 'notes' && (
          <div role="tabpanel" id="panel-notes" aria-labelledby="tab-notes">
            <StubPanel label="Notes" />
          </div>
        )}
        {activeTab === 'activity' && (
          <div role="tabpanel" id="panel-activity" aria-labelledby="tab-activity">
            <StubPanel label="Activity" />
          </div>
        )}
      </div>
    </section>
  )
}
