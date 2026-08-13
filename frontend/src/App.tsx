import { useCallback, useEffect, useMemo, useState } from 'react'
import { Group, Panel, Separator, type Layout } from 'react-resizable-panels'

import { AppShell } from '@/components/layout/AppShell'
import type { NavItemId } from '@/components/layout/Sidebar'
import { BatchOverviewStrip } from '@/components/BatchOverviewStrip'
import { ProductList } from '@/components/ProductList'
import { ProductReviewPanel } from '@/components/ProductReviewPanel'
import { BottomActionBar } from '@/components/BottomActionBar'
import { SourceSnippetPanel } from '@/components/SourceSnippetPanel'
import type { SourceTable } from '@/components/SourceSnippetPanel'
import { toReviewFields, formatFieldName, type ReviewField } from '@/lib/fields'
import { countStatuses } from '@/lib/status'
import {
  approveProduct,
  fetchProduct,
  fetchProducts,
  markProductForReview,
} from '@/lib/api'
import { PRODUCT_STATUS, type StatusChangeDTO } from '@/lib/api-types'
import { useAsync } from '@/lib/useAsync'
import {
  fieldStatuses,
  productCode,
  productDisplayName,
  sourceDocumentLabel,
} from '@/lib/products'

// Placeholder still: the backend has no project or user concept — no table,
// no auth. Left as constants rather than invented endpoints.
const PROJECT = 'FASTENER_IMPORT_MAY'
const USER = 'ENGINEER_01'

/** Starting split, in percent. Drag-adjusted at runtime, minimums in px. */
const DEFAULT_SIZES = { list: '18', review: '60', source: '22' }

/**
 * Drag handle between two panels. Occupies the same width the old grid `gap-4`
 * did, so the visual rhythm is unchanged — the hit target is the whole gap,
 * but only a 1px rule is painted until you approach it. Sharp corners, per the
 * house rule that nothing here is rounder than 4px.
 */
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

function App() {
  const [activeItem, setActiveItem] = useState<NavItemId>('dashboard')
  const [selectedProductId, setSelectedProductId] = useState<string | null>(null)
  const [selectedField, setSelectedField] = useState<ReviewField | null>(null)

  // Session-only panel widths. Deliberately React state and not localStorage
  // (banned here) — resizes survive re-renders, and reset on a full reload.
  const [panelLayout, setPanelLayout] = useState<Layout | undefined>(undefined)

  /** Which status transition is in flight, if any. */
  const [pendingAction, setPendingAction] = useState<
    'approve' | 'review' | null
  >(null)
  const [actionError, setActionError] = useState<string | null>(null)
  /**
   * Statuses written in this session, so the bar reflects a click immediately
   * without refetching. A map rather than a set of approved ids: the two
   * transitions are mutually exclusive, and the later one has to be able to
   * replace the earlier one for the same product.
   */
  const [statusOverrides, setStatusOverrides] = useState<
    ReadonlyMap<string, string>
  >(new Map())

  // GET /api/products — one request, on mount. Feeds both the batch strip and
  // the product list, which are two views of the same items.
  const list = useAsync((signal) => fetchProducts(signal), 'products')

  // GET /api/products/{id} — refetched whenever the selection changes. Keyed on
  // the id so an earlier slow response cannot overwrite a later one.
  const detail = useAsync(
    (signal) => fetchProduct(selectedProductId as string, signal),
    selectedProductId,
  )

  const products = useMemo(() => list.data ?? [], [list.data])

  // Select the first product once the list arrives, so the review panel has
  // something to show without a click.
  useEffect(() => {
    if (selectedProductId === null && products.length > 0) {
      setSelectedProductId(products[0].id)
    }
  }, [products, selectedProductId])

  const summaries = useMemo(
    () =>
      products.map((product) => ({
        id: product.id,
        code: productCode(product),
        name: productDisplayName(product),
        fieldStatuses: fieldStatuses(product),
      })),
    [products],
  )

  // The strip and the list render the same items by design — the strip is the
  // density health-check, the list is the selector — so they share one dataset
  // and one selected id, and selection is trivially in sync.
  const batches = useMemo(
    () =>
      summaries.map(({ id, code, fieldStatuses }) => ({
        id,
        name: code,
        fieldStatuses,
      })),
    [summaries],
  )

  const selectedSummary = summaries.find((p) => p.id === selectedProductId)
  const product = detail.data

  const fields = useMemo(() => {
    if (!product) return []
    return toReviewFields(product.fields, product.flags, {
      // Per-field page/table coordinates are not persisted, so this names the
      // source document rather than a location inside it.
      sourceLabelFor: (field) =>
        field.evidence_type === 'none' ? null : sourceDocumentLabel(product),
    })
  }, [product])

  /**
   * The product's own extracted values, rendered as the spec table in the
   * source panel with the active field highlighted. This is the real table the
   * values were read into — not a reconstruction of the source document's
   * layout, which the backend does not store.
   */
  const sourceTable: SourceTable | null = useMemo(() => {
    if (!product) return null
    return {
      label: sourceDocumentLabel(product),
      rows: product.fields.map((field) => ({
        item: formatFieldName(field.field_name),
        specification: field.value ?? '—',
        fieldName: field.field_name,
      })),
    }
  }, [product])

  const counts = useMemo(
    () => countStatuses(fields.map((f) => f.status)),
    [fields],
  )

  const handleSelectProduct = useCallback((id: string) => {
    setSelectedProductId(id)
    // The previous product's field has no meaning against the new one.
    setSelectedField(null)
    setActionError(null)
  }, [])

  /**
   * Both status transitions run through here — they differ only in which
   * endpoint they call and what they say when they fail.
   */
  const runStatusChange = useCallback(
    async (
      action: 'approve' | 'review',
      call: (id: string) => Promise<StatusChangeDTO>,
      failureMessage: string,
    ) => {
      if (!selectedProductId) return
      setPendingAction(action)
      setActionError(null)
      try {
        const result = await call(selectedProductId)
        setStatusOverrides((prev) =>
          new Map(prev).set(result.id, result.status),
        )
      } catch (cause) {
        setActionError(
          cause instanceof Error ? cause.message : failureMessage,
        )
      } finally {
        setPendingAction(null)
      }
    },
    [selectedProductId],
  )

  const handleApprove = useCallback(
    () =>
      runStatusChange('approve', approveProduct, 'Could not approve product.'),
    [runStatusChange],
  )

  const handleMarkForReview = useCallback(
    () =>
      runStatusChange(
        'review',
        markProductForReview,
        'Could not mark product for review.',
      ),
    [runStatusChange],
  )

  /**
   * Export the product as JSON, client-side.
   *
   * There is no export endpoint on the backend — this serialises the record
   * the panel is already showing rather than pretending a server-side export
   * exists. See the note in the README/handover.
   */
  const handleExport = useCallback(() => {
    if (!product) return
    const blob = new Blob([JSON.stringify(product, null, 2)], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `nuvilog-${productCode(product)}.json`
    link.click()
    URL.revokeObjectURL(url)
  }, [product])

  // A status set in this session wins over the one the fetch returned, since
  // the fetch predates the click.
  const currentStatus =
    (selectedProductId !== null
      ? statusOverrides.get(selectedProductId)
      : undefined) ?? product?.status

  return (
    <AppShell
      activeItem={activeItem}
      onNavigate={setActiveItem}
      project={PROJECT}
      user={USER}
    >
      <div className="flex h-full min-h-0 flex-col">
        <BatchOverviewStrip
          batches={batches}
          selectedBatchId={selectedProductId ?? undefined}
          onSelectBatch={handleSelectProduct}
          onAddBatch={() => {}}
          loading={list.loading}
          error={list.error}
        />

        {/* Drag-resizable columns. Minimums are in px (the library reads bare
            numbers as pixels) so no panel can be dragged to an unusable width
            regardless of window size.

            Each Panel is a full-height box; the section inside it stays
            height:auto and capped with `max-h-full`, which is what keeps the
            earlier fix intact — panels size to their own content instead of
            stretching to fill the row, and a long list scrolls internally
            rather than pushing the action bar off screen. */}
        <Group
          orientation="horizontal"
          className="min-h-0 min-w-0 flex-1 px-8 py-5"
          defaultLayout={panelLayout}
          onLayoutChanged={setPanelLayout}
        >
          <Panel
            id="product-list"
            minSize={200}
            defaultSize={DEFAULT_SIZES.list}
            className="min-h-0 min-w-0"
          >
            <ProductList
              className="max-h-full"
              products={summaries}
              selectedId={selectedProductId ?? undefined}
              onSelect={handleSelectProduct}
              loading={list.loading}
              error={list.error}
              onRetry={list.reload}
            />
          </Panel>

          <ResizeHandle />

          <Panel
            id="field-review"
            minSize={320}
            defaultSize={DEFAULT_SIZES.review}
            className="min-h-0 min-w-0"
          >
            <ProductReviewPanel
              className="max-h-full"
              // From the list, which has already loaded — so the heading does
              // not flash empty while the detail request is in flight.
              productId={selectedSummary?.code ?? '—'}
              productName={selectedSummary?.name ?? ''}
              category={product?.category ?? ''}
              templateName={(product?.category ?? '').toUpperCase()}
              fields={fields}
              // Real count: how many fields carry an evidence snippet. The
              // backend has no notes concept, so that tab shows no count
              // rather than an invented one.
              sourceCount={
                product?.fields.filter((f) => f.source_snippet).length
              }
              selectedFieldName={selectedField?.fieldName}
              onFieldSelect={setSelectedField}
              loading={detail.loading}
              error={detail.error}
              onRetry={detail.reload}
            />
          </Panel>

          <ResizeHandle />

          <Panel
            id="source-snippet"
            minSize={220}
            defaultSize={DEFAULT_SIZES.source}
            className="min-h-0 min-w-0"
          >
            <SourceSnippetPanel
              className="max-h-full"
              field={selectedField}
              sourceTable={selectedField ? sourceTable : null}
              onClose={() => setSelectedField(null)}
              loading={detail.loading}
              error={detail.error}
            />
          </Panel>
        </Group>

        <BottomActionBar
          counts={counts}
          onMarkForReview={handleMarkForReview}
          onExport={handleExport}
          onApprove={handleApprove}
          approving={pendingAction === 'approve'}
          approved={currentStatus === PRODUCT_STATUS.approved}
          marking={pendingAction === 'review'}
          markedForReview={currentStatus === PRODUCT_STATUS.needsReview}
          actionError={actionError}
          disabled={!product}
        />
      </div>
    </AppShell>
  )
}

export default App
