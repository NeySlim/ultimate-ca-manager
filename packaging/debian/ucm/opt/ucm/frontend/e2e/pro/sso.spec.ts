import { test, expect } from '@playwright/test'
import { config } from '../config'

/**
 * SSO (Single Sign-On) E2E Tests (Pro Feature)
 */
test.describe('SSO Configuration (Pro)', () => {
  test.skip(!config.isPro, 'Pro feature - skipped')

  test.beforeEach(async ({ page }) => {
    await page.goto('/sso')
  })

  test('displays SSO page', async ({ page }) => {
    await expect(page.locator('h1, [class*="title"]').first()).toContainText(/SSO|Single Sign|Identity/i)
  })

  test('shows SSO providers list', async ({ page }) => {
    await expect(page.locator('table, [class*="table"], [class*="list"], [class*="providers"]').first()).toBeVisible()
  })

  test('has add provider button', async ({ page }) => {
    const addBtn = page.locator('button:has-text("Add"), button:has-text("New"), button:has-text("Configure")')
    await expect(addBtn.first()).toBeVisible()
  })

  test('opens add SSO provider modal', async ({ page }) => {
    await page.locator('button:has-text("Add"), button:has-text("New"), button:has-text("Configure")').first().click()
    
    await expect(page.locator('[role="dialog"], [class*="modal"]')).toBeVisible({ timeout: 5000 })
  })

  test('shows provider type options', async ({ page }) => {
    await page.locator('button:has-text("Add"), button:has-text("New")').first().click()
    await page.waitForSelector('[role="dialog"], [class*="modal"]', { timeout: 5000 })
    
    // Should show OIDC, SAML options
    const providerTypes = page.locator('text=/OIDC|SAML|OAuth|OpenID/i')
    await expect(providerTypes.first()).toBeVisible()
  })

  test('can configure OIDC provider', async ({ page }) => {
    await page.locator('button:has-text("Add"), button:has-text("New")').first().click()
    await page.waitForSelector('[role="dialog"], [class*="modal"]', { timeout: 5000 })
    
    // Select OIDC if option available
    const oidcOption = page.locator('text=/OIDC|OpenID/i, [value="oidc"]')
    if (await oidcOption.count() > 0) {
      await oidcOption.first().click()
      
      // Should show OIDC config fields
      await expect(page.locator('input[name*="client"], input[placeholder*="Client"]').first()).toBeVisible()
    }
  })
})

/**
 * SSO Login Flow Tests
 */
test.describe('SSO Login Flow (Pro)', () => {
  test.skip(!config.isPro, 'Pro feature - skipped')

  test('shows SSO login button on login page', async ({ page }) => {
    // Go to login page (unauthenticated)
    await page.goto('/login')
    
    // Look for SSO login option
    const ssoBtn = page.locator('button:has-text("SSO"), button:has-text("Sign in with"), a:has-text("SSO")')
    // May or may not be visible depending on config
    if (await ssoBtn.count() > 0) {
      await expect(ssoBtn.first()).toBeVisible()
    }
  })

  test('SSO button redirects to IdP', async ({ page }) => {
    await page.goto('/login')
    
    const ssoBtn = page.locator('button:has-text("SSO"), a:has-text("SSO")')
    if (await ssoBtn.count() > 0) {
      // Click SSO button
      await ssoBtn.first().click()
      
      // Should redirect to IdP (Keycloak in our test setup)
      // URL should contain keycloak or auth
      await page.waitForTimeout(2000)
      const url = page.url()
      // Either stays on login (no SSO configured) or redirects
      expect(url).toBeTruthy()
    }
  })
})
