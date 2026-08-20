import { useState } from 'react'

import { AppShell } from '@/components/layout/AppShell'
import type { NavItemId } from '@/components/layout/Sidebar'
import { useTheme } from '@/hooks/useTheme'
import { CategorySchemasView } from '@/views/CategorySchemasView'
import { DescriptionFormatsView } from '@/views/DescriptionFormatsView'
import { EvaluationReportView } from '@/views/EvaluationReportView'
import { ManufacturerEnrichmentView } from '@/views/ManufacturerEnrichmentView'

// Placeholder still: the backend has no project or user concept — no table,
// no auth. Left as constants rather than invented endpoints.
const PROJECT = 'CATALOGIQ'
const USER = 'ANSSHHUU'

function App() {
  const [activeItem, setActiveItem] = useState<NavItemId>('analytics')
  const { theme, toggleTheme } = useTheme()

  // Every NavItemId now maps to a real view — no fallthrough placeholders
  // left. 'analytics' is both the default and the final `else` branch below,
  // which is redundant only in the sense that every id is covered exactly
  // once; it stays an if/else-if chain rather than a lookup map so each
  // view's required props (onBack, etc.) stay inline and type-checked.
  //
  // Mounting one or the other (rather than hiding one with CSS) is what keeps
  // each view's fetches scoped to the time it is actually on screen.
  return (
    <AppShell
      activeItem={activeItem}
      onNavigate={setActiveItem}
      project={PROJECT}
      user={USER}
      theme={theme}
      onToggleTheme={toggleTheme}
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
  )
}

export default App
