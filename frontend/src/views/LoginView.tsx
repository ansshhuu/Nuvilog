import { useState, type FormEvent } from 'react'

import { ThemeToggle } from '@/components/ThemeToggle'
import type { Theme } from '@/hooks/useTheme'
import { login as loginRequest } from '@/lib/api'
import type { Session } from '@/lib/session'

export interface LoginViewProps {
  onLogin: (session: Session) => void
  theme: Theme
  onToggleTheme: () => void
}

export function LoginView({ onLogin, theme, onToggleTheme }: LoginViewProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setPending(true)
    try {
      const session = await loginRequest(email, password)
      onLogin(session)
    } catch {
      setError('Invalid email or password.')
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="relative flex h-screen w-full items-center justify-center bg-background text-text-primary">
      <ThemeToggle
        theme={theme}
        onToggleTheme={onToggleTheme}
        className="absolute right-6 top-6 flex h-8 w-8 items-center justify-center text-text-muted transition-colors hover:text-text-primary"
      />

      <div className="flex w-[340px] flex-col gap-8">
        <div className="flex flex-col items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center border border-border bg-surface font-sans text-lg font-semibold leading-none text-text-primary">
            N
          </div>
          <span className="font-sans text-base font-medium uppercase tracking-[0.32em] text-text-primary">
            Nuvilog
          </span>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4 border border-border bg-surface p-6">
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="login-email"
              className="font-sans text-2xs uppercase tracking-[0.12em] text-text-muted"
            >
              Email
            </label>
            <input
              id="login-email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="border border-border bg-background px-3 py-2 font-mono text-sm text-text-primary outline-none focus:border-accent"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="login-password"
              className="font-sans text-2xs uppercase tracking-[0.12em] text-text-muted"
            >
              Password
            </label>
            <input
              id="login-password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="border border-border bg-background px-3 py-2 font-mono text-sm text-text-primary outline-none focus:border-accent"
            />
          </div>

          {error && (
            <span className="font-sans text-xs text-status-contradiction">{error}</span>
          )}

          <button
            type="submit"
            disabled={pending}
            className="mt-2 flex h-9 items-center justify-center border border-border bg-background font-sans text-2xs font-medium uppercase tracking-[0.14em] text-text-primary transition-colors hover:bg-border disabled:cursor-not-allowed disabled:opacity-60"
          >
            {pending ? 'Signing In…' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  )
}
