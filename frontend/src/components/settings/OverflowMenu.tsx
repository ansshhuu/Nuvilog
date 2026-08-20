import { MoreHorizontal } from 'lucide-react'

const DEFAULT_NOT_IMPLEMENTED =
  'Not yet implemented — edit schemas/*.yaml directly'

export interface OverflowMenuProps {
  /** Used only for the button's aria-label — not rendered as text. */
  label: string
  iconSize?: number
  /** Override the default YAML-schema reason — the dishwasher scaffold has
   * no schemas/*.yaml file behind it at all, it lives in dishwasher_schema.py. */
  reason?: string
}

/**
 * Confirmed against backend/main.py: there is no PUT/PATCH/DELETE route for
 * categories or fields, and neither schema_registry.py nor
 * dishwasher_schema.py has a write path — both are read/imported once at
 * process start and never rewritten. So this renders disabled with the
 * reason on hover, rather than opening a menu that has nothing real behind it.
 */
export function OverflowMenu({
  label,
  iconSize = 14,
  reason = DEFAULT_NOT_IMPLEMENTED,
}: OverflowMenuProps) {
  return (
    <span role="cell" className="flex min-w-0 justify-end">
      <button
        type="button"
        disabled
        title={reason}
        aria-label={`${label} options — ${reason}`}
        className="shrink-0 cursor-not-allowed p-1 text-text-muted opacity-40"
      >
        <MoreHorizontal size={iconSize} strokeWidth={1.75} />
      </button>
    </span>
  )
}
