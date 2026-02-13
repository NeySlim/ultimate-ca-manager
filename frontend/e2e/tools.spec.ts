import { test, expect } from '@playwright/test'

test.describe('Certificate Tools', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/tools')
    await page.waitForLoadState('networkidle')
  })

  test('page loads with heading', async ({ page }) => {
    await expect(page.locator('h1')).toBeVisible()
  })

  test('has tool cards', async ({ page }) => {
    // Tools page has tool cards as buttons
    const buttons = page.locator('button')
    expect(await buttons.count()).toBeGreaterThanOrEqual(1)
  })

  test('has content area', async ({ page }) => {
    const content = page.locator('main, [class*="content"], [class*="page"]').first()
    await expect(content).toBeVisible()
  })
})
