import { useCallback, useState } from 'react'
import {
  ChevronLeft,
  ChevronRight,
  Globe,
  RotateCw,
  ArrowLeft,
  ArrowRight,
  AlertCircle,
  XCircle,
  Clock,
} from 'lucide-react'

import { StatusDot } from '@/components/StatusDot'
import { fetchManufacturerEnrichment } from '@/lib/api'
import { useAsync } from '@/lib/useAsync'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Shell states
// ---------------------------------------------------------------------------

function LoadingShell() {
  return (
    <div className="flex h-full items-center justify-center">
      <span className="animate-pulse font-mono text-xs text-text-muted">
        Loading enrichment data…
      </span>
    </div>
  )
}

function ErrorShell({ message }: { message: string }) {
  return (
    <div className="flex h-full items-center justify-center">
      <span className="font-mono text-xs" style={{ color: 'var(--color-status-unverified)' }}>
        {message}
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Highlight logic
// ---------------------------------------------------------------------------
function HighlightedText({ text, snippet }: { text: string; snippet: string | null }) {
  if (!snippet || snippet.trim() === '') {
    return <>{text}</>
  }

  const index = text.indexOf(snippet)
  if (index === -1) {
    return <>{text}</>
  }

  const before = text.substring(0, index)
  const match = text.substring(index, index + snippet.length)
  const after = text.substring(index + snippet.length)

  return (
    <>
      {before}
      <span className="bg-status-verbatim/20 border border-status-verbatim text-status-verbatim font-medium">
        {match}
      </span>
      {after}
    </>
  )
}

// ---------------------------------------------------------------------------
// ManufacturerEnrichmentView
// ---------------------------------------------------------------------------

export function ManufacturerEnrichmentView({ onBack }: { onBack?: () => void }) {
  // 0-indexed record cursor
  const [record, setRecord] = useState(0)

  const result = useAsync(
    (signal) => fetchManufacturerEnrichment(record, signal),
    `mfr-enrichment-${record}`,
  )

  const handlePrev = useCallback(() => {
    if (result.data && record > 0) {
      setRecord((r) => r - 1)
    }
  }, [record, result.data])

  const handleNext = useCallback(() => {
    if (result.data && record < result.data.total - 1) {
      setRecord((r) => r + 1)
    }
  }, [record, result.data])

  if (result.loading) return <LoadingShell />
  if (result.error) return <ErrorShell message={result.error} />
  if (!result.data) return null

  const data = result.data

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* ---------------------------------------------------------------- */}
      {/* Header Area                                                     */}
      {/* ---------------------------------------------------------------- */}
      <div className="flex items-start justify-between border-b border-border bg-surface px-6 py-5 shrink-0">
        <div className="flex items-start gap-4">
          <div className="flex flex-col gap-1">
            <span className="font-sans text-xs uppercase tracking-[0.14em] text-text-muted">
              Manufacturer Enrichment
            </span>
            <div className="flex items-center gap-3">
              <h1 className="font-mono text-lg font-medium text-text-primary uppercase tracking-[0.05em]">
                {data.mpn || 'UNKNOWN MPN'}
              </h1>
            </div>
          </div>
        </div>

        <div className="flex flex-col items-end gap-2">
          {/* Status Pill */}
          {data.status === 'success' && (
            <div className="flex items-center gap-2 rounded-full border border-border px-3 py-1 bg-surface shadow-sm">
              <StatusDot status="verbatim" size="sm" />
              <span className="font-sans text-2xs uppercase tracking-[0.1em] text-status-verbatim font-medium">
                SOURCE REACHED
              </span>
            </div>
          )}
          {data.status === 'timeout' && (
            <div className="flex items-center gap-2 rounded-full border border-border px-3 py-1 bg-surface shadow-sm">
              <StatusDot status="unverified" size="sm" />
              <span className="font-sans text-2xs uppercase tracking-[0.1em] text-status-unverified font-medium">
                SOURCE UNREACHABLE (TIMEOUT)
              </span>
            </div>
          )}
          {data.status === 'not_attempted' && (
            <div className="flex items-center gap-2 rounded-full border border-border px-3 py-1 bg-surface shadow-sm">
              <span className="inline-block shrink-0 rounded-full h-2 w-2 border border-dashed border-text-muted" />
              <span className="font-sans text-2xs uppercase tracking-[0.1em] text-text-muted">
                NOT ATTEMPTED
              </span>
            </div>
          )}
          
          {data.timestamp && (
            <div className="flex items-center gap-1.5 text-text-muted">
              <Clock size={12} />
              <span className="font-mono text-xs">
                {new Date(data.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Record Pager (mimics DescriptionFormatsView) */}
      <div className="flex items-center justify-between border-b border-border bg-background px-6 py-2 shrink-0">
        <span className="font-mono text-xs text-text-muted uppercase tracking-[0.05em]">
          Record {data.record + 1} of {data.total}
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            className="flex h-8 w-8 items-center justify-center rounded-sm border border-border hover:bg-surface disabled:opacity-50 transition-colors"
            onClick={handlePrev}
            disabled={data.record === 0}
          >
            <ChevronLeft size={16} />
          </button>
          <button
            type="button"
            className="flex h-8 w-8 items-center justify-center rounded-sm border border-border hover:bg-surface disabled:opacity-50 transition-colors"
            onClick={handleNext}
            disabled={data.record === data.total - 1}
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </div>

      {/* ---------------------------------------------------------------- */}
      {/* Main Content (Two Columns)                                      */}
      {/* ---------------------------------------------------------------- */}
      <div className="flex min-h-0 flex-1">
        
        {/* LEFT COLUMN: Source Page */}
        <div className="flex min-h-0 flex-1 flex-col border-r border-border bg-background p-6">
          <span className="font-sans text-xs uppercase tracking-[0.14em] text-text-muted mb-4 shrink-0">
            Source Page
          </span>
          
          <div className="flex min-h-0 flex-1 flex-col border border-border bg-surface rounded-sm shadow-sm overflow-hidden">
            {/* Browser Chrome */}
            <div className="flex items-center gap-4 border-b border-border bg-background px-4 py-2 shrink-0">
              <div className="flex items-center gap-2 text-text-muted">
                <ArrowLeft size={14} />
                <ArrowRight size={14} />
                <RotateCw size={14} />
              </div>
              <div className="flex flex-1 items-center rounded-sm border border-border bg-surface px-3 py-1">
                <span className="font-mono text-xs text-text-primary truncate">
                  {data.url || 'about:blank'}
                </span>
              </div>
            </div>

            {/* Content Area */}
            <div className="flex-1 overflow-auto p-4 bg-background">
              {data.status === 'success' && data.page_text_excerpt ? (
                <div className="font-mono text-xs text-text-primary leading-relaxed whitespace-pre-wrap">
                  {data.page_text_excerpt}
                  <div className="mt-4 pt-4 border-t border-border">
                    <span className="text-text-muted text-xs italic">Matches highlighted below:</span>
                    {data.fields.filter(f => f.confidence === 'verbatim' && f.snippet).map((f, i) => (
                      <div key={i} className="mt-2 text-xs font-mono p-2 bg-status-verbatim/10 border border-status-verbatim/30 rounded">
                        <span className="font-bold text-status-verbatim mr-2">{f.field_name}:</span>
                        <HighlightedText text={f.snippet || ''} snippet={f.snippet} />
                      </div>
                    ))}
                  </div>
                </div>
              ) : data.status === 'timeout' ? (
                <div className="flex h-full flex-col items-center justify-center text-text-muted gap-3">
                  <AlertCircle size={24} className="text-text-muted opacity-50" />
                  <span className="font-sans text-sm">{data.error || 'Source unreachable'}</span>
                </div>
              ) : (
                <div className="flex h-full flex-col items-center justify-center text-text-muted gap-3">
                  <XCircle size={24} className="text-text-muted opacity-50" />
                  <span className="font-sans text-sm">No manufacturer URL available. Enrichment not attempted.</span>
                </div>
              )}
            </div>

            {/* Footer Row */}
            <div className="flex items-center justify-between border-t border-border bg-surface px-4 py-2 shrink-0">
              <span className="font-sans text-xs text-text-muted">
                {data.status === 'not_attempted' ? 'No Source' : 'Manufacturer Site'}
              </span>
              {data.status === 'success' && (
                <span className="font-mono text-xs font-medium text-status-verbatim">200 OK</span>
              )}
              {data.status === 'timeout' && (
                <span className="font-mono text-xs font-medium text-status-unverified">TIMEOUT</span>
              )}
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: Extracted Attributes */}
        <div className="flex min-h-0 w-[500px] shrink-0 flex-col bg-surface p-6">
          <div className="flex items-center justify-between mb-4 shrink-0">
            <span className="font-sans text-xs uppercase tracking-[0.14em] text-text-muted">
              Extracted Attributes
            </span>
            <span className="font-mono text-xs text-text-muted">
              {data.fields.filter((f) => f.confidence === 'verbatim').length} / 15 RECOVERED
            </span>
          </div>

          <div className="flex-1 overflow-auto border border-border">
            <table className="w-full text-left font-mono text-xs">
              <thead className="sticky top-0 bg-surface shadow-[0_1px_0_var(--color-border)]">
                <tr>
                  <th className="px-4 py-2 font-medium text-text-muted w-2/5">FIELD</th>
                  <th className="px-4 py-2 font-medium text-text-muted w-2/5">VALUE</th>
                  <th className="px-4 py-2 font-medium text-text-muted w-1/5">CONFIDENCE</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.fields.map((field) => (
                  <tr
                    key={field.field_name}
                    className={cn(
                      field.confidence === 'verbatim' ? 'bg-status-verbatim/[0.03]' : ''
                    )}
                  >
                    <td className="px-4 py-3 align-top">
                      <span className={cn(
                        "font-medium",
                        field.confidence === 'verbatim' ? 'text-status-verbatim' : 'text-text-primary'
                      )}>
                        {field.field_name}
                      </span>
                    </td>
                    <td className="px-4 py-3 align-top break-words">
                      {field.confidence === 'verbatim' ? (
                        <span className="text-text-primary">{field.value}</span>
                      ) : (
                        <span className="text-text-muted italic">---</span>
                      )}
                    </td>
                    <td className="px-4 py-3 align-top">
                      {field.confidence === 'verbatim' ? (
                        <div className="flex items-center gap-2">
                          <StatusDot status="verbatim" size="sm" />
                          <span className="text-status-verbatim font-medium">VERBATIM</span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-2">
                          <span className="inline-block shrink-0 rounded-full h-2 w-2 border border-dashed border-text-muted" />
                          <span className="text-text-muted">NOT RECOVERED</span>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

      </div>

      {/* ---------------------------------------------------------------- */}
      {/* Bottom Info Bar                                                 */}
      {/* ---------------------------------------------------------------- */}
      <div className="flex items-center gap-2 border-t border-border bg-surface px-6 py-3 shrink-0">
        <Globe size={14} className="text-text-muted" />
        <span className="font-sans text-xs text-text-muted">
          Sourced from manufacturer's own site per content guidelines — marketplace sources excluded by policy.
        </span>
      </div>
    </div>
  )
}
