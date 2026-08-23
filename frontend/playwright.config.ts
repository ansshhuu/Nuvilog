import { defineConfig, devices } from '@playwright/test'

/**
 * All API calls are intercepted with page.route() in each test (see
 * e2e/mocks.ts) — no FastAPI/Supabase/Gemini backend runs in this suite.
 * That keeps tests hermetic (independent, no real quota spend, no shared
 * data) and fast enough for CI. Only the Vite dev server needs to be up.
 */
const CI = !!process.env.CI

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: CI,
  retries: CI ? 1 : 0,
  workers: CI ? 2 : undefined,
  reporter: CI ? [['github'], ['html', { open: 'never' }]] : 'list',

  use: {
    baseURL: 'http://localhost:5173',
    // Only keep evidence for the run that actually failed.
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    video: 'off',
  },

  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        // Headed locally for debugging, headless in CI.
        headless: CI,
      },
    },
  ],

  webServer: {
    command: 'npm run dev -- --port 5173 --strictPort',
    url: 'http://localhost:5173',
    // Always safe to reuse: a CI runner never has anything pre-bound to this
    // port, and locally it means the suite runs against whatever dev server
    // is already up instead of failing on EADDRINUSE.
    reuseExistingServer: true,
    timeout: 30_000,
  },
})
