import { expect, test } from '@playwright/test'

import { dishwasherSchemaFixture, evaluationReportFixture } from './fixtures'
import { fulfillJson, loginThroughUi, mockLogin, navigateTo } from './helpers'

test.describe('View Settings / Category Schemas', () => {
  test('shows the real 15-slot dishwasher scaffold, auto-expanded', async ({ page }) => {
    await mockLogin(page)
    await page.route('**/api/evaluation-report', (route) =>
      fulfillJson(route, 200, evaluationReportFixture),
    )
    await page.route('**/api/dishwasher-schema', (route) =>
      fulfillJson(route, 200, dishwasherSchemaFixture),
    )

    await loginThroughUi(page)
    await navigateTo(page, 'Settings')

    await expect(page.getByRole('heading', { name: /category schemas/i })).toBeVisible()

    // The one schema row (Dishwasher), open by default, with the real field count.
    const schemaTable = page.getByRole('table', { name: 'Category schemas' })
    await expect(schemaTable.getByText('Dishwasher')).toBeVisible()
    await expect(schemaTable.getByText('15', { exact: true })).toBeVisible()

    // Field-definition table underneath is already expanded — 15 field rows.
    const fieldTable = page.getByRole('table', { name: 'Field definitions' })
    await expect(fieldTable.getByRole('row')).toHaveCount(16) // 15 fields + header
    await expect(fieldTable.getByText('Sound Level')).toBeVisible()
    await expect(fieldTable.getByText('dBA')).toBeVisible()

    // "+ Add Field" is honestly disabled, not a dead-looking live control.
    const addField = page.getByRole('button', { name: 'Add Field' })
    await expect(addField).toBeDisabled()
  })

  test('collapsing the schema row hides the field table', async ({ page }) => {
    await mockLogin(page)
    await page.route('**/api/evaluation-report', (route) =>
      fulfillJson(route, 200, evaluationReportFixture),
    )
    await page.route('**/api/dishwasher-schema', (route) =>
      fulfillJson(route, 200, dishwasherSchemaFixture),
    )

    await loginThroughUi(page)
    await navigateTo(page, 'Settings')

    await expect(page.getByRole('table', { name: 'Field definitions' })).toBeVisible()

    await page.getByRole('row', { name: /Dishwasher/ }).click()

    await expect(page.getByRole('table', { name: 'Field definitions' })).toBeHidden()
  })
})
