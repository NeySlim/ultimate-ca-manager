import { test, expect } from '@playwright/test'

/**
 * ACME E2E Tests
 */
test.describe('ACME', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/acme')
    await page.waitForLoadState('networkidle')
  })

  test('displays ACME page', async ({ page }) => {
    // Page title in header or nav
    await expect(page.locator('text=ACME').first()).toBeVisible()
  })

  test('shows ACME enable toggle', async ({ page }) => {
    // Enable checkbox
    const toggle = page.getByRole('checkbox', { name: /enable acme/i })
    await expect(toggle).toBeVisible({ timeout: 5000 })
  })

  test('shows ACME tabs', async ({ page }) => {
    // Configuration, Accounts, History tabs - may be buttons or tabs
    await expect(page.locator('button:has-text("Configuration"), [role="tab"]:has-text("Configuration")').first()).toBeVisible()
    await expect(page.locator('button:has-text("Accounts"), [role="tab"]:has-text("Accounts")').first()).toBeVisible()
  })

  test('shows Default Issuing CA selector', async ({ page }) => {
    // CA combobox
    const caSelector = page.getByRole('combobox')
    await expect(caSelector.first()).toBeVisible({ timeout: 5000 })
  })

  test('can switch to Accounts tab', async ({ page }) => {
    // Click Accounts tab
    await page.getByRole('button', { name: /accounts/i }).click()
    await page.waitForTimeout(500)
    
    // Should show accounts content
    await expect(page.locator('text=/account|email|registered/i').first()).toBeVisible({ timeout: 5000 })
  })

  test('can switch to History tab', async ({ page }) => {
    // Click History tab
    await page.getByRole('button', { name: /history/i }).click()
    await page.waitForTimeout(500)
    
    // Page should not error (may be empty)
    await page.waitForTimeout(500)
  })

  test('shows stats bar', async ({ page }) => {
    // Stats: Accounts, Active, Certificates
    await expect(page.locator('text=/accounts/i').first()).toBeVisible()
    await expect(page.locator('text=/active/i').first()).toBeVisible()
  })

  test('has refresh button', async ({ page }) => {
    const refreshBtn = page.getByRole('button', { name: /refresh/i })
    await expect(refreshBtn).toBeVisible()
  })

  test('has help button', async ({ page }) => {
    const helpBtn = page.getByRole('button', { name: /help/i })
    await expect(helpBtn).toBeVisible()
  })
})
