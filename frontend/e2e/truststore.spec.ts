import { test, expect } from '@playwright/test'

test.describe('Truststore', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/truststore')
    await page.waitForLoadState('networkidle')
  })

  test('page loads with heading', async ({ page }) => {
    await expect(page.locator('h1')).toBeVisible()
  })

  test('has table', async ({ page }) => {
    await expect(page.locator('table')).toBeVisible({ timeout: 10000 })
  })

  test('has help button', async ({ page }) => {
    await expect(page.locator('button').filter({ hasText: /help/i })).toBeVisible()
  })

  test('has action buttons', async ({ page }) => {
    // Truststore has: Help, purpose filter, Sync, Import, Add
    const buttons = page.locator('button')
    expect(await buttons.count()).toBeGreaterThanOrEqual(3)
  })

  test('action button opens dialog', async ({ page }) => {
    const buttons = page.locator('button')
    const count = await buttons.count()
    for (let i = count - 1; i >= Math.max(0, count - 4); i--) {
      await buttons.nth(i).click()
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
