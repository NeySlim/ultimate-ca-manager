import { test, expect } from '@playwright/test'

test.describe('ACME', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/acme')
    await page.waitForLoadState('networkidle')
  })

  test('page loads with heading', async ({ page }) => {
    await expect(page.locator('h1')).toBeVisible()
  })

  test('has tab buttons', async ({ page }) => {
    // ACME has multiple tabs: Let's Encrypt providers, DNS providers, Domains, ACME Local, etc.
    const buttons = page.locator('button')
    expect(await buttons.count()).toBeGreaterThanOrEqual(5)
  })

  test('has help button', async ({ page }) => {
    await expect(page.locator('button').filter({ hasText: /help/i })).toBeVisible()
  })

  test('can click second tab', async ({ page }) => {
    // Click a tab button (not Help, not the first active tab)
    const buttons = page.locator('button')
    const count = await buttons.count()
    if (count > 3) {
      await buttons.nth(2).click()
      await page.waitForTimeout(500)
    }
  })

  test('can click third tab', async ({ page }) => {
    const buttons = page.locator('button')
    const count = await buttons.count()
    if (count > 4) {
      await buttons.nth(3).click()
      await page.waitForTimeout(500)
    }
  })

  test('has action buttons', async ({ page }) => {
    // Refresh, Help, "Request certificate", "Settings" buttons
    const buttons = page.locator('button')
    expect(await buttons.count()).toBeGreaterThanOrEqual(4)
  })

  test('page has content area', async ({ page }) => {
    // ACME page has content below the tabs
    const content = page.locator('main, [class*="content"], [class*="page"]').first()
    await expect(content).toBeVisible()
  })
})
