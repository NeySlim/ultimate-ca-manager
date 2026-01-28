import { test, expect } from '@playwright/test'

test.describe('Authentication', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login')
  })

  test('shows login page', async ({ page }) => {
    await expect(page.locator('h1, h2').first()).toContainText(/login|sign in/i)
    await expect(page.locator('input[type="text"], input[name="username"]')).toBeVisible()
    await expect(page.locator('input[type="password"]')).toBeVisible()
  })

  test('shows error for invalid credentials', async ({ page }) => {
    await page.fill('input[type="text"], input[name="username"]', 'invalid')
    await page.fill('input[type="password"]', 'invalid')
    await page.click('button[type="submit"]')
    
    // Wait for error message
    await expect(page.locator('text=/invalid|error|failed/i')).toBeVisible({ timeout: 5000 })
  })

  test('successful login redirects to dashboard', async ({ page }) => {
    await page.fill('input[type="text"], input[name="username"]', 'admin')
    await page.fill('input[type="password"]', 'changeme123')
    await page.click('button[type="submit"]')
    
    // Should redirect to dashboard
    await expect(page).toHaveURL(/\/(dashboard)?$/, { timeout: 10000 })
    
    // Dashboard content should be visible
    await expect(page.locator('text=/dashboard|overview|certificates/i').first()).toBeVisible()
  })

  test('logout returns to login page', async ({ page }) => {
    // First login
    await page.fill('input[type="text"], input[name="username"]', 'admin')
    await page.fill('input[type="password"]', 'changeme123')
    await page.click('button[type="submit"]')
    
    // Wait for dashboard
    await expect(page).toHaveURL(/\/(dashboard)?$/, { timeout: 10000 })
    
    // Find and click logout (may be in dropdown)
    const logoutButton = page.locator('text=/logout|sign out/i')
    if (await logoutButton.isVisible()) {
      await logoutButton.click()
    } else {
      // Try user menu
      await page.click('[data-testid="user-menu"], button:has-text("admin")')
      await page.click('text=/logout|sign out/i')
    }
    
    // Should be back at login
    await expect(page).toHaveURL(/\/login/, { timeout: 5000 })
  })
})
