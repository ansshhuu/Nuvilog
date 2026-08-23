export interface Session {
  token: string
  email: string
  role: string
}

const STORAGE_KEY = 'nuvilog-session'

/** Pure localStorage read — used by api.ts to attach the auth header without
 * a React dependency, and by useSession.ts as its initial state. */
export function getStoredSession(): Session | null {
  if (typeof window === 'undefined') return null
  const raw = window.localStorage.getItem(STORAGE_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as Session
  } catch {
    return null
  }
}

export function setStoredSession(session: Session): void {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session))
}

export function clearStoredSession(): void {
  window.localStorage.removeItem(STORAGE_KEY)
}
