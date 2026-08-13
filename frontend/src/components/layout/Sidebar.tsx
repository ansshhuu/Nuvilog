import {
  AlertTriangle,
  BarChart2,
  Database,
  FileText,
  GitBranch,
  LayoutGrid,
  Settings,
  Upload,
  type LucideIcon,
} from 'lucide-react'

import { cn } from '@/lib/utils'

export type NavItemId =
  | 'dashboard'
  | 'ingest'
  | 'documents'
  | 'sources'
  | 'flags'
  | 'pipeline'
  | 'analytics'
  | 'settings'

interface NavItem {
  id: NavItemId
  label: string
  icon: LucideIcon
}

export const NAV_ITEMS: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutGrid },
  // The nav had no upload entry before — Documents/Sources are both read
  // views. Added rather than repurposed, so "ingest" is its own destination.
  { id: 'ingest', label: 'Ingest New Data', icon: Upload },
  { id: 'documents', label: 'Documents', icon: FileText },
  { id: 'sources', label: 'Sources', icon: Database },
  { id: 'flags', label: 'Flagged', icon: AlertTriangle },
  { id: 'pipeline', label: 'Pipeline', icon: GitBranch },
  { id: 'analytics', label: 'Analytics', icon: BarChart2 },
  { id: 'settings', label: 'Settings', icon: Settings },
]

export interface SidebarProps {
  activeItem: NavItemId
  onNavigate?: (id: NavItemId) => void
}

export function Sidebar({ activeItem, onNavigate }: SidebarProps) {
  return (
    <nav
      aria-label="Main"
      className="flex h-full w-[72px] shrink-0 flex-col border-r border-border bg-background"
    >
      {/* Logo mark — sharp-cornered square, matches top bar height */}
      <div className="flex h-16 items-center justify-center border-b border-border">
        <div className="flex h-9 w-9 items-center justify-center border border-border bg-surface font-sans text-lg font-semibold leading-none text-text-primary">
          N
        </div>
      </div>

      <ul className="flex flex-1 flex-col items-center gap-2 py-6">
        {NAV_ITEMS.map(({ id, label, icon: Icon }) => {
          const isActive = id === activeItem
          return (
            <li key={id} className="w-full">
              <button
                type="button"
                title={label}
                aria-label={label}
                aria-current={isActive ? 'page' : undefined}
                onClick={() => onNavigate?.(id)}
                className={cn(
                  'relative flex h-11 w-full items-center justify-center transition-colors',
                  isActive
                    ? 'text-selected'
                    : 'text-text-muted hover:text-text-primary',
                )}
              >
                {isActive && (
                  <span
                    aria-hidden
                    className="absolute left-0 top-1/2 h-6 w-[2px] -translate-y-1/2 bg-selected"
                  />
                )}
                <Icon size={14} strokeWidth={1.75} />
              </button>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
