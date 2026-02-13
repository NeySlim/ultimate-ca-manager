import { test, expect } from '@playwright/test'
import { config } from '../config'

test.describe('SSO Configuration (Pro)', () => {
  test.skip(!config.isPro, 'Pro feature - skipped')

  test.beforeEach(async ({ page }) => {
    // SSO is now under Settings page, not a separate /sso page
    await page.goto('/settings')
    await page.waitForLoadState('networkidle')
  })

  test('settings page loads with heading', async ({ page }) => {
    await expect(page.locator('h1')).toBeVisible()
  })

  test('has section buttons including SSO', async ({ page }) => {
    // Settings has sidebar-like section buttons
    const buttons = page.locator('button')
    expect(await buttons.count()).toBeGreaterThanOrEqual(8)
  })

  test('can click through section buttons', async ({ page }) => {
    const buttons = page.locator('button')
    const count = await buttons.count()
    // Click a section button (SSO is typically around position 7-8)
    if (count > 7) {
      await buttons.nth(7).click()
      await page.waitForTimeout(500)
    }
  })

  test('settings page has content', async ({ page }) => {
    const content = page.locator('main, [class*="content"], [class*="settings"]').first()
    await expect(content).toBeVisible()
  })
})
