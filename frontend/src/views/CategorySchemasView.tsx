import { useMemo } from 'react'
import { Plus, ShieldCheck } from 'lucide-react'

import { cn } from '@/lib/utils'
import { fetchCategories } from '@/lib/api'
import { useAsync } from '@/lib/useAsync'
import type { SchemaFieldDTO } from '@/lib/api-types'
import { InlineError, SkeletonRows } from '@/components/Feedback'

/** Renders a `ValidRange` as the compact form the mockup shows in a table cell. */
function formatRange(field: SchemaFieldDTO): string {
  const { valid_range } = field
  if (!valid_range || (valid_range.min === null && valid_range.max === null)) {
    return '—'
  }
  const { min, max } = valid_range
  if (min !== null && max !== null) return `${min}–${max}`
  if (min !== null) return `≥ ${min}`
  return `≤ ${max}`
}

function SchemaFieldRow({ field }: { field: SchemaFieldDTO }) {
  return (
    <tr className="border-b border-border last:border-b-0">
      <td className="whitespace-nowrap px-4 py-2.5 font-mono text-2xs text-text-primary">
        {field.name}
      </td>
      <td className="whitespace-nowrap px-4 py-2.5 font-mono text-2xs text-text-muted">
        {field.type}
      </td>
      <td className="whitespace-nowrap px-4 py-2.5">
        {field.required ? (
          <span className="font-sans text-3xs uppercase tracking-[0.14em] text-status-inferred">
            Required
          </span>
        ) : (
          <span className="font-sans text-3xs uppercase tracking-[0.14em] text-text-muted">
            Optional
          </span>
        )}
      </td>
      <td className="whitespace-nowrap px-4 py-2.5 font-mono text-2xs text-text-muted">
        {field.unit ?? '—'}
      </td>
      <td className="whitespace-nowrap px-4 py-2.5 font-mono text-2xs text-text-muted">
        {formatRange(field)}
      </td>
      <td className="px-4 py-2.5 font-mono text-2xs leading-relaxed text-text-muted">
        {field.description || '—'}
      </td>
    </tr>
  )
}

function SchemaCard({
  categoryId,
  displayName,
  description,
  fields,
}: {
  categoryId: string
  displayName: string
  description: string
  fields: SchemaFieldDTO[]
}) {
  return (
    <section
      aria-label={displayName}
      className="border border-border bg-background"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-border px-4 py-3">
        <div className="flex min-w-0 items-baseline gap-3">
          <h2 className="font-mono text-sm font-medium text-text-primary">
            {displayName}
          </h2>
          <span className="font-mono text-3xs text-text-muted">
            {categoryId}
          </span>
        </div>
        <span className="font-sans text-3xs uppercase tracking-[0.14em] text-text-muted">
          {fields.length} {fields.length === 1 ? 'field' : 'fields'}
        </span>
      </div>

      {description && (
        <p className="border-b border-border px-4 py-2.5 font-sans text-2xs leading-relaxed text-text-muted">
          {description}
        </p>
      )}

      {fields.length === 0 ? (
        <p className="px-4 py-6 font-mono text-2xs text-text-muted">
          No fields defined for this category yet.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b border-border text-left">
                {['Field', 'Type', 'Required', 'Unit', 'Valid Range', 'Description'].map(
                  (heading) => (
                    <th
                      key={heading}
                      className="whitespace-nowrap px-4 py-2 font-sans text-3xs font-normal uppercase tracking-[0.14em] text-text-muted"
                    >
                      {heading}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {fields.map((field) => (
                <SchemaFieldRow key={field.name} field={field} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

/**
 * Settings > Category Schemas: a read view onto the same registry
 * `GET /api/categories` feeds to the ingest form — the schema fields
 * (name/type/required/unit/range) live in backend/schemas/*.yaml, not in this
 * component, hence the "data-driven" badge rather than a claim this page
 * invented.
 *
 * "+ Add Field" has no backend endpoint yet (schema_registry.py has no write
 * path), so it renders but does nothing — same posture as IngestView's
 * "Ingest Guide" button.
 */
export function CategorySchemasView() {
  const categories = useAsync((signal) => fetchCategories(signal), 'categories')

  const entries = useMemo(
    () => Object.entries(categories.data ?? {}),
    [categories.data],
  )

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
          className="flex shrink-0 items-center gap-2 border border-accent px-4 py-2.5 font-sans text-2xs uppercase tracking-[0.14em] text-accent transition-colors hover:bg-accent/10"
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

      <div className="mt-6 flex flex-col gap-5 pb-2">
        {categories.error ? (
          <InlineError message={categories.error} onRetry={categories.reload} />
        ) : categories.loading ? (
          <SkeletonRows rows={6} label="Loading category schemas" />
        ) : (
          entries.map(([categoryId, category]) => (
            <SchemaCard
              key={categoryId}
              categoryId={categoryId}
              displayName={category.display_name}
              description={category.description}
              fields={category.fields}
            />
          ))
        )}
      </div>
    </div>
  )
}
