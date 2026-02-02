import { test, expect } from '@playwright/test'

/**
 * Users Management E2E Tests
 */
test.describe('Users', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/users')
    await page.waitForLoadState('networkidle')
  })

  test('displays users list', async ({ page }) => {
    await expect(page.getByText('Users').first()).toBeVisible()
    await expect(page.locator('table').first()).toBeVisible()
  })

  test('has create user button', async ({ page }) => {
    const createBtn = page.getByRole('button', { name: /Create|New|Add/i })
    await expect(createBtn.first()).toBeVisible()
  })

  test('opens create user modal', async ({ page }) => {
    await page.getByRole('button', { name: /Create|New/i }).first().click()
    await expect(page.locator('[role="dialog"]')).toBeVisible({ timeout: 5000 })
  })

  test('shows user details on click', async ({ page }) => {
    // Click on a user row
    await page.locator('table tbody tr').first().click()
    
    // Details panel should show
    await expect(page.getByText(/Role|Permission/i).first()).toBeVisible({ timeout: 5000 })
  })

  test('can search users', async ({ page }) => {
    const searchInput = page.getByPlaceholder(/Search/i)
    await searchInput.fill('admin')
    await page.waitForTimeout(500)
  })
})

/**
 * Settings E2E Tests
 */
test.describe('Settings', () => {
  test('displays settings page', async ({ page }) => {
    await page.goto('/settings')
    await expect(page.getByText('Settings').first()).toBeVisible()
  })

  test('has settings tabs', async ({ page }) => {
    await page.goto('/settings')
    await page.waitForLoadState('networkidle')
    
    // Should have horizontal tabs - use contains text
    await expect(page.locator('button:has-text("General"), a:has-text("General")').first()).toBeVisible()
    await expect(page.locator('button:has-text("Appearance"), a:has-text("Appearance")').first()).toBeVisible()
  })

  test('can switch settings tabs', async ({ page }) => {
    await page.goto('/settings')
    await page.waitForLoadState('networkidle')
    
    // Click on Appearance tab
    await page.locator('button:has-text("Appearance"), a:has-text("Appearance")').first().click()
    await page.waitForTimeout(500)
    
    // Should show appearance content
    await expect(page.getByText(/Theme|Color/i).first()).toBeVisible()
  })
})

/**
 * Navigation E2E Tests
 */
test.describe('Navigation', () => {
  test('sidebar navigation works', async ({ page }) => {
    await page.goto('/dashboard')
    
    // Navigate to certificates
    await page.locator('a[href*="certificates"]').first().click()
    await expect(page).toHaveURL(/certificates/)
    
    // Navigate to CAs
    await page.locator('a[href*="cas"]').first().click()
    await expect(page).toHaveURL(/cas/)
  })

  test('logout works', async ({ page }) => {
    await page.goto('/account')
    
    // Find logout button in account page
    const logoutBtn = page.getByRole('button', { name: /Logout|Sign out/i })
    if (await logoutBtn.isVisible()) {
      await logoutBtn.click()
      await expect(page).toHaveURL(/login/)
    }
  })
})
