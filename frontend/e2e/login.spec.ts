import { expect, test } from '@playwright/test'

import { evaluationReportFixture, VALID_EMAIL, VALID_PASSWORD } from './fixtures'
import { expectStillOnLoginScreen, fulfillJson, loginThroughUi, mockLogin } from './helpers'

test.describe('Login', () => {
  test('valid credentials land on the app (Evaluation Report, the default screen)', async ({
    page,
  }) => {
    await mockLogin(page)
    // The app lands on Evaluation Report immediately after login, so that
    // fetch needs a stub too — this test is about the login->app transition,
    // not the report's content (evaluation-report.spec.ts owns that).
    await page.route('**/api/evaluation-report', (route) =>
      fulfillJson(route, 200, evaluationReportFixture),
    )

    await loginThroughUi(page)

    await expect(page.getByRole('heading', { name: 'Evaluation Report' })).toBeVisible()
    // The real identity, not a placeholder — confirms the session round-tripped.
    await expect(page.getByText(VALID_EMAIL)).toBeVisible()
    await expect(page.getByText('ADMIN', { exact: true })).toBeVisible()
  })

  test('wrong password shows an error and does not enter the app', async ({ page }) => {
    await mockLogin(page)

    await loginThroughUi(page, VALID_EMAIL, 'definitely-not-the-password')

    await expect(page.getByText('Invalid email or password.')).toBeVisible()
    await expectStillOnLoginScreen(page)
    // No nav landed either — the failed attempt must not leave any trace of
    // a session behind for a later action to pick up.
    await expect(page.getByRole('navigation', { name: 'Main' })).toBeHidden()
  })

  test('session persists across a reload (localStorage-backed)', async ({ page }) => {
    await mockLogin(page)
    await page.route('**/api/evaluation-report', (route) =>
      fulfillJson(route, 200, evaluationReportFixture),
    )

    await loginThroughUi(page)
    await expect(page.getByRole('heading', { name: 'Evaluation Report' })).toBeVisible()

    await page.reload()

    await expect(page.getByRole('heading', { name: 'Evaluation Report' })).toBeVisible()
    await expectLoginFormGone(page)
  })
})

async function expectLoginFormGone(page: import('@playwright/test').Page) {
  await expect(page.getByLabel('Email')).toBeHidden()
}
