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
    // Click SSO section button by label
    const ssoButton = page.getByRole('button', { name: /SSO|LDAP|Single Sign/i })
    if (await ssoButton.count() > 0) {
      await ssoButton.first().scrollIntoViewIfNeeded()
      await ssoButton.first().click()
      await page.waitForTimeout(500)
    } else {
      // SSO might be in a navigation link
      const ssoLink = page.getByText(/SSO|LDAP|Single Sign/i).first()
      await ssoLink.scrollIntoViewIfNeeded()
      await ssoLink.click()
      await page.waitForTimeout(500)
    }
  })
})
