import { useMemo, useState } from 'react'
import { ChevronLeft, ChevronRight, ListFilter, Search } from 'lucide-react'

import { cn } from '@/lib/utils'
import { STATUS_TEXT_CLASS, statusShares, type Status } from '@/lib/status'
import { StatusDot } from './StatusDot'

const PAGE_SIZE = 7

export interface ProductSummary {
  id: string
  name: string
  fieldStatuses: Status[]
}

export interface ProductListProps {
  products: ProductSummary[]
  selectedId?: string
  onSelect?: (id: string) => void
  onFilterClick?: () => void
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
        aria-current={isSelected ? 'true' : undefined}
        onClick={() => onSelect?.(product.id)}
        className={cn(
          'flex w-full flex-col gap-1 border-l-2 px-4 py-3 text-left transition-colors',
          isSelected
            ? 'border-l-selected bg-surface'
            : 'border-l-transparent hover:bg-surface/60',
        )}
      >
        <span className="truncate font-mono text-xs font-medium tracking-[0.04em] text-text-primary">
          {product.id}
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
          <ListFilter size={12} strokeWidth={1.75} />
        </button>
      </div>

      <ul className="min-h-0 flex-1 overflow-y-auto">
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
            No products match "{query}"
          </li>
        )}
      </ul>

      <Pagination
        page={currentPage}
        pageCount={pageCount}
        onChange={setPage}
      />
    </section>
  )
}
