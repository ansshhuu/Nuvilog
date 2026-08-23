import { useEffect, useState } from 'react'

const DURATION_MS = 900

export interface PostLoginTransitionProps {
  onDone: () => void
}

/** Brief branded overlay shown right after login, purely cosmetic — it never
 * gates the dashboard's own data fetch, which starts underneath immediately.
 * The percentage is a simulated fill tied 1:1 to the progress bar's width,
 * not a real fetch-progress readout — the underlying data load is untracked
 * and typically finishes well within this window. */
export function PostLoginTransition({ onDone }: PostLoginTransitionProps) {
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    const start = performance.now()
    let frame: number

    const tick = (now: number) => {
      const fraction = Math.min((now - start) / DURATION_MS, 1)
      setProgress(Math.round(fraction * 100))
      if (fraction < 1) {
        frame = window.requestAnimationFrame(tick)
      } else {
        onDone()
      }
    }
    frame = window.requestAnimationFrame(tick)
    return () => window.cancelAnimationFrame(frame)
  }, [onDone])

  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-background">
      <div className="flex w-64 flex-col items-center gap-6">
        <div className="flex h-14 w-14 items-center justify-center border border-border bg-surface font-sans text-2xl font-semibold leading-none text-text-primary">
          N
        </div>

        <span className="font-mono text-2xs uppercase tracking-[0.28em] text-text-muted">
          Initializing
        </span>

        <div className="h-px w-full overflow-hidden bg-border">
          <div
            className="h-full bg-accent transition-[width] duration-100 ease-linear"
            style={{ width: `${progress}%` }}
          />
        </div>

        <div className="flex w-full items-center justify-between font-mono text-2xs uppercase tracking-[0.12em] text-text-muted">
          <span>Preparing evaluation data</span>
          <span className="font-semibold text-text-primary">{progress}%</span>
        </div>
      </div>
    </div>
  )
}
