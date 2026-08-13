import { useCallback, useEffect, useState } from 'react'

import { ApiError } from './api'

export interface AsyncState<T> {
  data: T | null
  loading: boolean
  error: string | null
  /** Re-runs the request. */
  reload: () => void
}

/**
 * Runs an async request and tracks loading/error alongside the result.
 *
 * Two details that matter more than the state shape:
 *
 *  * The in-flight request is aborted when `key` changes or the component
 *    unmounts, so clicking through products quickly cannot let a slow earlier
 *    response land after a faster later one and show the wrong product.
 *  * `data` is cleared when `key` changes, so the panel shows its loading
 *    state rather than the previous product's values under a new heading.
 *
 * `key` is the identity of the request — pass null to skip fetching entirely.
 */
export function useAsync<T>(
  run: (signal: AbortSignal) => Promise<T>,
  key: string | null,
): AsyncState<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(key !== null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  const reload = useCallback(() => setAttempt((n) => n + 1), [])

  useEffect(() => {
    if (key === null) {
      setData(null)
      setLoading(false)
      setError(null)
      return
    }

    const controller = new AbortController()
    let active = true

    setLoading(true)
    setError(null)
    setData(null)

    run(controller.signal)
      .then((result) => {
        if (active) setData(result)
      })
      .catch((cause) => {
        // An abort is this hook cancelling its own request, not a failure the
        // user should ever see.
        if (controller.signal.aborted || !active) return
        setError(
          cause instanceof ApiError
            ? cause.message
            : 'Something went wrong loading this data.',
        )
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
      controller.abort()
    }
    // `run` is intentionally not a dependency: callers pass an inline closure,
    // and `key` already identifies the request it stands for.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, attempt])

  return { data, loading, error, reload }
}
