import { useState } from 'react'
import { Bolt, Hexagon } from 'lucide-react'

import { cn } from '@/lib/utils'
import type { ReviewField } from '@/lib/fields'
import { FieldReviewTable } from './FieldReviewTable'

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
        <div className="flex items-center gap-2 text-text-muted">
          <Hexagon size={12} strokeWidth={1.75} />
          <span className="font-sans text-3xs uppercase tracking-[0.18em]">
            Reviewing:
          </span>
          <span className="font-mono text-2xs tracking-[0.06em] text-text-primary">
            {productId}
          </span>
        </div>

        <div className="mt-3 flex items-start justify-between gap-6">
          <div className="flex min-w-0 items-center gap-4">
            <h1 className="truncate font-mono text-xl font-medium tracking-[0.01em] text-text-primary">
              {productName}
            </h1>
            {/* Pill is fine here — it is a tag, not a card surface. */}
            <span className="shrink-0 rounded-full border border-status-verbatim/50 px-3 py-1 font-sans text-3xs uppercase tracking-[0.14em] text-status-verbatim">
              {category}
            </span>
          </div>

          <div className="flex shrink-0 items-center gap-2 pt-1.5 text-text-muted">
            <Bolt size={12} strokeWidth={1.75} />
            <span className="font-sans text-3xs uppercase tracking-[0.16em]">
              Template Applied:
            </span>
            <span className="font-mono text-3xs text-text-primary">
              {templateName}
            </span>
          </div>
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
            <FieldReviewTable
              fields={fields}
              selectedFieldName={selectedFieldName}
              onFieldSelect={onFieldSelect}
            />
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
