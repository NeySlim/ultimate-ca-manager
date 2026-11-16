import { defineConfig, devices } from '@playwright/test'

// The suite runs against the instance scripts/ci/e2e.sh starts (UCM_E2E_BASE_URL, UCM_E2E_MANAGED=1).
// e2e/lab needs external services: it runs only when UCM_LAB=1 is set.
const lab = process.env.UCM_LAB === '1'
// A restore replaces the whole database: never on an instance the script did not start
const managed = process.env.UCM_E2E_MANAGED === '1' && !lab
const desktop = { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } }
const RESTORE = /backup-restore\.spec\.ts/
// The overview lists the five latest operations: its tests need to be the only ones acting
const OVERVIEW = /overview\.spec\.ts/
const LAB = lab ? [] : ['lab/**']

export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/support/global-setup.ts',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  // A flaky test is fixed, never replayed
  retries: 0,
  workers: process.env.CI ? 4 : 2,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  outputDir: 'test-results',
  use: {
    baseURL: process.env.UCM_E2E_BASE_URL,
    ignoreHTTPSErrors: true,
    locale: 'en-US',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
  },
  projects: [
    { name: 'chromium', use: desktop, testIgnore: [...LAB, RESTORE, OVERVIEW] },
    { name: 'overview', use: desktop, testMatch: [OVERVIEW], dependencies: ['chromium'], fullyParallel: false },
    // A restore replaces the database under every other test: it runs alone, last
    ...(managed ? [{ name: 'restore', use: desktop, testMatch: [RESTORE], dependencies: ['overview'] }] : []),
  ],
})
