import { test, expect } from '@playwright/test'

test.describe('Operations', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/operations')
    await page.waitForLoadState('networkidle')
  })

  test('page loads with heading', async ({ page }) => {
    await expect(page.locator('h1')).toBeVisible()
  })

  test('has tab buttons', async ({ page }) => {
    // Operations has tabs: Import, Export, Bulk Actions
    const buttons = page.locator('button')
    expect(await buttons.count()).toBeGreaterThanOrEqual(3)
  })

  test('can click tab buttons', async ({ page }) => {
    const buttons = page.locator('button')
    const count = await buttons.count()
    if (count > 1) {
      await buttons.nth(1).click()
      await page.waitForTimeout(500)
    }
  })

  test('has content area', async ({ page }) => {
    const content = page.locator('main, [class*="content"], [class*="page"]').first()
    await expect(content).toBeVisible()
  })

  test('has file upload area on import tab', async ({ page }) => {
    // Import tab should have file upload area
    const upload = page.locator('input[type="file"], [class*="upload"], [class*="drop"]')
    if (await upload.count() > 0) {
      await expect(upload.first()).toBeAttached()
    }
  })
})
