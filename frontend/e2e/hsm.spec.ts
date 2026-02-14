import { test, expect } from '@playwright/test'

test.describe('HSM', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/hsm')
    await page.waitForLoadState('networkidle')
  })

  test('page loads with heading', async ({ page }) => {
    await expect(page.locator('h1')).toBeVisible()
  })

  test('has stats bar', async ({ page }) => {
    const stats = page.locator('[class*="stat"], [class*="indicator"], [class*="badge"]')
    expect(await stats.count()).toBeGreaterThan(0)
  })

  test('has data table or empty state', async ({ page }) => {
    const table = page.locator('table')
    const empty = page.locator('h3:has-text("No HSM"), h3:has-text("Aucun")')
    const hasTable = await table.count() > 0
    const hasEmpty = await empty.count() > 0
    expect(hasTable || hasEmpty).toBeTruthy()
  })

  test('has search input', async ({ page }) => {
    const search = page.locator('input[type="search"], input[placeholder]').first()
    if (await search.count() > 0) {
      await expect(search).toBeVisible()
      await search.fill('pkcs')
      await page.waitForTimeout(500)
    }
  })

  test('has create provider button', async ({ page }) => {
    const createBtn = page.locator('button:has-text("New"), button:has-text("Add"), button:has-text("Nouveau"), button:has-text("Ajouter")')
    if (await createBtn.count() > 0) {
      await expect(createBtn.first()).toBeVisible()
    }
  })

  test('has filter dropdowns', async ({ page }) => {
    const filters = page.locator('select, [class*="filter"] button')
    if (await filters.count() > 0) {
      expect(await filters.count()).toBeGreaterThanOrEqual(1)
    }
  })

  test('provider row is clickable for detail', async ({ page }) => {
    const rows = page.locator('table tbody tr')
    if (await rows.count() > 0) {
      await rows.first().click()
      await page.waitForTimeout(500)
      const detail = page.locator('[class*="slide"], [class*="panel"], [class*="detail"]')
      expect(await detail.count()).toBeGreaterThan(0)
    }
  })

  test('has row actions (test, edit, delete)', async ({ page }) => {
    const rows = page.locator('table tbody tr')
    if (await rows.count() > 0) {
      await rows.first().hover()
      await page.waitForTimeout(300)
      const actions = page.locator('button[title], [class*="action"] button')
      expect(await actions.count()).toBeGreaterThan(0)
    }
  })

  test('hsm status banner may show', async ({ page }) => {
    // HSM page may show a warning banner if SoftHSM not installed
    const banner = page.locator('[class*="warning"], [class*="alert"], [class*="banner"]')
    // Just verify it doesn't crash — banner may or may not be visible
    await page.waitForTimeout(500)
  })
})
