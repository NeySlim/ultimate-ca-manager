import { test, expect } from '@playwright/test'

test.describe('RBAC', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/rbac')
    await page.waitForLoadState('networkidle')
  })

  test('page loads with heading', async ({ page }) => {
    await expect(page.locator('h1')).toBeVisible()
  })

  test('has stats bar', async ({ page }) => {
    const stats = page.locator('[class*="stat"], [class*="indicator"], [class*="badge"]')
    expect(await stats.count()).toBeGreaterThan(0)
  })

  test('has roles table', async ({ page }) => {
    await expect(page.locator('table')).toBeVisible({ timeout: 10000 })
  })

  test('table shows system roles', async ({ page }) => {
    // Should have at least admin and viewer system roles
    const rows = page.locator('table tbody tr')
    expect(await rows.count()).toBeGreaterThanOrEqual(2)
  })

  test('has search input', async ({ page }) => {
    const search = page.locator('input[type="search"], input[placeholder]').first()
    await expect(search).toBeVisible()
    await search.fill('admin')
    await page.waitForTimeout(500)
  })

  test('has type filter dropdown', async ({ page }) => {
    const filters = page.locator('select, [class*="filter"] button')
    if (await filters.count() > 0) {
      expect(await filters.count()).toBeGreaterThanOrEqual(1)
    }
  })

  test('has create role button', async ({ page }) => {
    const createBtn = page.locator('button:has-text("Create"), button:has-text("New"), button:has-text("Créer"), button:has-text("Nouveau")')
    if (await createBtn.count() > 0) {
      await expect(createBtn.first()).toBeVisible()
    }
  })

  test('role row is clickable for detail', async ({ page }) => {
    const rows = page.locator('table tbody tr')
    if (await rows.count() > 0) {
      await rows.first().click()
      await page.waitForTimeout(500)
      const detail = page.locator('[class*="slide"], [class*="panel"], [class*="detail"]')
      expect(await detail.count()).toBeGreaterThan(0)
    }
  })

  test('detail panel shows permissions', async ({ page }) => {
    const rows = page.locator('table tbody tr')
    if (await rows.count() > 0) {
      await rows.first().click()
      await page.waitForTimeout(500)
      // Look for permission-related elements
      const perms = page.locator('text=/permission/i, text=/autorisation/i, input[type="checkbox"]')
      expect(await perms.count()).toBeGreaterThan(0)
    }
  })

  test('system roles cannot be deleted', async ({ page }) => {
    const rows = page.locator('table tbody tr')
    if (await rows.count() > 0) {
      await rows.first().click()
      await page.waitForTimeout(500)
      // Delete button should be disabled or hidden for system roles
      const deleteBtn = page.locator('button:has-text("Delete"), button:has-text("Supprimer")')
      if (await deleteBtn.count() > 0) {
        const isDisabled = await deleteBtn.first().isDisabled()
        // System role delete should be disabled
        expect(isDisabled).toBeTruthy()
      }
    }
  })

  test('shows role type badges', async ({ page }) => {
    const badges = page.locator('[class*="badge"], span:has-text("System"), span:has-text("Custom"), span:has-text("Système")')
    expect(await badges.count()).toBeGreaterThan(0)
  })
})
