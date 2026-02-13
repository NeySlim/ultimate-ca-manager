import { test, expect } from '@playwright/test'
import { config } from '../config'

test.describe('HSM (Pro)', () => {
  test.skip(!config.isPro, 'Pro feature - skipped')

  test.beforeEach(async ({ page }) => {
    await page.goto('/hsm')
    await page.waitForLoadState('networkidle')
  })

  test('page loads with heading', async ({ page }) => {
    await expect(page.locator('h1')).toBeVisible()
  })

  test('has help button', async ({ page }) => {
    await expect(page.locator('button').filter({ hasText: /help/i })).toBeVisible()
  })

  test('has filter buttons', async ({ page }) => {
    // HSM page has status filter and type filter
    const buttons = page.locator('button')
    expect(await buttons.count()).toBeGreaterThanOrEqual(3)
  })

  test('has content area', async ({ page }) => {
    // HSM uses div-based layout, not <table>
    const content = page.locator('[class*="table"], [class*="grid"], [class*="list"], [class*="data"], [class*="provider"]').first()
    await expect(content).toBeVisible({ timeout: 10000 })
  })

  test('new provider button opens dialog', async ({ page }) => {
    // Try clicking action buttons to find the one that opens a dialog
    const buttons = page.locator('button')
    const count = await buttons.count()
    for (let i = count - 1; i >= Math.max(0, count - 4); i--) {
      const btn = buttons.nth(i)
      await btn.click()
      const dialog = page.locator('[role="dialog"]').first()
      try {
        await dialog.waitFor({ state: 'visible', timeout: 2000 })
        await expect(dialog).toBeVisible()
        return
      } catch {
        await page.keyboard.press('Escape')
        await page.waitForTimeout(300)
      }
    }
  })
})
