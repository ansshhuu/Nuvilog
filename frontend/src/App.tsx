import { useMemo, useState } from 'react'

import { AppShell } from '@/components/layout/AppShell'
import type { NavItemId } from '@/components/layout/Sidebar'
import { BatchOverviewStrip } from '@/components/BatchOverviewStrip'
import { ProductList } from '@/components/ProductList'
import { ProductReviewPanel } from '@/components/ProductReviewPanel'
import { BottomActionBar } from '@/components/BottomActionBar'
import { toReviewFields, type ReviewField } from '@/lib/fields'
import { countStatuses } from '@/lib/status'
import { MOCK_BATCHES } from '@/data/mockBatches'
import { MOCK_PRODUCTS } from '@/data/mockProducts'
import { SourceSnippetPanel } from '@/components/SourceSnippetPanel'
import {
  MOCK_PRODUCT_DETAIL,
  mockSourceLabelFor,
  mockSourceTableFor,
} from '@/data/mockProductDetail'

// Placeholder state — replaced by real project/user data in a later section.
const PROJECT = 'FASTENER_IMPORT_MAY'
const USER = 'ENGINEER_01'

function App() {
  const [activeItem, setActiveItem] = useState<NavItemId>('dashboard')
  const [selectedBatchId, setSelectedBatchId] = useState(MOCK_BATCHES[0].id)
  const [selectedProductId, setSelectedProductId] = useState(
    MOCK_PRODUCTS[0].id,
  )
  const [selectedField, setSelectedField] = useState<ReviewField | null>(null)

  const fields = useMemo(
    () =>
      toReviewFields(MOCK_PRODUCT_DETAIL.fields, MOCK_PRODUCT_DETAIL.flags, {
        sourceLabelFor: mockSourceLabelFor,
      }),
    [],
  )

  // Derived from the fields on screen, so the bar can never disagree with the
  // table above it.
  const counts = useMemo(
    () => countStatuses(fields.map((f) => f.status)),
    [fields],
  )

  const product = MOCK_PRODUCTS.find((p) => p.id === selectedProductId)

  return (
    <AppShell
      activeItem={activeItem}
      onNavigate={setActiveItem}
      project={PROJECT}
      user={USER}
    >
      <div className="flex h-full min-h-0 flex-col">
        <BatchOverviewStrip
          batches={MOCK_BATCHES}
          selectedBatchId={selectedBatchId}
          onSelectBatch={setSelectedBatchId}
          onAddBatch={() => {}}
        />

        {/* Fluid ratios, not fixed px — every track is minmax(0, …) so a
            column can shrink below its content instead of overflowing.

            items-start is what keeps the panels honest: grid items stretch to
            the row height by default, which is what left a tall empty block
            under a short field table. Aligned to start they size to their own
            content, and `max-h-full` caps them at the space available so a
            long product or field list scrolls internally instead of pushing
            the action bar off screen. Height is a ceiling here, never a floor. */}
        <div className="grid min-h-0 min-w-0 flex-1 grid-cols-[minmax(0,1fr)_minmax(0,3fr)_minmax(0,1.05fr)] items-start gap-4 px-8 py-5">
          <ProductList
            className="max-h-full"
            products={MOCK_PRODUCTS}
            selectedId={selectedProductId}
            onSelect={setSelectedProductId}
          />

          <ProductReviewPanel
            className="max-h-full"
            productId={MOCK_PRODUCT_DETAIL.id}
            productName={product?.name ?? ''}
            category="Fasteners"
            templateName="FASTENER_BOLT"
            fields={fields}
            sourceCount={6}
            noteCount={1}
            selectedFieldName={selectedField?.fieldName}
            onFieldSelect={setSelectedField}
          />

          <SourceSnippetPanel
            className="max-h-full"
            field={selectedField}
            sourceTable={
              selectedField ? mockSourceTableFor(selectedField.fieldName) : null
            }
            onClose={() => setSelectedField(null)}
          />
        </div>

        <BottomActionBar
          counts={counts}
          onMarkForReview={() => console.log('mark for review', selectedProductId)}
          onExport={() => console.log('export', selectedProductId)}
          onApprove={() => console.log('approve', selectedProductId)}
        />
      </div>
    </AppShell>
  )
}

export default App
