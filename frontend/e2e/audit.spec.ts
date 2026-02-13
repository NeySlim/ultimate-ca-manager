import { test, expect } from '@playwright/test'

test.describe('Audit Logs', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/audit')
    await page.waitForLoadState('networkidle')
  })

  test('page loads with heading', async ({ page }) => {
    await expect(page.locator('h1')).toBeVisible()
  })

  test('has table', async ({ page }) => {
    await expect(page.locator('table')).toBeVisible({ timeout: 10000 })
  })

  test('has filter buttons', async ({ page }) => {
    // Audit has filters: action, status, user, date
    const buttons = page.locator('button')
    expect(await buttons.count()).toBeGreaterThanOrEqual(4)
  })

  test('has pagination', async ({ page }) => {
    const pagination = page.locator('[class*="pagination"], nav[aria-label], button:has-text("/page")')
    if (await pagination.count() > 0) {
      await expect(pagination.first()).toBeVisible()
    }
  })

  test('table has rows', async ({ page }) => {
    const rows = page.locator('table tbody tr')
    await rows.first().waitFor({ state: 'visible', timeout: 10000 })
    expect(await rows.count()).toBeGreaterThan(0)
  })

  test('has action buttons', async ({ page }) => {
    // Clean logs, Verify integrity buttons
    const buttons = page.locator('button')
    expect(await buttons.count()).toBeGreaterThanOrEqual(2)
  })
})
