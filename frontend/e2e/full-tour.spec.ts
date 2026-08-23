import { expect, test } from '@playwright/test'

import {
  descriptionFormatsFixture,
  dishwasherSchemaFixture,
  evaluationReportFixture,
  manufacturerEnrichmentSuccessFixture,
} from './fixtures'
import { fulfillJson, loginThroughUi, mockLogin, navigateTo } from './helpers'

/**
 * The connected journey the ask names literally: log in, then visit all 4
 * real screens in one session via the sidebar. Per-screen content assertions
 * live in each screen's own spec file — this test's job is the navigation
 * path itself: every nav item lands on the right screen, back links work,
 * nothing dead-clicks.
 */
test('login through to viewing all 4 real screens', async ({ page }) => {
  await mockLogin(page)
  await page.route('**/api/evaluation-report', (route) =>
    fulfillJson(route, 200, evaluationReportFixture),
  )
  await page.route('**/api/description-formats**', (route) =>
    fulfillJson(route, 200, descriptionFormatsFixture(0)),
  )
  await page.route('**/api/manufacturer-enrichment**', (route) =>
    fulfillJson(route, 200, manufacturerEnrichmentSuccessFixture(0)),
  )
  await page.route('**/api/dishwasher-schema', (route) =>
    fulfillJson(route, 200, dishwasherSchemaFixture),
  )

  await loginThroughUi(page)

  // 1. Evaluation Report — the default landing screen after login.
  await expect(page.getByRole('heading', { name: 'Evaluation Report' })).toBeVisible()

  // 2. Description Formats.
  await navigateTo(page, 'Description Formats')
  await expect(page.getByRole('heading', { name: 'Description Formats' })).toBeVisible()
  await page.getByRole('button', { name: 'Back to Evaluation Report' }).click()
  await expect(page.getByRole('heading', { name: 'Evaluation Report' })).toBeVisible()

  // 3. Manufacturer Enrichment.
  await navigateTo(page, 'Manufacturer Enrichment')
  await expect(page.getByText('SOURCE REACHED')).toBeVisible()
  await page.getByRole('button', { name: 'Back to Evaluation Report' }).click()
  await expect(page.getByRole('heading', { name: 'Evaluation Report' })).toBeVisible()

  // 4. Settings / Category Schemas.
  await navigateTo(page, 'Settings')
  await expect(page.getByRole('heading', { name: /category schemas/i })).toBeVisible()

  // Sign out returns to the login screen and the session is gone.
  await page.getByRole('button', { name: 'Sign out' }).click()
  await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible()
})
