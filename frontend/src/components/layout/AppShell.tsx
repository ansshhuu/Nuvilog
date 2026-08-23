import type { ReactNode } from 'react'

import type { Theme } from '@/hooks/useTheme'

import { Sidebar, type NavItemId } from './Sidebar'
import { TopBar } from './TopBar'

export interface AppShellProps {
  activeItem: NavItemId
  onNavigate?: (id: NavItemId) => void
  project: string
  email: string
  role: string
  theme: Theme
  onToggleTheme: () => void
  onLogout?: () => void
  children?: ReactNode
}

export function AppShell({
  activeItem,
  onNavigate,
  project,
  email,
  role,
  theme,
  onToggleTheme,
  onLogout,
  children,
}: AppShellProps) {
  return (
    <div className="flex h-screen w-full overflow-hidden bg-background text-text-primary">
      <Sidebar activeItem={activeItem} onNavigate={onNavigate} onLogout={onLogout} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar project={project} email={email} role={role} theme={theme} onToggleTheme={onToggleTheme} />
        <main className="min-h-0 flex-1 overflow-auto">{children}</main>
      </div>
    </div>
  )
}
