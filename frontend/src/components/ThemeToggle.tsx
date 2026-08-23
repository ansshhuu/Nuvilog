import { Moon, Sun } from 'lucide-react'

import type { Theme } from '@/hooks/useTheme'

export interface ThemeToggleProps {
  theme: Theme
  onToggleTheme: () => void
  className?: string
}

/** Dark/light toggle — the single implementation, shared by the top bar and
 * the login screen so both stay pixel-identical and drive the same state. */
export function ThemeToggle({ theme, onToggleTheme, className }: ThemeToggleProps) {
  const isLight = theme === 'light'

  return (
    <button
      type="button"
      onClick={onToggleTheme}
      aria-label={isLight ? 'Switch to dark theme' : 'Switch to light theme'}
      title={isLight ? 'Switch to dark theme' : 'Switch to light theme'}
      className={
        className ??
        'flex h-8 w-8 items-center justify-center text-text-muted transition-colors hover:text-text-primary'
      }
    >
      {isLight ? <Moon size={13} strokeWidth={1.75} /> : <Sun size={13} strokeWidth={1.75} />}
    </button>
  )
}
