import { useCallback, useState } from 'react'

import {
  clearStoredSession,
  getStoredSession,
  setStoredSession,
  type Session,
} from '@/lib/session'

/** Session state backed by localStorage, same pattern as useTheme. */
export function useSession() {
  const [session, setSession] = useState<Session | null>(getStoredSession)

  const login = useCallback((next: Session) => {
    setStoredSession(next)
    setSession(next)
  }, [])

  const logout = useCallback(() => {
    clearStoredSession()
    setSession(null)
  }, [])

  return { session, login, logout }
}
