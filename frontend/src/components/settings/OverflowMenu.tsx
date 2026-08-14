import { MoreHorizontal } from 'lucide-react'

const NOT_IMPLEMENTED = 'Not yet implemented — edit schemas/*.yaml directly'

export interface OverflowMenuProps {
  /** Used only for the button's aria-label — not rendered as text. */
  label: string
  iconSize?: number
}

/**
 * Confirmed against backend/main.py: there is no PUT/PATCH/DELETE route for
 * categories or fields, and schema_registry.py has no write path at all —
 * schemas are read from schemas/*.yaml at process start and never rewritten.
 * So this renders disabled with the reason on hover, rather than opening a
 * menu that has nothing real behind it.
 */
export function OverflowMenu({ label, iconSize = 14 }: OverflowMenuProps) {
  return (
    <span role="cell" className="flex min-w-0 justify-end">
      <button
        type="button"
        disabled
        title={NOT_IMPLEMENTED}
        aria-label={`${label} options — ${NOT_IMPLEMENTED}`}
        className="shrink-0 cursor-not-allowed p-1 text-text-muted opacity-40"
      >
        <MoreHorizontal size={iconSize} strokeWidth={1.75} />
      </button>
    </span>
  )
}
