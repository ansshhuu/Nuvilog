import { useMemo, useState } from 'react'
import { ChevronDown } from 'lucide-react'

import { StatusDot } from '@/components/StatusDot'
import type { Status } from '@/lib/status'
import { fetchEvaluationReport } from '@/lib/api'
import type {
  Tier3ScoreDTO,
  TierScoreDTO,
  ComparisonRowDTO,
} from '@/lib/api-types'
import { useAsync } from '@/lib/useAsync'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Map a score ratio to one of the three relevant pipeline Status values.
 *
 *  100 %  → verbatim  (green)  — perfect pass
 *  ≥ 80 % → inferred  (amber)  — partial, above the acceptable threshold
 *  < 80 % → unverified (red)   — significant gap
 *
 * This is deliberately NOT hardcoded green — per spec, dot and bar color must
 * reflect the actual score ratio.
 */
function tierStatus(score: number, total: number): Status {
  if (total === 0) return 'unverified'
  const ratio = score / total
  if (ratio >= 1) return 'verbatim'
  if (ratio >= 0.8) return 'inferred'
  return 'unverified'
}

/** CSS color var string keyed by Status — mirrors STATUS_VAR in lib/status.ts. */
const STATUS_BAR_COLOR: Record<Status, string> = {
  verbatim: 'var(--color-status-verbatim)',
  inferred: 'var(--color-status-inferred)',
  unverified: 'var(--color-status-unverified)',
  contradiction: 'var(--color-status-contradiction)',
}

/**
 * Parse "X/Y" strings from the comparison endpoint into a numeric numerator so
 * baseline vs enriched values can be compared.
 */
function parseFractionNumerator(value: string): number {
  const n = Number(value.split('/')[0])
  return isNaN(n) ? 0 : n
}

/** True only when the enriched value is strictly greater than baseline. */
function isImprovement(baseline: string, enriched: string): boolean {
  return parseFractionNumerator(enriched) > parseFractionNumerator(baseline)
}

// ---------------------------------------------------------------------------
// TierCard
// ---------------------------------------------------------------------------

/**
 * Compact stat card (~150 px tall) showing a tier's score, progress bar, and
 * optional subtitle. StatusDot + bar color are derived from the score ratio —
 * never hardcoded.
 */
function TierCard({
  tierLabel,
  tierDesc,
  score,
  total,
  subtitle,
}: {
  tierLabel: string
  tierDesc: string
  score: number
  total: number
  subtitle?: string
}) {
  const status = tierStatus(score, total)
  const pct = total > 0 ? (score / total) * 100 : 0
  const barColor = STATUS_BAR_COLOR[status]

  return (
    <div className="flex flex-1 flex-col gap-3 rounded border border-border bg-surface p-4">
      {/* Header: dot + "TIER N — DESCRIPTION" */}
      <div className="flex items-center gap-2">
        <StatusDot status={status} size="sm" />
        <span className="font-sans text-2xs uppercase tracking-[0.12em] text-text-muted">
          {tierLabel} — {tierDesc}
        </span>
      </div>

      {/* Score in medium-large mono — "210 / 252" format */}
      <div className="font-mono text-xl font-medium tracking-[0.04em] text-text-primary">
        {score} / {total}
      </div>

      {/* Thin progress bar + optional subtitle */}
      <div className="flex flex-col gap-1.5">
        <div className="relative h-1.5 overflow-hidden rounded-sm bg-border">
          <div
            className="absolute left-0 top-0 h-full rounded-sm transition-all duration-500"
            style={{ width: `${pct}%`, backgroundColor: barColor }}
          />
        </div>
        {subtitle !== undefined && (
          <span className="font-mono text-2xs text-text-muted">{subtitle}</span>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// ComparisonTable
// ---------------------------------------------------------------------------

/**
 * Before/after comparison table. The enriched value cell gets a subtle green
 * chip *only* when `enriched > baseline` numerically — this is the only place
 * a conditional highlight is applied, and it is always data-driven.
 */
function ComparisonTable({ row }: { row: ComparisonRowDTO }) {
  const metrics = [
    {
      label: 'Descriptions non-empty',
      baseline: row.descriptions_nonempty.baseline,
      enriched: row.descriptions_nonempty.enriched,
    },
    {
      label: 'Attributes verified',
      baseline: row.attributes_verified.baseline,
      enriched: row.attributes_verified.enriched,
    },
    {
      label: 'Tier 1 score',
      baseline: row.tier1_score.baseline,
      enriched: row.tier1_score.enriched,
    },
  ]

  return (
    <div className="overflow-hidden rounded border border-border bg-surface">
      {/* Column headers */}
      <div
        className="grid border-b border-border"
        style={{ gridTemplateColumns: '1fr auto 36px auto' }}
      >
        <div className="px-4 py-2.5" />
        <div className="min-w-[200px] px-6 py-2.5">
          <span className="font-sans text-2xs uppercase tracking-[0.12em] text-text-muted">
            BASELINE (NO ENRICHMENT)
          </span>
        </div>
        <div className="py-2.5" />
        <div className="min-w-[240px] px-6 py-2.5">
          <span className="font-sans text-2xs uppercase tracking-[0.12em] text-text-muted">
            ENRICHED (MANUFACTURER SOURCE)
          </span>
        </div>
      </div>

      {/* Data rows */}
      {metrics.map((m, idx) => {
        const improved = isImprovement(m.baseline, m.enriched)
        return (
          <div
            key={m.label}
            className={cn(
              'grid items-center',
              idx < metrics.length - 1 && 'border-b border-border',
            )}
            style={{ gridTemplateColumns: '1fr auto 36px auto' }}
          >
            {/* Row label — sans, regular weight */}
            <div className="px-4 py-3">
              <span className="font-sans text-xs text-text-primary">{m.label}</span>
            </div>

            {/* Baseline value — mono */}
            <div className="min-w-[200px] px-6 py-3">
              <span className="font-mono text-xs text-text-primary">{m.baseline}</span>
            </div>

            {/* Arrow divider */}
            <div className="flex items-center justify-center py-3">
              <span className="font-sans text-sm text-text-muted">→</span>
            </div>

            {/* Enriched value — green chip only when improved, plain mono otherwise */}
            <div className="min-w-[240px] px-6 py-3">
              {improved ? (
                <span
                  className="inline-block rounded px-1.5 py-0.5 font-mono text-xs font-medium"
                  style={{
                    backgroundColor:
                      'color-mix(in srgb, var(--color-status-verbatim) 18%, transparent)',
                    color: 'var(--color-status-verbatim)',
                  }}
                >
                  {m.enriched}
                </span>
              ) : (
                <span className="font-mono text-xs text-text-primary">{m.enriched}</span>
              )}
            </div>
          </div>
        )
      })}
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
        Loading evaluation report…
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
// Dropdown — shared pattern for the two header selects
// ---------------------------------------------------------------------------

/**
 * A real <select> with the app's design language overlaid.
 * `appearance-none` hides the native arrow; ChevronDown is positioned
 * absolutely. The overlay div is `pointer-events-none` so clicks still reach
 * the native <select> beneath it.
 */
function EvalSelect({
  id,
  prefixLabel,
  displayValue,
  options,
  value,
  onChange,
  minWidth,
}: {
  id: string
  prefixLabel: string
  displayValue: string
  options: { value: string }[]
  value: string
  onChange: (v: string) => void
  /** Explicit min-width in px so the control never clips its longest content. */
  minWidth: number
}) {
  return (
    <div className="relative" style={{ minWidth }}>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          'h-9 w-full appearance-none pl-3 pr-8',
          'rounded border border-border bg-surface',
          // Text is transparent so only our overlay shows, but the select
          // still receives keyboard/mouse events and stays accessible.
          'text-transparent',
          'cursor-pointer transition-colors focus:outline-none',
          'hover:border-text-muted focus:border-text-muted',
        )}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value} className="bg-surface text-text-primary">
            {opt.value}
          </option>
        ))}
      </select>

      {/* Visual overlay — whitespace-nowrap on both spans prevents any wrapping */}
      <div className="pointer-events-none absolute inset-0 flex items-center gap-1.5 pl-3 pr-7">
        <span className="shrink-0 whitespace-nowrap font-sans text-2xs uppercase tracking-[0.12em] text-text-muted">
          {prefixLabel}:
        </span>
        <span className="whitespace-nowrap font-mono text-xs tracking-[0.04em] text-text-primary">
          {displayValue}
        </span>
      </div>

      <ChevronDown
        size={11}
        strokeWidth={1.75}
        className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted"
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// EvaluationReportView
// ---------------------------------------------------------------------------

export function EvaluationReportView() {
  const report = useAsync((signal) => fetchEvaluationReport(signal), 'evaluation-report')

  // Only rows with ground truth (is_known=true) have comparison data; these
  // are the meaningful choices for the MPN dropdown.
  const knownRows = useMemo(
    () => (report.data?.rows ?? []).filter((r) => r.is_known),
    [report.data],
  )

  // Controlled selection; null means "use the first known row".
  const [selectedMpn, setSelectedMpn] = useState<string | null>(null)
  const activeMpn = selectedMpn ?? knownRows[0]?.mpn ?? null

  const activeRow = useMemo(
    () => report.data?.rows.find((r) => r.mpn === activeMpn) ?? null,
    [report.data, activeMpn],
  )

  const activeComparison = activeMpn
    ? (report.data?.comparison[activeMpn] ?? null)
    : null

  if (report.loading) return <LoadingShell />
  if (report.error) return <ErrorShell message={report.error} />
  if (!report.data) return null

  // Derive tier values with safe fallbacks so we never crash on missing data.
  const tier1: TierScoreDTO | null = activeRow?.tier1 ?? null
  const tier2: TierScoreDTO = activeRow?.tier2 ?? { score: 0, total: 11 }
  const tier3: Tier3ScoreDTO = activeRow?.tier3 ?? {
    score: 0,
    total: 176,
    fabrication_violations: 0,
  }

  const mpnOptions = knownRows.map((r) => ({ value: r.mpn }))
  const compareOptions = [{ value: 'BASELINE vs ENRICHED' }]

  return (
    <div className="flex h-full flex-col gap-5 overflow-auto p-6">
      {/* ---------------------------------------------------------------- */}
      {/* Header row                                                       */}
      {/* ---------------------------------------------------------------- */}
      <div className="flex items-center justify-between gap-4">
        <h1 className="font-sans text-xl font-semibold uppercase tracking-[0.18em] text-text-primary">
          Evaluation Report
        </h1>

        <div className="flex items-center gap-3">
          {/*
           * minWidth sized for the widest real MPN in the dataset (17 chars:
           * "WF4REGSWW590CRIMW") plus the "MFG_PART_NUM:" label prefix and
           * internal padding, measured in JetBrains Mono at 12px / 0.04em.
           * 240px accommodates that without clipping.
           */}
          <EvalSelect
            id="eval-mpn-select"
            prefixLabel="MFG_PART_NUM"
            displayValue={activeMpn ?? ''}
            options={mpnOptions}
            value={activeMpn ?? ''}
            onChange={setSelectedMpn}
            minWidth={240}
          />
          {/*
           * minWidth sized for "COMPARE: BASELINE vs ENRICHED" — the longest
           * possible content in this control. 288px fits on one line at 10px
           * uppercase Inter + 12px mono with the current padding.
           */}
          <EvalSelect
            id="eval-compare-select"
            prefixLabel="COMPARE"
            displayValue="BASELINE vs ENRICHED"
            options={compareOptions}
            value="BASELINE vs ENRICHED"
            onChange={() => {
              /* single option — no-op */
            }}
            minWidth={288}
          />
        </div>
      </div>

      {/* ---------------------------------------------------------------- */}
      {/* Tier stat cards — equal width, compact (~150 px)                 */}
      {/* ---------------------------------------------------------------- */}
      <div className="flex gap-4">
        {/* Tier 1 — only rendered when is_known=true; otherwise an N/A card */}
        {tier1 !== null ? (
          <TierCard
            tierLabel="TIER 1"
            tierDesc="EXACT MATCH"
            score={tier1.score}
            total={tier1.total}
          />
        ) : (
          <div className="flex flex-1 flex-col gap-3 rounded border border-border bg-surface p-4 opacity-40">
            <div className="flex items-center gap-2">
              <StatusDot status="unverified" size="sm" />
              <span className="font-sans text-2xs uppercase tracking-[0.12em] text-text-muted">
                TIER 1 — EXACT MATCH
              </span>
            </div>
            <div className="font-mono text-xl font-medium text-text-muted">N / A</div>
            <div className="h-1.5 rounded-sm bg-border" />
          </div>
        )}

        <TierCard
          tierLabel="TIER 2"
          tierDesc="RULE COMPLIANCE"
          score={tier2.score}
          total={tier2.total}
        />

        <TierCard
          tierLabel="TIER 3"
          tierDesc="HONESTY CHECK"
          score={tier3.score}
          total={tier3.total}
          subtitle={`${tier3.fabrication_violations} fabrication violation${tier3.fabrication_violations === 1 ? '' : 's'}`}
        />
      </div>

      {/* ---------------------------------------------------------------- */}
      {/* Before / after comparison table                                  */}
      {/* ---------------------------------------------------------------- */}
      {activeComparison && <ComparisonTable row={activeComparison} />}

    </div>
  )
}
