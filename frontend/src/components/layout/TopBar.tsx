import { ChevronDown, FileOutput } from 'lucide-react'

export interface TopBarProps {
  project: string
  user: string
}

const NO_PROJECT_CONCEPT =
  'Not yet implemented — the backend has no project or user concept (no table, no auth)'
const NO_EXPORT_ROUTE = 'Not yet implemented — no export route exists in backend/main.py'

interface SelectorProps {
  label: string
  value: string
}

/**
 * Rendered disabled with the reason on hover, same posture as every other
 * not-yet-implemented control in this app (OverflowMenu, Add Field,
 * Regenerate All) — this used to render as a live-looking button with a
 * chevron affordance and no handler wired anywhere, a silent dead click.
 */
function Selector({ label, value }: SelectorProps) {
  return (
    <button
      type="button"
      disabled
      title={NO_PROJECT_CONCEPT}
      className="flex cursor-not-allowed items-center gap-2 px-2 py-1 text-text-muted opacity-60"
    >
      <span className="font-sans text-2xs uppercase tracking-[0.12em]">
        {label}:
      </span>
      <span className="font-mono text-2xs tracking-[0.06em] text-text-primary">
        {value}
      </span>
      <ChevronDown size={12} strokeWidth={1.75} />
    </button>
  )
}

export function TopBar({ project, user }: TopBarProps) {
  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-border bg-background pl-8 pr-6">
      <span className="font-sans text-base font-medium uppercase tracking-[0.32em] text-text-primary">
        Nuvilog
      </span>

      <div className="flex items-center gap-6">
        <Selector label="Project" value={project} />
        <Selector label="User" value={user} />
        <button
          type="button"
          disabled
          aria-label="Export"
          title={NO_EXPORT_ROUTE}
          className="ml-2 flex h-8 w-8 cursor-not-allowed items-center justify-center text-text-muted opacity-60"
        >
          <FileOutput size={13} strokeWidth={1.75} />
        </button>
      </div>
    </header>
  )
}
