import { expect, test } from '@playwright/test'

import {
  evaluationReportFixture,
  manufacturerEnrichmentSuccessFixture,
  manufacturerEnrichmentTimeoutFixture,
} from './fixtures'
import { fulfillJson, loginThroughUi, mockLogin, navigateTo } from './helpers'

test.describe('View Manufacturer Enrichment', () => {
  test('success state: source reached, verified attributes shown with snippets', async ({
    page,
  }) => {
    await mockLogin(page)
    await page.route('**/api/evaluation-report', (route) =>
      fulfillJson(route, 200, evaluationReportFixture),
    )
    await page.route('**/api/manufacturer-enrichment**', (route) => {
      const url = new URL(route.request().url())
      const record = Number(url.searchParams.get('record') ?? '0')
      return fulfillJson(route, 200, manufacturerEnrichmentSuccessFixture(record))
    })

    await loginThroughUi(page)
    await navigateTo(page, 'Manufacturer Enrichment')

    await expect(page.getByText('SOURCE REACHED')).toBeVisible()
    await expect(
      page.getByText('https://learnwhirlpool.com/product/wdts7024rz'),
    ).toBeVisible()
    await expect(page.getByText('200 OK')).toBeVisible()

    // 4 of 15 attributes verified — the honest count, not a guess.
    await expect(page.getByText('4 / 15 RECOVERED')).toBeVisible()

    // A verified field shows its real value and a VERBATIM badge...
    const seriesRow = page.getByRole('row', { name: /^Series/ })
    await expect(seriesRow.getByText('Eco Series')).toBeVisible()
    await expect(seriesRow.getByText('VERBATIM')).toBeVisible()

    // ...while an unrecovered field is honestly dashed out, not fabricated.
    const capacityRow = page.getByRole('row', { name: /^Capacity/ })
    await expect(capacityRow.getByText('---')).toBeVisible()
    await expect(capacityRow.getByText('NOT RECOVERED')).toBeVisible()

    // The page excerpt with the matched snippet highlighted underneath it
    // (the same sentence also appears verbatim as the Additional Information
    // attribute's value on the right — .first() targets the left-column
    // source excerpt specifically).
    await expect(
      page.getByText(/quietest and largest capacity dishwasher/).first(),
    ).toBeVisible()
  })

  test('timeout failure state: renders the honest "NOT RECOVERED" state for every field, not a crash', async ({
    page,
  }) => {
    await mockLogin(page)
    await page.route('**/api/evaluation-report', (route) =>
      fulfillJson(route, 200, evaluationReportFixture),
    )
    await page.route('**/api/manufacturer-enrichment**', (route) => {
      const url = new URL(route.request().url())
      const record = Number(url.searchParams.get('record') ?? '0')
      return fulfillJson(route, 200, manufacturerEnrichmentTimeoutFixture(record))
    })

    await loginThroughUi(page)
    await navigateTo(page, 'Manufacturer Enrichment')

    // The expected, documented failure mode — a clear status, not a silent
    // blank screen or a thrown error boundary.
    await expect(page.getByText('SOURCE UNREACHABLE (TIMEOUT)')).toBeVisible()
    await expect(
      page.getByText('Source unreachable — request timed out after 10s'),
    ).toBeVisible()
    await expect(page.getByText('TIMEOUT', { exact: true })).toBeVisible()

    // Zero of 15 recovered — every single field honestly unresolved.
    await expect(page.getByText('0 / 15 RECOVERED')).toBeVisible()

    const rows = page.getByRole('row')
    // 15 data rows + 1 header row.
    await expect(rows).toHaveCount(16)

    // Every data row shows the gray-dashed "NOT RECOVERED" state — none
    // show a value or a VERBATIM badge, none crash the table render.
    await expect(page.getByText('NOT RECOVERED')).toHaveCount(15)
    await expect(page.getByText('VERBATIM')).toHaveCount(0)
    await expect(page.getByText('---')).toHaveCount(15)

    // The rest of the screen (pager, back link) is still intact — the
    // failure is contained, not a full-page crash.
    await expect(
      page.getByRole('button', { name: 'Back to Evaluation Report' }),
    ).toBeVisible()
  })
})
