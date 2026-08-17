import { useState } from 'react'

import { AppShell } from '@/components/layout/AppShell'
import type { NavItemId } from '@/components/layout/Sidebar'
import { CategorySchemasView } from '@/views/CategorySchemasView'
import { DashboardView } from '@/views/DashboardView'
import { DescriptionFormatsView } from '@/views/DescriptionFormatsView'
import { EvaluationReportView } from '@/views/EvaluationReportView'
import { IngestView } from '@/views/IngestView'
import { ManufacturerEnrichmentView } from '@/views/ManufacturerEnrichmentView'

// Placeholder still: the backend has no project or user concept — no table,
// no auth. Left as constants rather than invented endpoints.
const PROJECT = 'CATALOGIQ'
const USER = 'ANSSHHUU'

function App() {
  const [activeItem, setActiveItem] = useState<NavItemId>('dashboard')

  // Four built destinations so far. The other nav entries have no screen yet
  // and fall through to the dashboard, as they did before this split.
  //
  // Mounting one or the other (rather than hiding one with CSS) is what keeps
  // each view's fetches scoped to the time it is actually on screen — and it
  // means returning to the dashboard after an ingest refetches the product
  // list, so a newly ingested product is there without a manual reload.
  return (
    <AppShell
      activeItem={activeItem}
      onNavigate={setActiveItem}
      project={PROJECT}
      user={USER}
    >
      {activeItem === 'ingest' ? (
        <IngestView onIngested={() => setActiveItem('dashboard')} />
      ) : activeItem === 'settings' ? (
        <CategorySchemasView />
      ) : activeItem === 'analytics' ? (
        <EvaluationReportView />
      ) : activeItem === 'pipeline' ? (
        <DescriptionFormatsView onBack={() => setActiveItem('dashboard')} />
      ) : activeItem === 'enrichment' ? (
        <ManufacturerEnrichmentView onBack={() => setActiveItem('dashboard')} />
      ) : (
        <DashboardView />
      )}
    </AppShell>
  )
}

export default App
