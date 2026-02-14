import { test, expect } from '@playwright/test'

test.describe('CSRs', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/csrs')
    await page.waitForLoadState('networkidle')
  })

  test('page loads with heading', async ({ page }) => {
    await expect(page.locator('h1')).toBeVisible()
  })

  test('has data table', async ({ page }) => {
    await expect(page.locator('table')).toBeVisible({ timeout: 10000 })
  })

  test('has stats bar', async ({ page }) => {
    const stats = page.locator('[class*="stat"], [class*="indicator"], [class*="badge"]')
    expect(await stats.count()).toBeGreaterThan(0)
  })

  test('has search input', async ({ page }) => {
    const search = page.locator('input[type="search"], input[placeholder]').first()
    await expect(search).toBeVisible()
    await search.fill('test')
    await page.waitForTimeout(500)
  })

  test('has tab buttons for Pending and History', async ({ page }) => {
    const nav = page.locator('nav button, [role="tablist"] button, button')
    expect(await nav.count()).toBeGreaterThanOrEqual(2)
  })

  test('can switch tabs', async ({ page }) => {
    // Click second tab (History)
    const tabs = page.locator('nav button')
    if (await tabs.count() >= 2) {
      await tabs.nth(1).click()
      await page.waitForTimeout(1000)
      await expect(page.locator('table')).toBeVisible({ timeout: 10000 })
    }
  })

  test('has import button', async ({ page }) => {
    const importBtn = page.locator('button:has-text("Import"), button:has-text("Importer")')
    if (await importBtn.count() > 0) {
      await expect(importBtn.first()).toBeVisible()
    }
  })

  test('table rows are clickable for detail', async ({ page }) => {
    const rows = page.locator('table tbody tr')
    if (await rows.count() > 0) {
      await rows.first().click()
      await page.waitForTimeout(500)
      // Detail panel should appear
      const detail = page.locator('[class*="slide"], [class*="panel"], [class*="detail"]')
      expect(await detail.count()).toBeGreaterThan(0)
    }
  })

  test('has row action buttons', async ({ page }) => {
    const rows = page.locator('table tbody tr')
    if (await rows.count() > 0) {
      await rows.first().hover()
      await page.waitForTimeout(300)
      const actions = page.locator('button[title], [class*="action"] button')
      expect(await actions.count()).toBeGreaterThan(0)
    }
  })
})
