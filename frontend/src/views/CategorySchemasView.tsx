import { useEffect, useMemo, useState } from 'react'
import { Plus, ShieldCheck } from 'lucide-react'

import { fetchCategories } from '@/lib/api'
import { useAsync } from '@/lib/useAsync'
import { InlineError, SkeletonRows } from '@/components/Feedback'
import {
  SchemaListHeaderRow,
  SchemaListRow,
  type SchemaSummary,
} from '@/components/settings/SchemaListRow'

const ADD_FIELD_NOT_IMPLEMENTED =
  'Not yet implemented — edit schemas/*.yaml directly'

/**
 * Settings > Category Schemas: a read view onto the same registry
 * `GET /api/categories` feeds to the ingest form. Confirmed directly against
 * backend/main.py::list_categories — it really does return each field's full
 * definition (name/type/required/description/unit/valid_range), not just
 * category names, so the field table below is real data, not invented.
 *
 * "+ Add Field" and every "..." menu are disabled: backend/main.py has no
 * write route for categories or fields, and schema_registry.py has no write
 * path at all — schemas are read from YAML once at process start.
 */
export function CategorySchemasView() {
  const categories = useAsync((signal) => fetchCategories(signal), 'categories')

  const schemas: SchemaSummary[] = useMemo(
    () =>
      Object.entries(categories.data ?? {}).map(([id, category]) => ({
        id,
        displayName: category.display_name,
        description: category.description,
        fields: category.fields,
        // GET /api/categories carries no edit-history timestamp — the
        // registry loads YAML at process start and does not track it.
        lastUpdated: null,
      })),
    [categories.data],
  )

  const [expandedId, setExpandedId] = useState<string | null>(null)

  // One row open by default, as soon as there is a row to open — the first
  // in registry order, since nothing in the response marks one as primary.
  useEffect(() => {
    if (expandedId === null && schemas.length > 0) {
      setExpandedId(schemas[0].id)
    }
  }, [schemas, expandedId])

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
        {categories.error ? (
          <InlineError message={categories.error} onRetry={categories.reload} />
        ) : categories.loading ? (
          <SkeletonRows rows={6} label="Loading category schemas" />
        ) : (
          <div role="table" aria-label="Category schemas" className="border border-border">
            <SchemaListHeaderRow />
            <div role="rowgroup">
              {schemas.map((schema) => (
                <SchemaListRow
                  key={schema.id}
                  schema={schema}
                  expanded={schema.id === expandedId}
                  onToggle={() =>
                    setExpandedId((current) =>
                      current === schema.id ? null : schema.id,
                    )
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
