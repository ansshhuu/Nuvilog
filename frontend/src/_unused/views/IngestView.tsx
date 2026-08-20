import { useMemo, useState } from 'react'
import { BookText, FileUp, Loader2 } from 'lucide-react'

import { cn } from '@/lib/utils'
import { fetchCategories, ingestBatch, ingestOne } from '@/lib/api'
import { useAsync } from '@/lib/useAsync'
import { InlineError } from '@/components/Feedback'
import { FileDropZone } from '@/components/ingest/FileDropZone'
import { CategoryChips } from '@/components/ingest/CategoryChips'
import { RecentIngestsPanel } from '@/components/ingest/RecentIngestsPanel'

const TABS = [
  { id: 'file', label: 'File Upload' },
  { id: 'text', label: 'Paste Text' },
  { id: 'url', label: 'URL' },
] as const

type TabId = (typeof TABS)[number]['id']

export interface IngestViewProps {
  /** Called after a successful ingest, to hand control back to the dashboard. */
  onIngested?: (productIds: string[]) => void
}

function SectionLabel({ children }: { children: string }) {
  return (
    <h3 className="mb-3 font-sans text-3xs uppercase tracking-[0.18em] text-text-muted">
      {children}
    </h3>
  )
}

export function IngestView({ onIngested }: IngestViewProps) {
  const [activeTab, setActiveTab] = useState<TabId>('file')
  const [files, setFiles] = useState<File[]>([])
  const [text, setText] = useState('')
  const [url, setUrl] = useState('')
  const [categoryId, setCategoryId] = useState<string | null>(null)

  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [rejected, setRejected] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // GET /api/categories — the real schema registry, not a hardcoded three.
  const categories = useAsync((signal) => fetchCategories(signal), 'categories')

  const options = useMemo(
    () =>
      Object.entries(categories.data ?? {}).map(([id, meta]) => ({
        id,
        displayName: meta.display_name,
      })),
    [categories.data],
  )

  // Whether the active tab has something to send.
  const hasInput =
    activeTab === 'file'
      ? files.length > 0
      : activeTab === 'text'
        ? text.trim().length > 0
        : url.trim().length > 0

  const canSubmit = hasInput && categoryId !== null && !submitting

  const handleIngest = async () => {
    if (!canSubmit || !categoryId) return
    setSubmitting(true)
    setSubmitError(null)
    setSuccess(null)

    try {
      let productIds: string[]

      if (activeTab === 'file') {
        if (files.length === 1) {
          // The single endpoint types the input explicitly, so the extension
          // decides which InputType this is.
          const isCsv = files[0].name.toLowerCase().endsWith('.csv')
          const result = await ingestOne({
            category: categoryId,
            inputType: isCsv ? 'csv' : 'pdf',
            file: files[0],
          })
          productIds = [result.product_id]
        } else {
          // The batch endpoint types each upload from its own filename.
          const result = await ingestBatch({ category: categoryId, files })
          productIds = result.product_ids
          if (result.failed > 0) {
            setSubmitError(
              `${result.failed} of ${result.total} items failed. ${result.succeeded} succeeded.`,
            )
          }
        }
      } else if (activeTab === 'text') {
        const result = await ingestOne({
          category: categoryId,
          inputType: 'text',
          text,
        })
        productIds = [result.product_id]
      } else {
        const result = await ingestOne({
          category: categoryId,
          inputType: 'url',
          url,
        })
        productIds = [result.product_id]
      }

      setFiles([])
      setText('')
      setUrl('')
      setSuccess(
        productIds.length === 1
          ? 'Ingested 1 product.'
          : `Ingested ${productIds.length} products.`,
      )
      onIngested?.(productIds)
    } catch (cause) {
      setSubmitError(
        cause instanceof Error ? cause.message : 'Ingest failed.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex h-full min-h-0 gap-5 overflow-y-auto px-8 py-6">
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-start justify-between gap-6">
          <div className="min-w-0">
            <h1 className="font-mono text-xl font-medium tracking-[0.02em] text-text-primary">
              INGEST NEW DATA
            </h1>
            <p className="mt-1.5 font-sans text-2xs leading-relaxed text-text-muted">
              Upload or paste data to extract and verify product information.
            </p>
          </div>

          <button
            type="button"
            className="flex shrink-0 items-center gap-2 border border-border px-4 py-2.5 font-sans text-2xs uppercase tracking-[0.14em] text-text-primary transition-colors hover:border-text-muted hover:bg-surface"
          >
            <BookText size={12} strokeWidth={1.75} />
            Ingest Guide
          </button>
        </div>

        {/* Same active-tab treatment as the dashboard's field review tabs. */}
        <div
          role="tablist"
          aria-label="Ingest input type"
          className="mt-6 flex gap-6 border-b border-border"
        >
          {TABS.map(({ id, label }) => {
            const isActive = id === activeTab
            return (
              <button
                key={id}
                type="button"
                role="tab"
                id={`ingest-tab-${id}`}
                aria-selected={isActive}
                aria-controls={`ingest-panel-${id}`}
                onClick={() => setActiveTab(id)}
                className={cn(
                  '-mb-px border-b-2 pb-3 pt-1 font-sans text-2xs uppercase tracking-[0.14em] transition-colors',
                  isActive
                    ? 'border-selected text-text-primary'
                    : 'border-transparent text-text-muted hover:text-text-primary',
                )}
              >
                {label}
              </button>
            )
          })}
        </div>

        <div className="mt-6">
          {activeTab === 'file' && (
            <div role="tabpanel" id="ingest-panel-file">
              <FileDropZone
                files={files}
                onFilesChange={setFiles}
                onRejected={setRejected}
                disabled={submitting}
              />
            </div>
          )}

          {activeTab === 'text' && (
            <div role="tabpanel" id="ingest-panel-text">
              <label htmlFor="ingest-text" className="sr-only">
                Product data to paste
              </label>
              <textarea
                id="ingest-text"
                value={text}
                onChange={(e) => setText(e.target.value)}
                disabled={submitting}
                rows={12}
                placeholder="Paste product specification text..."
                className="w-full resize-y border border-border bg-surface px-4 py-3 font-mono text-2xs leading-relaxed text-text-primary outline-none transition-colors placeholder:text-text-muted focus:border-accent"
              />
            </div>
          )}

          {activeTab === 'url' && (
            <div role="tabpanel" id="ingest-panel-url">
              <label htmlFor="ingest-url" className="sr-only">
                Product data URL
              </label>
              <input
                id="ingest-url"
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                disabled={submitting}
                placeholder="https://example.com/product-spec"
                className="w-full border border-border bg-surface px-4 py-3 font-mono text-2xs text-text-primary outline-none transition-colors placeholder:text-text-muted focus:border-accent"
              />
            </div>
          )}
        </div>

        <div className="mt-8">
          <SectionLabel>Select Category Schema</SectionLabel>
          {categories.error ? (
            <InlineError
              message={categories.error}
              onRetry={categories.reload}
              className="m-0"
            />
          ) : (
            <CategoryChips
              categories={options}
              selectedId={categoryId}
              onSelect={setCategoryId}
              loading={categories.loading}
            />
          )}
          <p className="mt-3 font-mono text-3xs text-text-muted">
            The selected schema will be used to extract and validate fields.
          </p>
        </div>

        {rejected && (
          <InlineError message={rejected} className="mx-0 mb-0 mt-6" />
        )}
        {submitError && (
          <InlineError message={submitError} className="mx-0 mb-0 mt-6" />
        )}
        {success && (
          <p
            role="status"
            className="mt-6 border border-status-verbatim/40 bg-status-verbatim/5 px-4 py-3 font-mono text-2xs text-status-verbatim"
          >
            {success}
          </p>
        )}

        <div className="mt-8 flex justify-end pb-2">
          <button
            type="button"
            onClick={handleIngest}
            disabled={!canSubmit}
            className="flex items-center gap-2 border border-accent bg-accent px-6 py-2.5 font-sans text-2xs font-medium uppercase tracking-[0.14em] text-background transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            {submitting ? (
              <Loader2 size={12} strokeWidth={2} className="animate-spin" />
            ) : (
              // Same document-upload metaphor as the drop zone mark.
              <FileUp size={12} strokeWidth={2} />
            )}
            {submitting ? 'Ingesting…' : 'Ingest'}
          </button>
        </div>
      </div>

      <RecentIngestsPanel className="w-[260px] shrink-0 self-start" />
    </div>
  )
}
