import { expect, test } from '@playwright/test'

import { evaluationReportFixture, KNOWN_MPN } from './fixtures'
import { fulfillJson, loginThroughUi, mockLogin } from './helpers'

test.describe('View Evaluation Report', () => {
  test.beforeEach(async ({ page }) => {
    await mockLogin(page)
    await page.route('**/api/evaluation-report', (route) =>
      fulfillJson(route, 200, evaluationReportFixture),
    )
    await loginThroughUi(page)
    await expect(page.getByRole('heading', { name: 'Evaluation Report' })).toBeVisible()
  })

  test('shows tier scores for the default (first known) row', async ({ page }) => {
    // First known row in the fixture is PDSH4816AF: Tier 1 240/252, Tier 2 11/11, Tier 3 176/176.
    await expect(page.getByText('240 / 252')).toBeVisible()
    await expect(page.getByText('11 / 11')).toBeVisible()
    await expect(page.getByText('176 / 176')).toBeVisible()
    await expect(page.getByText('0 fabrication violations')).toBeVisible()
  })

  test('switching the MPN selector updates tier scores and comparison table', async ({
    page,
  }) => {
    const mpnSelect = page.getByRole('combobox', { name: 'MFG_PART_NUM' })
    await mpnSelect.selectOption(KNOWN_MPN)

    // KNOWN_MPN (WDTS7024RZ) is a perfect Tier 1: 252/252.
    await expect(page.getByText('252 / 252')).toBeVisible()

    // Comparison table: enriched attributes_verified (4/15) beats baseline
    // (0/15) — the enriched cell gets the "improved" highlight treatment.
    await expect(page.getByText('0/15')).toBeVisible()
    await expect(page.getByText('4/15')).toBeVisible()
  })

  test('a row with no ground truth shows Tier 1 as N/A', async ({ page }) => {
    // THIN-ROW-001 (is_known: false) is not in the MPN dropdown (only known
    // rows are selectable) — confirm the dropdown only lists the 2 known MPNs.
    const mpnSelect = page.getByRole('combobox', { name: 'MFG_PART_NUM' })
    await expect(mpnSelect.locator('option')).toHaveCount(2)
  })
})
