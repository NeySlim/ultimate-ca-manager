import { test, expect } from '@playwright/test'

test.describe('Authentication', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login')
  })

  test('shows login page with username step', async ({ page }) => {
    await expect(page.locator('h1, h2').first()).toContainText(/login|sign in/i)
    // Two-step login: first shows username input
    await expect(page.locator('input[type="text"], input[placeholder*="username" i]').first()).toBeVisible()
  })

  test('shows error for invalid credentials', async ({ page }) => {
    // Step 1: Enter username
    const usernameInput = page.locator('input[type="text"], input[placeholder*="username" i]').first()
    await usernameInput.fill('invalid_user')
    
    // Click continue
    await page.click('button:has-text("Continue")')
    
    // Step 2: Enter password (wait for password field to appear)
    const passwordInput = page.locator('input[type="password"]')
    await expect(passwordInput).toBeVisible({ timeout: 5000 })
    await passwordInput.fill('invalid_pass')
    
    // Submit
    await page.click('button:has-text("Sign In"), button[type="submit"]')
    
    // Wait for error message
    await expect(page.locator('text=/invalid|error|failed|incorrect/i')).toBeVisible({ timeout: 5000 })
  })

  test('successful login redirects to dashboard', async ({ page }) => {
    // Step 1: Enter username
    const usernameInput = page.locator('input[type="text"], input[placeholder*="username" i]').first()
    await usernameInput.fill('admin')
    
    // Click continue
    await page.click('button:has-text("Continue")')
    
    // Wait for WebAuthn to timeout/fail (it will try for ~10s, then show password option)
    // After WebAuthn fails, the page shows "Security key cancelled. Use password instead." in a div
    await page.waitForTimeout(15000)
    
    // Now password form should be visible (authMethod auto-switches to password on WebAuthn failure)
    const passwordInput = page.locator('input[type="password"]')
    await expect(passwordInput).toBeVisible({ timeout: 5000 })
    await passwordInput.fill('changeme123')
    
    // Submit
    await page.click('button:has-text("Sign In"), button[type="submit"]')
    
    // Should redirect to dashboard
    await expect(page).toHaveURL(/\/(dashboard)?$/, { timeout: 10000 })
    
    // Dashboard content should be visible
    await expect(page.locator('text=/dashboard|overview|certificates/i').first()).toBeVisible()
  })

  test('logout returns to login page', async ({ page }) => {
    // First login
    const usernameInput = page.locator('input[type="text"], input[placeholder*="username" i]').first()
    await usernameInput.fill('admin')
    await page.click('button:has-text("Continue")')
    
    // Wait for WebAuthn timeout, then password form appears
    await page.waitForTimeout(15000)
    
    const passwordInput = page.locator('input[type="password"]')
    await expect(passwordInput).toBeVisible({ timeout: 5000 })
    await passwordInput.fill('changeme123')
    await page.click('button:has-text("Sign In"), button[type="submit"]')
    
    // Wait for dashboard
    await expect(page).toHaveURL(/\/(dashboard)?$/, { timeout: 10000 })
    
    // Click user button in sidebar (shows username "admin")
    await page.click('button:has-text("admin")')
    await page.waitForTimeout(500)
    
    // Click Sign Out in dropdown
    await page.click('text=Sign Out')
    
    // Should be back at login
    await expect(page).toHaveURL(/\/login/, { timeout: 10000 })
  })
})
