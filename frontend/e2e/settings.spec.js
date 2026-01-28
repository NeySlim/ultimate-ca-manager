import { test, expect } from '@playwright/test'

test.describe('Settings & Backup', () => {
  test.beforeEach(async ({ page }) => {
    // Login first
    await page.goto('/login')
    await page.fill('input[type="text"], input[name="username"]', 'admin')
    await page.fill('input[type="password"]', 'changeme123')
    await page.click('button[type="submit"]')
    await expect(page).toHaveURL(/\/(dashboard)?$/, { timeout: 10000 })
  })

  test('navigate to settings page', async ({ page }) => {
    await page.click('a[href="/settings"], text=Settings')
    await expect(page).toHaveURL(/\/settings/)
  })

  test('settings tabs are visible', async ({ page }) => {
    await page.goto('/settings')
    
    // Check for various settings tabs
    await expect(page.locator('text=/general|email|backup|security/i').first()).toBeVisible()
  })

  test('can toggle auto-backup setting', async ({ page }) => {
    await page.goto('/settings')
    
    // Navigate to backup tab
    await page.click('text=Backup')
    
    // Find auto-backup checkbox
    const checkbox = page.locator('input[type="checkbox"]').first()
    if (await checkbox.isVisible()) {
      const initialState = await checkbox.isChecked()
      await checkbox.click()
      
      // Save settings
      await page.click('button:has-text("Save")')
      
      // Verify state changed
      const newState = await checkbox.isChecked()
      expect(newState).not.toBe(initialState)
    }
  })

  test('backup modal requires password', async ({ page }) => {
    await page.goto('/settings')
    await page.click('text=Backup')
    
    // Click create backup button
    const backupButton = page.locator('button:has-text("Create Backup")')
    if (await backupButton.isVisible()) {
      await backupButton.click()
      
      // Modal should appear with password field
      await expect(page.locator('input[type="password"]')).toBeVisible()
      await expect(page.locator('text=/password|encrypt/i').first()).toBeVisible()
    }
  })

  test('backup password validation', async ({ page }) => {
    await page.goto('/settings')
    await page.click('text=Backup')
    
    const backupButton = page.locator('button:has-text("Create Backup")')
    if (await backupButton.isVisible()) {
      await backupButton.click()
      
      // Enter short password
      await page.fill('input[type="password"]', 'short')
      
      // Create button should be disabled or show error
      const createBtn = page.locator('button:has-text("Create")')
      // Either disabled or clicking shows error
      if (await createBtn.isEnabled()) {
        await createBtn.click()
        await expect(page.locator('text=/12 characters|too short/i')).toBeVisible({ timeout: 3000 })
      }
    }
  })
})
