import { useEffect } from 'react'

const DURATION_MS = 900

export interface PostLoginTransitionProps {
  onDone: () => void
}

/** Brief branded overlay shown right after login, purely cosmetic — it never
 * gates the dashboard's own data fetch, which starts underneath immediately. */
export function PostLoginTransition({ onDone }: PostLoginTransitionProps) {
  useEffect(() => {
    const timer = window.setTimeout(onDone, DURATION_MS)
    return () => window.clearTimeout(timer)
  }, [onDone])

  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-6 bg-background">
      <span className="font-sans text-lg font-medium uppercase tracking-[0.32em] text-text-primary">
        Nuvilog
      </span>
      <div className="h-px w-40 overflow-hidden bg-border">
        <div className="h-full w-1/3 animate-post-login-progress bg-accent" />
      </div>
    </div>
  )
}
