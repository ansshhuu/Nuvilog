import { useEffect, useMemo, useRef, useState } from 'react'
import { ChevronRight, Plus, ShieldCheck } from 'lucide-react'

import { fetchDishwasherSchema } from '@/lib/api'
import { useAsync } from '@/lib/useAsync'
import { InlineError, SkeletonRows } from '@/components/Feedback'
import {
  SchemaListHeaderRow,
  SchemaListRow,
  type SchemaSummary,
} from '@/components/settings/SchemaListRow'
import { cn } from '@/lib/utils'
import type { NotBuiltSubTypeDTO } from '@/lib/api-types'

const ADD_FIELD_NOT_IMPLEMENTED =
  'Not yet implemented — edit dishwasher_schema.py directly'

const NOT_BUILT_COL =
  'grid grid-cols-[minmax(0,1.6fr)_100px_minmax(0,3fr)] items-start gap-x-4'

function NotBuiltRow({ entry }: { entry: NotBuiltSubTypeDTO }) {
  return (
    <div
      role="row"
      aria-disabled
      className={cn(
        NOT_BUILT_COL,
        'cursor-not-allowed border-b border-border px-5 py-3 opacity-50 last:border-b-0',
      )}
    >
      <span role="cell" className="min-w-0 truncate font-mono text-2xs font-semibold uppercase tracking-[0.08em] text-text-primary">
        {entry.sub_type}
      </span>
      <span role="cell" className="min-w-0 font-mono text-2xs text-text-muted">
        {entry.row_count === null ? '—' : `${entry.row_count} rows`}
      </span>
      <span
        role="cell"
        title={entry.reason}
        className="min-w-0 truncate font-mono text-2xs leading-relaxed text-text-muted"
      >
        {entry.reason}
      </span>
    </div>
  )
}

/**
 * Settings > Category Schemas: dishwasher-only now — this project has one
 * proven attribute scaffold (backend/pipeline/dishwasher_schema.py's
 * confirmed 15-slot label list), not a general schema registry. Backed by
 * `GET /api/dishwasher-schema`, confirmed directly against
 * backend/main.py::get_dishwasher_schema — the field list below is the real
 * DISHWASHER_ATTRIBUTE_SCAFFOLD, not invented.
 *
 * "+ Add Field" and every "..." menu are disabled: dishwasher_schema.py has
 * no write path, same posture the old fastener/electrical/plumbing screen
 * took toward schemas/*.yaml.
 */
export function CategorySchemasView() {
  const schema = useAsync((signal) => fetchDishwasherSchema(signal), 'dishwasher-schema')

  const schemas: SchemaSummary[] = useMemo(() => {
    if (!schema.data) return []
    return [
      {
        id: 'dishwasher',
        displayName: schema.data.display_name,
        description: schema.data.description,
        fields: schema.data.fields,
        // GET /api/dishwasher-schema carries no edit-history timestamp — the
        // scaffold is imported from dishwasher_schema.py at process start
        // and does not track it.
        lastUpdated: null,
      },
    ]
  }, [schema.data])

  const [expandedId, setExpandedId] = useState<string | null>(null)
  const hasAutoExpanded = useRef(false)

  // The one row open by default, the first time there is a row to open —
  // gated on a ref rather than `expandedId === null` so a user collapsing
  // the (only) row doesn't immediately reopen it. With a single schema,
  // `expandedId === null` is indistinguishable from "not yet loaded" and
  // "the user just closed it"; the ref keeps those apart.
  useEffect(() => {
    if (!hasAutoExpanded.current && schemas.length > 0) {
      hasAutoExpanded.current = true
      setExpandedId(schemas[0].id)
    }
  }, [schemas])

  const [notBuiltOpen, setNotBuiltOpen] = useState(false)
  const notBuilt = schema.data?.not_built ?? []

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto px-8 py-6">
      <div className="flex items-start justify-between gap-6">
        <div className="min-w-0">
          <h1 className="font-mono text-xl font-medium tracking-[0.02em]">
            <span className="text-text-muted">SETTINGS</span>
            <span className="mx-2 text-text-muted">/</span>
            <span className="text-text-primary">CATEGORY SCHEMAS</span>
          </h1>
        </div>

        <button
          type="button"
          disabled
          title={ADD_FIELD_NOT_IMPLEMENTED}
          className="flex shrink-0 cursor-not-allowed items-center gap-2 border border-accent px-4 py-2.5 font-sans text-2xs uppercase tracking-[0.14em] text-accent opacity-40"
        >
          <Plus size={12} strokeWidth={2} />
          Add Field
        </button>
      </div>

      <div className="mt-4">
        <span className="inline-flex items-center gap-2 border border-border px-3 py-1.5 font-sans text-3xs uppercase tracking-[0.16em] text-text-muted">
          <ShieldCheck size={11} strokeWidth={1.75} />
          Data-Driven — No Hardcoded Logic
        </span>
      </div>

      <div className="mt-6 pb-2">
        {schema.error ? (
          <InlineError message={schema.error} onRetry={schema.reload} />
        ) : schema.loading ? (
          <SkeletonRows rows={4} label="Loading category schema" />
        ) : (
          <div role="table" aria-label="Category schemas" className="border border-border">
            <SchemaListHeaderRow />
            <div role="rowgroup">
              {schemas.map((s) => (
                <SchemaListRow
                  key={s.id}
                  schema={s}
                  expanded={s.id === expandedId}
                  onToggle={() =>
                    setExpandedId((current) => (current === s.id ? null : s.id))
                  }
                />
              ))}
            </div>
          </div>
        )}
      </div>

      {!schema.loading && !schema.error && notBuilt.length > 0 && (
        <div className="pb-8">
          <button
            type="button"
            onClick={() => setNotBuiltOpen((open) => !open)}
            aria-expanded={notBuiltOpen}
            className="flex items-center gap-2 font-sans text-3xs uppercase tracking-[0.16em] text-text-muted transition-colors hover:text-text-primary"
          >
            <ChevronRight
              size={12}
              strokeWidth={1.75}
              className={cn('transition-transform duration-150', notBuiltOpen && 'rotate-90')}
            />
            Other Sub-Types — Not Built ({notBuilt.length})
          </button>

          {notBuiltOpen && (
            <div className="mt-3 border border-border">
              <div
                role="row"
                className={cn(
                  NOT_BUILT_COL,
                  'border-b border-border px-5 py-2.5 font-sans text-3xs uppercase tracking-[0.16em] text-text-muted',
                )}
              >
                <span role="columnheader">Sub-Type</span>
                <span role="columnheader">Real Rows</span>
                <span role="columnheader">Why It's Not Built</span>
              </div>
              <div role="rowgroup">
                {notBuilt.map((entry) => (
                  <NotBuiltRow key={entry.sub_type} entry={entry} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
