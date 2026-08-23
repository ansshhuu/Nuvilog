import type { Page, Route } from '@playwright/test'
import { expect } from '@playwright/test'

import {
  LOGIN_FAILURE_RESPONSE,
  LOGIN_SUCCESS_RESPONSE,
  VALID_EMAIL,
  VALID_PASSWORD,
} from './fixtures'

/** Fulfil `route` with a JSON body, matching FastAPI's default response shape. */
export async function fulfillJson(route: Route, status: number, body: unknown) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

/**
 * Stub POST /api/login for the whole test. Every spec calls this before
 * logging in through the real form — no test reaches into localStorage to
 * skip the login screen, so the suite exercises the actual login flow every
 * time and stays independent of any other test's session state.
 */
export async function mockLogin(page: Page) {
  await page.route('**/api/login', async (route) => {
    const body = route.request().postDataJSON() as { email: string; password: string }
    if (body.email === VALID_EMAIL && body.password === VALID_PASSWORD) {
      await fulfillJson(route, 200, LOGIN_SUCCESS_RESPONSE)
    } else {
      await fulfillJson(route, 401, LOGIN_FAILURE_RESPONSE)
    }
  })
}

/** Log in through the real UI (mockLogin must already be installed). */
export async function loginThroughUi(
  page: Page,
  email: string = VALID_EMAIL,
  password: string = VALID_PASSWORD,
) {
  await page.goto('/')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: /sign in/i }).click()
}

/** Navigate to one of the 4 real screens via the sidebar, by its aria-label. */
export async function navigateTo(
  page: Page,
  label: 'Evaluation Report' | 'Description Formats' | 'Manufacturer Enrichment' | 'Settings',
) {
  await page.getByRole('button', { name: label, exact: true }).click()
}

/** Asserts the app is showing the login screen (used by the wrong-credentials test). */
export async function expectStillOnLoginScreen(page: Page) {
  await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible()
}
