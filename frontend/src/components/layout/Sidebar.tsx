import {
  BarChart2,
  GitBranch,
  Globe,
  LogOut,
  Settings,
  type LucideIcon,
} from 'lucide-react'

import { cn } from '@/lib/utils'

// 'dashboard' and 'ingest' removed from the reachable nav — those screens
// were built for the old fastener-domain demo (Supabase product review +
// upload flow) and don't fit this domain. Components moved to
// src/_unused/, not deleted, in case any of it's salvageable later.
//
// 'documents', 'sources', 'flags' removed too — they never had a screen
// (App.tsx fell through to the dashboard, then to analytics, for all
// three), so they were dead clicks with no real destination. The 4
// remaining entries are the entire demo path: every one of them routes to
// a real, data-backed view in App.tsx.
export type NavItemId = 'pipeline' | 'enrichment' | 'analytics' | 'settings'

interface NavItem {
  id: NavItemId
  label: string
  icon: LucideIcon
}

export const NAV_ITEMS: NavItem[] = [
  { id: 'analytics', label: 'Evaluation Report', icon: BarChart2 },
  { id: 'pipeline', label: 'Description Formats', icon: GitBranch },
  { id: 'enrichment', label: 'Manufacturer Enrichment', icon: Globe },
  { id: 'settings', label: 'Settings', icon: Settings },
]

export interface SidebarProps {
  activeItem: NavItemId
  onNavigate?: (id: NavItemId) => void
  onLogout?: () => void
}

export function Sidebar({ activeItem, onNavigate, onLogout }: SidebarProps) {
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

      <div className="flex flex-col items-center border-t border-border py-4">
        <button
          type="button"
          title="Sign out"
          aria-label="Sign out"
          onClick={onLogout}
          className="flex h-11 w-full items-center justify-center text-text-muted transition-colors hover:text-text-primary"
        >
          <LogOut size={14} strokeWidth={1.75} />
        </button>
      </div>
    </nav>
  )
}
