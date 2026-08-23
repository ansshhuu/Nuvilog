import { expect, test } from '@playwright/test'

import {
  descriptionFormatsFixture,
  descriptionFormatsOutOfRangeError,
  evaluationReportFixture,
  KNOWN_MPN,
} from './fixtures'
import { fulfillJson, loginThroughUi, mockLogin, navigateTo } from './helpers'

test.describe('View Description Formats for a known row', () => {
  test('renders the 5 format cards with real generated/not-generated states', async ({
    page,
  }) => {
    await mockLogin(page)
    await page.route('**/api/evaluation-report', (route) =>
      fulfillJson(route, 200, evaluationReportFixture),
    )
    await page.route('**/api/description-formats**', (route) => {
      const url = new URL(route.request().url())
      const record = Number(url.searchParams.get('record') ?? '0')
      return fulfillJson(route, 200, descriptionFormatsFixture(record))
    })

    await loginThroughUi(page)
    await navigateTo(page, 'Description Formats')

    await expect(page.getByRole('heading', { name: 'Description Formats' })).toBeVisible()
    await expect(page.getByText(KNOWN_MPN, { exact: true })).toBeVisible()

    // INVOICE_DESC: generated, within its 40-char limit — real text, real badge.
    // (Card 1 is focused by default, so its text is echoed a second time in
    // the right-hand rule panel's EXAMPLE — .first() targets the card body.)
    await expect(page.getByText('WDTS7024RZ DISHWASHER BUILT IN').first()).toBeVisible()
    await expect(page.getByText('31 / 40')).toBeVisible()

    // MOBILE_DESC: generated but under its 60-80 floor — badge must flag it,
    // not silently pass.
    await expect(page.getByText('54 / 60-80')).toBeVisible()

    // SHORT_DESC: not generated — honest reason shown, not a blank card.
    await expect(
      page.getByRole('button', { name: /SHORT_DESC/ }),
    ).toContainText('Not generated — rule confidence too low')

    // Clicking a card focuses it and drives the right-hand generation-rule panel.
    await page.getByRole('button', { name: /INVOICE_DESC/ }).click()
    await expect(page.getByText('Generation Rule')).toBeVisible()
    await expect(
      page.getByText('Mfg_Part_Num + Part_Desc, space-joined, truncated to 40 chars.'),
    ).toBeVisible()

    // Pager reflects the real total and the Previous button is disabled on record 1.
    await expect(page.getByText('Record 1 of 2')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Previous record' })).toBeDisabled()
  })

  test('a row selector pointing at a non-existent SKU shows the honest error, not a crash', async ({
    page,
  }) => {
    await mockLogin(page)
    await page.route('**/api/evaluation-report', (route) =>
      fulfillJson(route, 200, evaluationReportFixture),
    )
    // Mirrors the real backend's 400 for GET /api/description-formats?record=N
    // when N doesn't correspond to any row in the pipeline output — see
    // backend/main.py::get_description_formats.
    await page.route('**/api/description-formats**', (route) =>
      fulfillJson(route, 400, descriptionFormatsOutOfRangeError(0, 10)),
    )

    await loginThroughUi(page)
    await navigateTo(page, 'Description Formats')

    await expect(page.getByText('record must be 0–9; got 0.')).toBeVisible()
    // No format cards, no partial/broken render underneath the error.
    await expect(page.getByRole('heading', { name: 'Description Formats' })).toBeHidden()
  })
})
