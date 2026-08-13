import { useEffect, useRef, useState } from 'react'
import { FileText, X } from 'lucide-react'

import { cn } from '@/lib/utils'
import { StatusDot } from './StatusDot'
import { formatFieldName, type ReviewField } from '@/lib/fields'
import type { MentionDTO } from '@/lib/api-types'

export interface ContradictionModalProps {
  /** The contradicted field. Null closes the modal. */
  field: ReviewField | null
  onClose: () => void
}

/**
 * No endpoint exists for resolving a contradiction — not for picking a side,
 * not for flagging one for manual review. The buttons are rendered because the
 * decision they represent is the point of the screen, but they are disabled
 * and say why on hover rather than silently doing nothing on click.
 */
const NOT_IMPLEMENTED = 'Backend endpoint not yet implemented'

function Label({ children }: { children: string }) {
  return (
    <h4 className="font-sans text-3xs uppercase tracking-[0.18em] text-text-muted">
      {children}
    </h4>
  )
}

function MentionCard({ mention }: { mention: MentionDTO }) {
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-4 border border-border bg-surface p-4">
      <div className="flex items-center gap-2 text-text-muted">
        <FileText size={12} strokeWidth={1.75} className="shrink-0" />
        <span className="truncate font-mono text-3xs uppercase tracking-[0.08em]">
          {mention.location}
        </span>
      </div>

      <div className="flex flex-col gap-2">
        <Label>Extracted Value</Label>
        <p className="break-words font-mono text-lg text-status-contradiction">
          {mention.value}
        </p>
      </div>

      {/* No heading when there is nothing to put under it. */}
      {mention.snippet && (
        <div className="flex flex-col gap-2">
          <Label>Source Snippet</Label>
          <div className="border-t border-dashed border-border pt-3">
            <p className="whitespace-pre-wrap break-words font-mono text-3xs leading-relaxed text-text-muted">
              {mention.snippet}
            </p>
          </div>
        </div>
      )}
    </div>
  )
}

/** The divider between two sides. Decorative — the cards carry the meaning. */
function VersusRule() {
  return (
    <div aria-hidden className="flex shrink-0 flex-col items-center gap-2 self-stretch py-4">
      <span className="w-px flex-1 bg-border" />
      <span className="font-mono text-3xs uppercase tracking-[0.12em] text-text-muted">
        VS
      </span>
      <span className="w-px flex-1 bg-border" />
    </div>
  )
}

export function ContradictionModal({ field, onClose }: ContradictionModalProps) {
  const [note, setNote] = useState('')
  const closeRef = useRef<HTMLButtonElement>(null)

  // Reset between fields — a note written about one contradiction must not
  // reappear under another.
  useEffect(() => setNote(''), [field?.key])

  useEffect(() => {
    if (!field) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    closeRef.current?.focus()
    return () => document.removeEventListener('keydown', onKey)
  }, [field, onClose])

  if (!field) return null

  const flag = field.flags.find((f) => f.issue_type === 'contradiction')
  const mentions = flag?.mentions ?? null
  // Null means "written before the column existed", which is not the same as
  // an empty list. Only a populated list can drive the side-by-side view.
  const hasSides = Array.isArray(mentions) && mentions.length > 0

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-6"
      // Backdrop click closes; clicks inside the card must not bubble to here.
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Contradiction in ${formatFieldName(field.fieldName)}`}
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-full w-full max-w-[820px] flex-col overflow-y-auto border border-border bg-background"
      >
        {/* Status colour as a top rule, the way the dot carries it elsewhere. */}
        <div aria-hidden className="h-[3px] shrink-0 bg-status-contradiction" />

        <div className="flex items-center justify-between gap-4 border-b border-border px-5 py-4">
          <div className="flex min-w-0 items-center gap-3">
            <StatusDot status="contradiction" />
            <h2 className="truncate font-mono text-2xs uppercase tracking-[0.12em] text-text-primary">
              Contradiction — {formatFieldName(field.fieldName)}
            </h2>
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label="Close contradiction detail"
            className="shrink-0 text-text-muted transition-colors hover:text-text-primary"
          >
            <X size={13} strokeWidth={1.75} />
          </button>
        </div>

        <div className="flex flex-col gap-6 px-5 py-5">
          {hasSides ? (
            // More than two sides is rare but the detector supports it, so the
            // row wraps rather than dropping the third.
            <div className="flex flex-wrap items-stretch gap-0">
              {mentions.map((mention, i) => (
                <div
                  key={`${mention.value}-${i}`}
                  className="flex min-w-[240px] flex-1 items-stretch"
                >
                  {i > 0 && <VersusRule />}
                  <MentionCard mention={mention} />
                </div>
              ))}
            </div>
          ) : (
            /* Pre-migration row: the prose message is all that was stored, so
               it is shown as-is rather than guessed apart into two cards. */
            <div className="border border-border bg-surface p-4">
              <Label>Reported Conflict</Label>
              <p className="mt-2 whitespace-pre-wrap break-words font-mono text-2xs leading-relaxed text-text-primary">
                {flag?.message ?? 'No detail was recorded for this contradiction.'}
              </p>
              <p className="mt-3 font-mono text-3xs leading-relaxed text-text-muted">
                This finding predates structured conflict data, so the
                individual values cannot be acted on separately.
              </p>
            </div>
          )}

          <div className="flex flex-wrap justify-end gap-3">
            {/* Per-side actions only exist when there are sides to act on. */}
            {hasSides && (
              <>
                <button
                  type="button"
                  disabled
                  title={NOT_IMPLEMENTED}
                  className="border border-border px-4 py-2.5 font-sans text-2xs uppercase tracking-[0.14em] text-text-primary opacity-40"
                >
                  Use Left Value
                </button>
                <button
                  type="button"
                  disabled
                  title={NOT_IMPLEMENTED}
                  className="border border-border px-4 py-2.5 font-sans text-2xs uppercase tracking-[0.14em] text-text-primary opacity-40"
                >
                  Use Right Value
                </button>
              </>
            )}
            <button
              type="button"
              disabled
              title={NOT_IMPLEMENTED}
              className="border border-accent bg-accent px-5 py-2.5 font-sans text-2xs font-medium uppercase tracking-[0.14em] text-background opacity-40"
            >
              Flag for Manual Review
            </button>
          </div>

          <div className="flex flex-col gap-2">
            <label
              htmlFor="reviewer-note"
              className="font-sans text-3xs uppercase tracking-[0.18em] text-text-muted"
            >
              Reviewer Note (Optional)
            </label>
            <textarea
              id="reviewer-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={3}
              placeholder="Add resolution note..."
              className={cn(
                'w-full resize-y border border-border bg-surface px-3 py-2.5',
                'font-mono text-2xs leading-relaxed text-text-primary outline-none',
                'transition-colors placeholder:text-text-muted focus:border-accent',
              )}
            />
            {/* Local state only: there is no submit action to attach it to yet. */}
            <p className="font-mono text-3xs text-text-muted">
              Not saved — no endpoint accepts a resolution note yet.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
