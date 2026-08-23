import { useCallback, useState } from 'react'

import { AppShell } from '@/components/layout/AppShell'
import type { NavItemId } from '@/components/layout/Sidebar'
import { PostLoginTransition } from '@/components/PostLoginTransition'
import { useSession } from '@/hooks/useSession'
import { useTheme } from '@/hooks/useTheme'
import type { Session } from '@/lib/session'
import { CategorySchemasView } from '@/views/CategorySchemasView'
import { DescriptionFormatsView } from '@/views/DescriptionFormatsView'
import { EvaluationReportView } from '@/views/EvaluationReportView'
import { LoginView } from '@/views/LoginView'
import { ManufacturerEnrichmentView } from '@/views/ManufacturerEnrichmentView'

// Placeholder still: the backend has no project concept — no table.
// The user/role display is real now, sourced from the session (see
// useSession.ts / backend/auth.py).
const PROJECT = 'CATALOGIQ'

function App() {
  const [activeItem, setActiveItem] = useState<NavItemId>('analytics')
  const { theme, toggleTheme } = useTheme()
  const { session, login, logout } = useSession()
  const [showTransition, setShowTransition] = useState(false)

  const handleLogin = useCallback(
    (next: Session) => {
      login(next)
      setShowTransition(true)
    },
    [login],
  )

  // No valid session -> the login screen is the entire app; nothing behind
  // it renders or fetches.
  if (!session) {
    return <LoginView onLogin={handleLogin} theme={theme} onToggleTheme={toggleTheme} />
  }

  // Every NavItemId now maps to a real view — no fallthrough placeholders
  // left. 'analytics' is both the default and the final `else` branch below,
  // which is redundant only in the sense that every id is covered exactly
  // once; it stays an if/else-if chain rather than a lookup map so each
  // view's required props (onBack, etc.) stay inline and type-checked.
  //
  // Mounting one or the other (rather than hiding one with CSS) is what keeps
  // each view's fetches scoped to the time it is actually on screen.
  return (
    <>
      <AppShell
        activeItem={activeItem}
        onNavigate={setActiveItem}
        project={PROJECT}
        email={session.email}
        role={session.role}
        theme={theme}
        onToggleTheme={toggleTheme}
        onLogout={logout}
      >
        {activeItem === 'settings' ? (
          <CategorySchemasView />
        ) : activeItem === 'pipeline' ? (
          <DescriptionFormatsView onBack={() => setActiveItem('analytics')} />
        ) : activeItem === 'enrichment' ? (
          <ManufacturerEnrichmentView onBack={() => setActiveItem('analytics')} />
        ) : (
          <EvaluationReportView />
        )}
      </AppShell>
      {showTransition && <PostLoginTransition onDone={() => setShowTransition(false)} />}
    </>
  )
}

export default App
