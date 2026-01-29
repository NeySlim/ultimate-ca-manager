import { test, expect } from '@playwright/test'

/**
 * Dashboard E2E Tests
 */
test.describe('Dashboard', () => {
  test('displays dashboard with stats', async ({ page }) => {
    await page.goto('/dashboard')
    
    // Check page title
    await expect(page.locator('h1, [class*="title"]').first()).toContainText(/Dashboard/i)
    
    // Check stats cards are present
    await expect(page.locator('text=/Certificates/i').first()).toBeVisible()
    await expect(page.locator('text=/Certificate Authorities/i').first()).toBeVisible()
  })

  test('shows recent activity', async ({ page }) => {
    await page.goto('/dashboard')
    
    // Activity section should be visible
    await expect(page.locator('text=/Activity|Recent/i').first()).toBeVisible()
  })

  test('shows expiring certificates widget', async ({ page }) => {
    await page.goto('/dashboard')
    
    // Expiring certs section
    await expect(page.locator('text=/Expir/i').first()).toBeVisible()
  })

  test('navigates to certificates from dashboard', async ({ page }) => {
    await page.goto('/dashboard')
    
    // Click on certificates link/card
    await page.locator('a[href*="certificates"], [class*="card"]:has-text("Certificate")').first().click()
    
    // Should navigate to certificates page
    await expect(page).toHaveURL(/certificates/)
  })
})
