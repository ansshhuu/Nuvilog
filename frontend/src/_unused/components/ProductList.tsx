import { useEffect, useMemo, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight, Filter, Search } from 'lucide-react'

import { cn } from '@/lib/utils'
import { STATUS_TEXT_CLASS, statusShares, type Status } from '@/lib/status'
import { StatusDot } from '@/components/StatusDot'
import { InlineError, SkeletonBar } from '@/components/Feedback'

const PAGE_SIZE = 7

export interface ProductSummary {
  /** The product's real id — a uuid — used for every request. */
  id: string
  /** Short human-readable code shown in the list; see productCode(). */
  code: string
  name: string
  fieldStatuses: Status[]
}

export interface ProductListProps {
  products: ProductSummary[]
  selectedId?: string
  onSelect?: (id: string) => void
  onFilterClick?: () => void
  loading?: boolean
  error?: string | null
  onRetry?: () => void
  className?: string
}

/** Condensed single-line version of the batch card's summary. */
function MiniStatusSummary({ statuses }: { statuses: Status[] }) {
  const shares = statusShares(statuses)

  return (
    <div className="flex items-center gap-1.5 overflow-hidden">
      {shares.map(({ status, percent }) => (
        <span key={status} className="flex shrink-0 items-center gap-1">
          <StatusDot status={status} size="xs" />
          <span
            className={cn(
              'font-mono text-3xs leading-none',
              STATUS_TEXT_CLASS[status],
            )}
          >
            {percent}%
          </span>
        </span>
      ))}
    </div>
  )
}

interface ProductRowProps {
  product: ProductSummary
  isSelected: boolean
  onSelect?: (id: string) => void
}

function ProductRow({ product, isSelected, onSelect }: ProductRowProps) {
  return (
    <li>
      <button
        type="button"
        data-product-id={product.id}
        aria-current={isSelected ? 'true' : undefined}
        onClick={() => onSelect?.(product.id)}
        // Full outline when active, matching the batch card's selected state —
        // the two panels show the same item, so they should agree on what
        // "selected" looks like. Inactive rows keep a transparent border of the
        // same width so nothing shifts by a pixel when selection moves.
        className={cn(
          'flex w-full flex-col gap-1 border px-4 py-3 text-left transition-colors',
          isSelected
            ? 'border-selected bg-surface'
            : 'border-transparent hover:bg-surface/60',
        )}
      >
        <span className="truncate font-mono text-xs font-medium tracking-[0.04em] text-text-primary">
          {product.code}
        </span>
        <span className="truncate font-mono text-2xs text-text-muted">
          {product.name}
        </span>
        <MiniStatusSummary statuses={product.fieldStatuses} />
      </button>
    </li>
  )
}

interface PaginationProps {
  page: number
  pageCount: number
  onChange: (page: number) => void
}

function Pagination({ page, pageCount, onChange }: PaginationProps) {
  const pages = Array.from({ length: pageCount }, (_, i) => i + 1)

  return (
    <div className="flex items-center justify-center gap-1 border-t border-border px-4 py-3">
      <button
        type="button"
        aria-label="Previous page"
        disabled={page === 1}
        onClick={() => onChange(page - 1)}
        className="flex h-7 w-7 items-center justify-center text-text-muted transition-colors hover:text-text-primary disabled:opacity-30 disabled:hover:text-text-muted"
      >
        <ChevronLeft size={12} strokeWidth={1.75} />
      </button>

      {pages.map((p) => (
        <button
          key={p}
          type="button"
          aria-label={`Page ${p}`}
          aria-current={p === page ? 'page' : undefined}
          onClick={() => onChange(p)}
          className={cn(
            'flex h-7 w-7 items-center justify-center border font-mono text-2xs transition-colors',
            p === page
              ? 'border-selected text-selected'
              : 'border-transparent text-text-muted hover:text-text-primary',
          )}
        >
          {p}
        </button>
      ))}

      <button
        type="button"
        aria-label="Next page"
        disabled={page === pageCount}
        onClick={() => onChange(page + 1)}
        className="flex h-7 w-7 items-center justify-center text-text-muted transition-colors hover:text-text-primary disabled:opacity-30 disabled:hover:text-text-muted"
      >
        <ChevronRight size={12} strokeWidth={1.75} />
      </button>
    </div>
  )
}

export function ProductList({
  products,
  selectedId,
  onSelect,
  onFilterClick,
  loading = false,
  error = null,
  onRetry,
  className,
}: ProductListProps) {
  const [query, setQuery] = useState('')
  const [page, setPage] = useState(1)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return products
    return products.filter(
      (p) =>
        p.id.toLowerCase().includes(q) || p.name.toLowerCase().includes(q),
    )
  }, [products, query])

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  // A shrinking result set can strand the page number past the last page.
  const currentPage = Math.min(page, pageCount)
  const visible = filtered.slice(
    (currentPage - 1) * PAGE_SIZE,
    currentPage * PAGE_SIZE,
  )

  const listRef = useRef<HTMLUListElement>(null)
  const lastSelected = useRef(selectedId)

  // Selection can arrive from outside (clicking a card in the batch strip), and
  // the item is often on another page — without this the list would highlight
  // a row nobody can see. Guarded on the id actually changing so that typing in
  // the search box, which also rebuilds `filtered`, doesn't yank the user back
  // to the selected item's page.
  useEffect(() => {
    if (selectedId === lastSelected.current) return
    lastSelected.current = selectedId
    if (!selectedId) return

    const index = filtered.findIndex((p) => p.id === selectedId)
    if (index >= 0) setPage(Math.floor(index / PAGE_SIZE) + 1)
  }, [selectedId, filtered])

  // Runs after the page above has settled, so the row exists by now.
  useEffect(() => {
    if (!selectedId) return
    listRef.current
      ?.querySelector(`[data-product-id="${CSS.escape(selectedId)}"]`)
      ?.scrollIntoView({ block: 'nearest' })
  }, [selectedId, currentPage])

  return (
    <section
      aria-label="Product list"
      className={cn(
        'flex min-h-0 min-w-0 flex-col border border-border bg-background',
        className,
      )}
    >
      <h2 className="px-4 pb-3 pt-4 font-sans text-2xs uppercase tracking-[0.18em] text-text-muted">
        Product List ({products.length})
      </h2>

      <div className="flex items-center gap-2 px-4 pb-3">
        <div className="flex min-w-0 flex-1 items-center gap-2 border border-border bg-surface px-2.5 py-2">
          <Search size={12} strokeWidth={1.75} className="shrink-0 text-text-muted" />
          <input
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setPage(1)
            }}
            placeholder="Search products..."
            aria-label="Search products"
            className="min-w-0 flex-1 bg-transparent font-mono text-2xs text-text-primary outline-none placeholder:text-text-muted"
          />
        </div>
        <button
          type="button"
          aria-label="Filter products"
          title="Filter"
          onClick={onFilterClick}
          className="flex h-[33px] w-[33px] shrink-0 items-center justify-center border border-border bg-surface text-text-muted transition-colors hover:text-text-primary"
        >
          <Filter size={12} strokeWidth={1.75} />
        </button>
      </div>

      {error ? (
        <InlineError message={error} onRetry={onRetry} />
      ) : loading ? (
        <div role="status" aria-busy="true" aria-label="Loading products" className="px-4">
          <span className="sr-only">Loading products</span>
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i} className="flex flex-col gap-1.5 py-3">
              <SkeletonBar className="w-2/3" />
              <SkeletonBar className="h-2 w-5/6" />
              <SkeletonBar className="h-2 w-1/2" />
            </div>
          ))}
        </div>
      ) : (
        <>
          <ul ref={listRef} className="min-h-0 flex-1 overflow-y-auto">
            {visible.map((product) => (
              <ProductRow
                key={product.id}
                product={product}
                isSelected={product.id === selectedId}
                onSelect={onSelect}
              />
            ))}
            {visible.length === 0 && (
              <li className="px-4 py-6 font-mono text-2xs text-text-muted">
                {query
                  ? `No products match "${query}"`
                  : 'No products have been ingested yet.'}
              </li>
            )}
          </ul>

          <Pagination
            page={currentPage}
            pageCount={pageCount}
            onChange={setPage}
          />
        </>
      )}
    </section>
  )
}
