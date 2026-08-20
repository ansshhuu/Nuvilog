import { useCallback, useState } from 'react'
import {
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Minus,
} from 'lucide-react'

import { StatusDot } from '@/components/StatusDot'
import type { Status } from '@/lib/status'
import { fetchDescriptionFormats } from '@/lib/api'
import type { DescFormatDTO, DescRuleDTO, DescSourceFieldDTO } from '@/lib/api-types'
import { useAsync } from '@/lib/useAsync'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Map the backend's status string to the four-state Status type. */
function toStatus(s: string): Status {
  if (s === 'verbatim') return 'verbatim'
  if (s === 'inferred') return 'inferred'
  if (s === 'contradiction') return 'contradiction'
  return 'unverified'
}

/** The bracketed status word that MUST pair with the dot colour. */
const STATUS_WORD: Record<Status, string> = {
  verbatim: 'verified',
  inferred: 'inferred',
  unverified: 'unverified',
  contradiction: 'contradiction',
}

// ---------------------------------------------------------------------------
// StatusLegend — reused pattern, matches DashboardView status legend style
// ---------------------------------------------------------------------------

interface LegendEntry {
  status?: Status
  label: string
  dashed?: boolean
}

const LEGEND_ENTRIES: LegendEntry[] = [
  { status: 'verbatim', label: 'VERBATIM / VERIFIED' },
  { status: 'inferred', label: 'INFERRED' },
  { status: 'unverified', label: 'UNVERIFIED' },
  { status: 'contradiction', label: 'CONTRADICTION' },
  { label: 'NOT BUILT / OUT OF SCOPE', dashed: true },
]

function StatusLegend() {
  return (
    <div className="flex flex-col gap-1.5">
      {LEGEND_ENTRIES.map((entry) => (
        <div key={entry.label} className="flex items-center gap-2">
          {entry.dashed ? (
            <span
              className="inline-flex h-2 w-2 shrink-0 items-center justify-center rounded-full border border-dashed"
              style={{ borderColor: 'var(--color-text-muted)' }}
            />
          ) : (
            <StatusDot status={entry.status!} size="sm" />
          )}
          <span className="font-sans text-2xs uppercase tracking-[0.1em] text-text-muted">
            {entry.label}
          </span>
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// CharBadge
// ---------------------------------------------------------------------------

function CharBadge({
  count,
  limit,
  generated,
  withinLimit,
}: {
  count: number
  limit: string
  generated: boolean
  withinLimit: boolean
}) {
  const isOk = generated && withinLimit

  if (!generated) {
    return (
      <span
        className="inline-flex items-center px-2 py-0.5 font-mono text-xs text-text-muted"
        style={{
          border: '1px dashed var(--color-border)',
        }}
      >
        0 / {limit}
      </span>
    )
  }

  return (
    <span
      className="inline-flex items-center px-2 py-0.5 font-mono text-xs font-medium"
      style={{
        border: `1px solid ${isOk ? 'var(--color-status-verbatim)' : 'var(--color-status-unverified)'}`,
        color: isOk ? 'var(--color-status-verbatim)' : 'var(--color-status-unverified)',
      }}
    >
      {count} / {limit}
    </span>
  )
}

// ---------------------------------------------------------------------------
// PassIcon — checkmark when generated+ok, neutral dash otherwise
// ---------------------------------------------------------------------------

function PassIcon({ generated, withinLimit }: { generated: boolean; withinLimit: boolean }) {
  if (generated && withinLimit) {
    return (
      <CheckCircle2
        size={18}
        strokeWidth={1.5}
        style={{ color: 'var(--color-status-verbatim)' }}
      />
    )
  }
  // Not generated is a valid state, not an error — neutral dash/minus, not red
  return (
    <Minus
      size={18}
      strokeWidth={1.5}
      className="text-text-muted"
    />
  )
}

// ---------------------------------------------------------------------------
// FormatCard
// ---------------------------------------------------------------------------

function FormatCard({
  fmt,
  focused,
  onFocus,
}: {
  fmt: DescFormatDTO
  focused: boolean
  onFocus: () => void
}) {
  const dotStatus: Status = fmt.generated ? 'verbatim' : 'unverified'

  return (
    <div
      className={cn(
        'flex flex-col gap-2 border bg-surface p-4 transition-colors cursor-pointer',
        focused ? 'border-accent' : 'border-border hover:border-text-muted',
      )}
      onClick={onFocus}
      onFocus={onFocus}
      tabIndex={0}
      role="button"
      aria-pressed={focused}
    >
      {/* Header row */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <StatusDot status={dotStatus} size="md" />
          <span className="font-mono text-sm font-medium tracking-[0.05em] text-text-primary">
            {fmt.field}
          </span>
        </div>

        <div className="flex items-center gap-3">
          <CharBadge
            count={fmt.char_count}
            limit={fmt.char_limit}
            generated={fmt.generated}
            withinLimit={fmt.within_limit}
          />
          <PassIcon generated={fmt.generated} withinLimit={fmt.within_limit} />
        </div>
      </div>

      {/* Body */}
      {fmt.generated ? (
        <p className="font-mono text-xs text-text-primary leading-relaxed">
          {fmt.text}
        </p>
      ) : (
        <p
          className="font-sans text-xs italic"
          style={{ color: 'var(--color-text-muted)' }}
        >
          {fmt.not_generated_reason
            ? `Not generated — ${fmt.not_generated_reason}.`
            : 'Not generated.'}
        </p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// GenerationRulePanel
// ---------------------------------------------------------------------------

function GenerationRulePanel({
  fmt,
}: {
  fmt: DescFormatDTO | null
}) {
  if (!fmt) {
    return (
      <div className="flex h-full items-center justify-center">
        <span className="font-sans text-xs text-text-muted">
          Hover or focus a format card to see its rule.
        </span>
      </div>
    )
  }

  const rule: DescRuleDTO = fmt.rule

  return (
    <div className="flex flex-col gap-4">
      {/* Section heading */}
      <span className="font-sans text-2xs uppercase tracking-[0.14em] text-text-muted">
        Generation Rule
      </span>

      {/* Focused field name */}
      <span
        className="font-mono text-sm font-semibold tracking-[0.05em]"
        style={{ color: 'var(--color-accent)' }}
      >
        {fmt.field}
      </span>

      {/* Rule metadata */}
      <div className="flex flex-col gap-2">
        <RuleLine label="CHAR LIMIT" value={rule.char_limit} />
        <RuleLine label="RULE" value={rule.casing} />
        {!rule.is_authoritative && (
          <div
            className="mt-1 border-l-2 pl-3 text-xs font-sans italic"
            style={{
              borderColor: 'var(--color-status-inferred)',
              color: 'var(--color-status-inferred)',
            }}
          >
            LOW confidence — rule inferred from limited examples. Not authoritative.
          </div>
        )}
        <div className="mt-1">
          <span className="font-sans text-2xs uppercase tracking-[0.1em] text-text-muted">
            CONSTRUCTION RULE:
          </span>
          <p className="mt-1 font-sans text-xs text-text-primary leading-relaxed">
            {rule.rule}
          </p>
        </div>
        <div className="mt-1">
          <span className="font-sans text-2xs uppercase tracking-[0.1em] text-text-muted">
            EXAMPLE:
          </span>
          {fmt.text ? (
            <p className="mt-1 font-mono text-xs italic text-text-muted leading-relaxed">
              {fmt.text.length > 120 ? fmt.text.slice(0, 120) + '…' : fmt.text}
            </p>
          ) : (
            <p className="mt-1 font-sans text-xs italic text-text-muted">
              No generated example for this row.
            </p>
          )}
        </div>
      </div>

      {/* Confidence source fields */}
      <div className="flex flex-col gap-2 mt-2">
        <span className="font-sans text-2xs uppercase tracking-[0.14em] text-text-muted">
          Confidence (Source Fields)
        </span>
        <div className="flex flex-col gap-1.5">
          {fmt.source_fields.map((sf: DescSourceFieldDTO) => {
            const status = toStatus(sf.status)
            const word = STATUS_WORD[status]
            return (
              <div key={sf.field} className="flex items-center gap-2">
                <StatusDot status={status} size="sm" />
                <span
                  className="inline-flex items-center px-1.5 py-0.5 font-mono text-2xs"
                  style={{
                    border: '1px solid var(--color-border)',
                    color: 'var(--color-text-primary)',
                  }}
                >
                  {sf.field}
                </span>
                <span
                  className="font-sans text-2xs"
                  style={{ color: 'var(--color-text-muted)' }}
                >
                  [{word}]
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

function RuleLine({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2">
      <span className="font-sans text-2xs uppercase tracking-[0.1em] text-text-muted shrink-0">
        {label}:
      </span>
      <span className="font-mono text-xs text-text-primary">{value}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Shell states
// ---------------------------------------------------------------------------

function LoadingShell() {
  return (
    <div className="flex h-full items-center justify-center">
      <span className="animate-pulse font-mono text-xs text-text-muted">
        Loading description formats…
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
// DescriptionFormatsView
// ---------------------------------------------------------------------------

export function DescriptionFormatsView({ onBack }: { onBack?: () => void }) {
  // 0-indexed record cursor
  const [record, setRecord] = useState(0)
  // Which card is focused for the right panel — start with first card
  const [focusedIdx, setFocusedIdx] = useState(0)

  const result = useAsync(
    (signal) => fetchDescriptionFormats(record, signal),
    `desc-formats-${record}`,
  )

  const handlePrev = useCallback(() => {
    if (result.data && record > 0) {
      setRecord((r) => r - 1)
      setFocusedIdx(0)
    }
  }, [record, result.data])

  const handleNext = useCallback(() => {
    if (result.data && record < result.data.total - 1) {
      setRecord((r) => r + 1)
      setFocusedIdx(0)
    }
  }, [record, result.data])

  if (result.loading) return <LoadingShell />
  if (result.error) return <ErrorShell message={result.error} />
  if (!result.data) return null

  const data = result.data
  const focusedFmt = data.formats[focusedIdx] ?? null

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* ---------------------------------------------------------------- */}
      {/* Main content area                                                 */}
      {/* ---------------------------------------------------------------- */}
      <div className="flex min-h-0 flex-1 gap-0">
        {/* Left column — header + 5 cards */}
        <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-6 pr-4">
          {/* Header */}
          <div className="flex items-start justify-between gap-4">
            <div className="flex flex-col gap-1">
              <h1 className="font-sans text-xl font-semibold uppercase tracking-[0.18em] text-text-primary">
                Description Formats
              </h1>
              <p className="font-sans text-xs text-text-muted">
                <span className="font-mono text-text-primary">{data.mpn}</span>
                {' — '}
                {data.part_desc}
              </p>
            </div>

            {/* Category pill */}
            <span
              className="shrink-0 self-start px-2.5 py-1 font-sans text-2xs font-semibold uppercase tracking-[0.14em]"
              style={{
                border: '1px solid var(--color-accent)',
                color: 'var(--color-accent)',
              }}
            >
              {data.category}
            </span>
          </div>

          {/* 5 format cards */}
          <div className="flex flex-col gap-3">
            {data.formats.map((fmt, idx) => (
              <FormatCard
                key={fmt.field}
                fmt={fmt}
                focused={focusedIdx === idx}
                onFocus={() => setFocusedIdx(idx)}
              />
            ))}
          </div>
        </div>

        {/* Vertical divider */}
        <div className="w-px shrink-0 bg-border" />

        {/* Right panel — generation rule + legend */}
        <div className="flex w-[280px] shrink-0 flex-col gap-6 overflow-auto p-5">
          <GenerationRulePanel fmt={focusedFmt} />

          {/* Legend pinned to bottom */}
          <div className="mt-auto pt-4 border-t border-border">
            <StatusLegend />
          </div>
        </div>
      </div>

      {/* ---------------------------------------------------------------- */}
      {/* Bottom bar                                                        */}
      {/* ---------------------------------------------------------------- */}
      <div className="flex h-14 shrink-0 items-center justify-between border-t border-border px-6">
        {/* Back link */}
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-1.5 font-sans text-xs uppercase tracking-[0.1em] text-text-muted transition-colors hover:text-text-primary"
        >
          <ChevronLeft size={12} strokeWidth={1.75} />
          Back to Evaluation Report
        </button>

        {/* Pager */}
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handlePrev}
            disabled={record === 0}
            className={cn(
              'flex h-7 w-7 items-center justify-center border border-border transition-colors',
              record === 0
                ? 'cursor-not-allowed opacity-30'
                : 'hover:border-text-muted hover:text-text-primary',
            )}
          >
            <ChevronLeft size={11} strokeWidth={1.75} />
          </button>

          <span className="font-sans text-2xs uppercase tracking-[0.12em] text-text-muted">
            Record{' '}
            <span className="font-mono text-text-primary">
              {record + 1}
            </span>{' '}
            of{' '}
            <span className="font-mono text-text-primary">
              {data.total}
            </span>
          </span>

          <button
            type="button"
            onClick={handleNext}
            disabled={record === data.total - 1}
            className={cn(
              'flex h-7 w-7 items-center justify-center border border-border transition-colors',
              record === data.total - 1
                ? 'cursor-not-allowed opacity-30'
                : 'hover:border-text-muted hover:text-text-primary',
            )}
          >
            <ChevronRight size={11} strokeWidth={1.75} />
          </button>
        </div>

        {/* REGENERATE ALL — no real backend action exists yet, disabled with tooltip */}
        <button
          type="button"
          disabled
          title="REGENERATE ALL is not yet implemented — re-running the LLM pipeline requires a backend action not present in this version."
          className="flex items-center px-3 py-1.5 font-sans text-2xs uppercase tracking-[0.12em] cursor-not-allowed opacity-40"
          style={{
            border: '1px solid var(--color-accent)',
            color: 'var(--color-accent)',
          }}
        >
          Regenerate All
        </button>
      </div>
    </div>
  )
}
