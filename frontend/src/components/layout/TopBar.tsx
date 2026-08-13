import { ChevronDown, FileOutput } from 'lucide-react'

export interface TopBarProps {
  project: string
  user: string
  onProjectClick?: () => void
  onUserClick?: () => void
  onExportClick?: () => void
}

interface SelectorProps {
  label: string
  value: string
  onClick?: () => void
}

function Selector({ label, value, onClick }: SelectorProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex items-center gap-2 px-2 py-1 text-text-muted transition-colors hover:text-text-primary"
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

export function TopBar({
  project,
  user,
  onProjectClick,
  onUserClick,
  onExportClick,
}: TopBarProps) {
  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-border bg-background pl-8 pr-6">
      <span className="font-sans text-base font-medium uppercase tracking-[0.32em] text-text-primary">
        Nuvilog
      </span>

      <div className="flex items-center gap-6">
        <Selector label="Project" value={project} onClick={onProjectClick} />
        <Selector label="User" value={user} onClick={onUserClick} />
        <button
          type="button"
          aria-label="Export"
          title="Export"
          onClick={onExportClick}
          className="ml-2 flex h-8 w-8 items-center justify-center text-text-muted transition-colors hover:text-text-primary"
        >
          <FileOutput size={13} strokeWidth={1.75} />
        </button>
      </div>
    </header>
  )
}
