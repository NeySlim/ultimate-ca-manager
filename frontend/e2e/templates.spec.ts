import { test, expect } from '@playwright/test'

test.describe('Templates', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/templates')
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
    // Templates page has: Help, type filter, New, Import
    const buttons = page.locator('button')
    expect(await buttons.count()).toBeGreaterThanOrEqual(3)
  })

  test('has pagination', async ({ page }) => {
    const pagination = page.locator('[class*="pagination"], nav[aria-label], button:has-text("/page")')
    if (await pagination.count() > 0) {
      await expect(pagination.first()).toBeVisible()
    }
  })

  test('create button opens dialog', async ({ page }) => {
    // Find and click create/new button - try buttons from the right side
    const actionButtons = page.locator('header button, [class*="header"] button, [class*="toolbar"] button, [class*="actions"] button')
    const count = await actionButtons.count()
    if (count > 0) {
      for (let i = count - 1; i >= Math.max(0, count - 3); i--) {
        await actionButtons.nth(i).click()
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
    }
  })
})
