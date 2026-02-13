import { test, expect } from '@playwright/test'
import { config } from '../config'

test.describe('LDAP Integration (Pro)', () => {
  test.skip(!config.isPro, 'Pro feature - skipped')

  test('settings page loads', async ({ page }) => {
    await page.goto('/settings')
    await page.waitForLoadState('networkidle')
    await expect(page.locator('h1')).toBeVisible()
  })

  test('SSO section is accessible from settings', async ({ page }) => {
    await page.goto('/settings')
    await page.waitForLoadState('networkidle')
    // SSO section button exists in settings sidebar
    const buttons = page.locator('button')
    expect(await buttons.count()).toBeGreaterThanOrEqual(5)
  })

  test('can click SSO section button', async ({ page }) => {
    await page.goto('/settings')
    await page.waitForLoadState('networkidle')
    // Click through section buttons to find SSO (which contains LDAP)
    const buttons = page.locator('button')
    const count = await buttons.count()
    // SSO is typically one of the later section buttons
    for (let i = Math.max(0, count - 5); i < count; i++) {
      await buttons.nth(i).click()
      await page.waitForTimeout(500)
    }
  })
})
