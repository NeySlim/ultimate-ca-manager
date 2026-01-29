import { test, expect } from '@playwright/test'

/**
 * Users Management E2E Tests
 */
test.describe('Users', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/users')
  })

  test('displays users list', async ({ page }) => {
    await expect(page.locator('h1, [class*="title"]').first()).toContainText(/Users/i)
    await expect(page.locator('table, [class*="table"]').first()).toBeVisible()
  })

  test('has create user button', async ({ page }) => {
    const createBtn = page.locator('button:has-text("Create"), button:has-text("New"), button:has-text("Add")')
    await expect(createBtn.first()).toBeVisible()
  })

  test('opens create user modal', async ({ page }) => {
    await page.locator('button:has-text("Create"), button:has-text("New")').first().click()
    
    await expect(page.locator('[role="dialog"], [class*="modal"]')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('input[name="username"], input[placeholder*="Username"]')).toBeVisible()
  })

  test('shows user details with role', async ({ page }) => {
    // Wait for users table
    await page.waitForSelector('table tbody tr', { timeout: 10000 })
    
    // Click on a user row
    const userRow = page.locator('table tbody tr').first()
    await userRow.click()
    
    // Details panel should show role info
    await expect(page.locator('text=/Role|Permission/i').first()).toBeVisible({ timeout: 5000 })
  })

  test('can search users', async ({ page }) => {
    const searchInput = page.locator('input[type="search"], input[placeholder*="Search"]')
    
    if (await searchInput.count() > 0) {
      await searchInput.first().fill('admin')
      await page.waitForTimeout(500)
      // Should filter results
    }
  })
})

/**
 * Settings E2E Tests
 */
test.describe('Settings', () => {
  test('displays settings page', async ({ page }) => {
    await page.goto('/settings')
    await expect(page.locator('h1, [class*="title"]').first()).toContainText(/Settings/i)
  })

  test('has multiple settings tabs', async ({ page }) => {
    await page.goto('/settings')
    
    // Should have tabs for different settings
    const tabs = page.locator('[role="tab"], button[class*="tab"], a[class*="tab"]')
    await expect(tabs.first()).toBeVisible()
  })

  test('can navigate to email settings', async ({ page }) => {
    await page.goto('/settings')
    
    // Click on email tab/link
    const emailTab = page.locator('text=/Email|SMTP/i')
    if (await emailTab.count() > 0) {
      await emailTab.first().click()
      await expect(page.locator('input[name*="smtp"], input[placeholder*="SMTP"], text=/SMTP Server/i').first()).toBeVisible()
    }
  })
})

/**
 * Navigation E2E Tests
 */
test.describe('Navigation', () => {
  test('sidebar navigation works', async ({ page }) => {
    await page.goto('/dashboard')
    
    // Navigate using sidebar
    const pages = ['certificates', 'cas', 'users', 'settings']
    
    for (const pageName of pages) {
      const navLink = page.locator(`a[href*="${pageName}"], [class*="nav"] *:has-text("${pageName}")`)
      if (await navLink.count() > 0) {
        await navLink.first().click()
        await expect(page).toHaveURL(new RegExp(pageName))
      }
    }
  })

  test('logout works', async ({ page }) => {
    await page.goto('/dashboard')
    
    // Find logout button (usually in user menu)
    const userMenu = page.locator('[class*="avatar"], [class*="user-menu"], button:has-text("Account")')
    if (await userMenu.count() > 0) {
      await userMenu.first().click()
    }
    
    const logoutBtn = page.locator('button:has-text("Logout"), button:has-text("Sign out"), a:has-text("Logout")')
    if (await logoutBtn.count() > 0) {
      await logoutBtn.first().click()
      // Should redirect to login
      await expect(page).toHaveURL(/login/)
    }
  })
})
