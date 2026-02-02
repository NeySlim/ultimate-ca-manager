import { test, expect } from '@playwright/test'

/**
 * Dashboard E2E Tests
 */
test.describe('Dashboard', () => {
  test('displays dashboard with stats', async ({ page }) => {
    await page.goto('/dashboard')
    
    // Check stats cards are present (new UI shows count numbers)
    await expect(page.locator('text=/Certificates/i').first()).toBeVisible()
    await expect(page.locator('text=/Authorities/i').first()).toBeVisible()
  })

  test('shows recent activity', async ({ page }) => {
    await page.goto('/dashboard')
    
    // Activity section should be visible
    await expect(page.locator('text=/Recent Activity/i').first()).toBeVisible()
  })

  test('shows recent certificates widget', async ({ page }) => {
    await page.goto('/dashboard')
    
    // Recent certs section
    await expect(page.locator('text=/Recent Certificates/i').first()).toBeVisible()
  })

  test('navigates to certificates from sidebar', async ({ page }) => {
    await page.goto('/dashboard')
    
    // Click on certificates link in sidebar
    await page.locator('a[href*="certificates"]').first().click()
    
    // Should navigate to certificates page
    await expect(page).toHaveURL(/certificates/)
  })
})
