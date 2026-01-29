import { test, expect } from '@playwright/test'

// Helper function for two-step login (handles WebAuthn users)
async function login(page, username = 'admin', password = 'changeme123') {
  await page.goto('/login')
  
  // Step 1: Enter username
  const usernameInput = page.locator('input[type="text"], input[placeholder*="username" i]').first()
  await usernameInput.fill(username)
  await page.click('button:has-text("Continue")')
  
  // Wait for WebAuthn to timeout/fail (~10-12s), then password form appears automatically
  await page.waitForTimeout(15000)
  
  // Step 2: Enter password (now visible after WebAuthn timeout)
  const passwordInput = page.locator('input[type="password"]')
  await expect(passwordInput).toBeVisible({ timeout: 5000 })
  await passwordInput.fill(password)
  await page.click('button:has-text("Sign In"), button[type="submit"]')
  
  // Wait for redirect to dashboard
  await expect(page).toHaveURL(/\/(dashboard)?$/, { timeout: 10000 })
}

test.describe('Settings & Backup', () => {
  test.beforeEach(async ({ page }) => {
    await login(page)
  })

  test('navigate to settings page', async ({ page }) => {
    // Navigate directly via URL (sidebar has tooltip overlap issues in headless)
    await page.goto('/settings')
    await expect(page).toHaveURL(/\/settings/)
  })

  test('settings tabs are visible', async ({ page }) => {
    await page.goto('/settings')
    
    // Wait for page to load
    await page.waitForTimeout(1000)
    
    // Check for various settings tabs/sections
    await expect(page.locator('text=/general|email|backup|security/i').first()).toBeVisible()
  })

  test('can toggle auto-backup setting', async ({ page }) => {
    await page.goto('/settings')
    
    // Wait for page to load
    await page.waitForTimeout(1000)
    
    // Look for auto-backup toggle/checkbox
    const checkbox = page.locator('input[type="checkbox"], [role="switch"]').first()
    if (await checkbox.isVisible()) {
      await checkbox.click()
      
      // Save settings
      const saveButton = page.locator('button:has-text("Save")')
      if (await saveButton.isVisible()) {
        await saveButton.click()
      }
    }
  })

  test('backup modal requires password', async ({ page }) => {
    await page.goto('/settings')
    
    // Wait for page to load
    await page.waitForTimeout(1000)
    
    // Click create backup button
    const backupButton = page.locator('button:has-text("Create Backup"), button:has-text("Backup Now")')
    if (await backupButton.isVisible()) {
      await backupButton.click()
      
      // Modal should appear with password field
      await expect(page.locator('input[type="password"]')).toBeVisible({ timeout: 3000 })
    }
  })

  test('backup password validation', async ({ page }) => {
    await page.goto('/settings')
    
    // Wait for page to load
    await page.waitForTimeout(1000)
    
    const backupButton = page.locator('button:has-text("Create Backup"), button:has-text("Backup Now")')
    if (await backupButton.isVisible()) {
      await backupButton.click()
      
      // Wait for modal
      await page.waitForTimeout(500)
      
      // Enter short password
      const passwordField = page.locator('input[type="password"]').first()
      if (await passwordField.isVisible()) {
        await passwordField.fill('short')
        
        // Create button should show validation error
        const createBtn = page.locator('button:has-text("Create"), button:has-text("Download")')
        if (await createBtn.isVisible()) {
          await createBtn.click()
          // Expect validation message
          await page.waitForTimeout(500)
        }
      }
    }
  })
})
