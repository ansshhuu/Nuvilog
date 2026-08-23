import { useEffect, useMemo, useRef, useState } from 'react'
import { Plus, ShieldCheck } from 'lucide-react'

import { fetchDishwasherSchema } from '@/lib/api'
import { useAsync } from '@/lib/useAsync'
import { InlineError, SkeletonRows } from '@/components/Feedback'
import {
  SchemaListHeaderRow,
  SchemaListRow,
  type SchemaSummary,
} from '@/components/settings/SchemaListRow'

const ADD_FIELD_NOT_IMPLEMENTED =
  'Not yet implemented — edit dishwasher_schema.py directly'

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
    </div>
  )
}
