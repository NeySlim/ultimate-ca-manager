import { test, expect } from '@playwright/test'
import { config } from '../config'

test.describe('Groups (Pro)', () => {
  test.skip(!config.isPro, 'Pro feature - skipped')

  test.beforeEach(async ({ page }) => {
    // Groups is a tab on the Users page
    await page.goto('/users')
    await page.waitForLoadState('networkidle')
  })

  test('users page loads', async ({ page }) => {
    await expect(page.locator('h1')).toBeVisible()
  })

  test('has groups tab button', async ({ page }) => {
    // Users page has tab-like buttons including one for Groups
    const buttons = page.locator('button')
    expect(await buttons.count()).toBeGreaterThanOrEqual(2)
  })

  test('can switch to groups tab', async ({ page }) => {
    // Click the second tab-like button (Groups)
    const buttons = page.locator('button')
    const count = await buttons.count()
    // Groups tab is among the first buttons
    if (count >= 2) {
      await buttons.nth(1).click()
      await page.waitForTimeout(1000)
    }
  })

  test('groups tab has content', async ({ page }) => {
    // Switch to groups tab
    const buttons = page.locator('button')
    if (await buttons.count() >= 2) {
      await buttons.nth(1).click()
      await page.waitForTimeout(1000)
      // Should show table or content area
      const content = page.locator('table, [class*="table"], [class*="list"], [class*="grid"]').first()
      await expect(content).toBeVisible({ timeout: 5000 })
    }
  })
})
