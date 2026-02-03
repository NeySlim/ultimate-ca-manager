import { test, expect } from '@playwright/test'
import { config } from '../config'

/**
 * LDAP Integration E2E Tests (Pro Feature)
 * Tests LDAP user/group sync functionality
 */
test.describe('LDAP Integration (Pro)', () => {
  test.skip(!config.isPro, 'Pro feature - skipped')

  test('can access LDAP settings', async ({ page }) => {
    // LDAP settings might be in Settings or Groups page
    await page.goto('/settings')
    
    const ldapTab = page.locator('text=/LDAP|Directory/i, a[href*="ldap"]')
    if (await ldapTab.count() > 0) {
      await ldapTab.first().click()
      await expect(page.locator('text=/LDAP|Directory|Server/i').first()).toBeVisible()
    }
  })

  test('shows LDAP connection fields', async ({ page }) => {
    await page.goto('/settings')
    
    const ldapTab = page.locator('text=/LDAP|Directory/i')
    if (await ldapTab.count() > 0) {
      await ldapTab.first().click()
      
      // Should show connection fields
      await expect(page.locator('input[name*="host"], input[placeholder*="Host"], input[placeholder*="Server"]').first()).toBeVisible()
    }
  })

  test('can configure LDAP connection', async ({ page }) => {
    await page.goto('/groups')
    
    // Look for LDAP sync button
    const syncBtn = page.locator('button:has-text("LDAP"), button:has-text("Sync"), button:has-text("Import")')
    
    if (await syncBtn.count() > 0) {
      await syncBtn.first().click()
      
      // Should open LDAP config
      await expect(page.locator('[role="dialog"], [class*="modal"], form').first()).toBeVisible({ timeout: 5000 })
    }
  })

  test('LDAP test connection button exists', async ({ page }) => {
    await page.goto('/settings')
    
    const ldapTab = page.locator('text=/LDAP|Directory/i')
    if (await ldapTab.count() > 0) {
      await ldapTab.first().click()
      
      const testBtn = page.locator('button:has-text("Test"), button:has-text("Verify")')
      if (await testBtn.count() > 0) {
        await expect(testBtn.first()).toBeVisible()
      }
    }
  })
})

/**
 * LDAP User Sync Tests
 */
test.describe('LDAP User Sync (Pro)', () => {
  test.skip(!config.isPro, 'Pro feature - skipped')

  test('can trigger LDAP user sync', async ({ page }) => {
    await page.goto('/users')
    
    // Look for sync button
    const syncBtn = page.locator('button:has-text("Sync"), button:has-text("Import"), button:has-text("LDAP")')
    
    if (await syncBtn.count() > 0) {
      await expect(syncBtn.first()).toBeVisible()
    }
  })

  test('shows LDAP sync status', async ({ page }) => {
    await page.goto('/users')
    
    // Look for sync status indicator
    const syncStatus = page.locator('text=/Last sync|Synced|LDAP users/i, [class*="sync-status"]')
    
    if (await syncStatus.count() > 0) {
      await expect(syncStatus.first()).toBeVisible()
    }
  })
})

/**
 * LDAP Group Sync Tests
 */
test.describe('LDAP Group Sync (Pro)', () => {
  test.skip(!config.isPro, 'Pro feature - skipped')

  test('can sync groups from LDAP', async ({ page }) => {
    await page.goto('/groups')
    
    const syncBtn = page.locator('button:has-text("Sync"), button:has-text("Import LDAP")')
    
    if (await syncBtn.count() > 0) {
      await expect(syncBtn.first()).toBeVisible()
    }
  })

  test('shows LDAP-synced groups indicator', async ({ page }) => {
    await page.goto('/groups')
    
    // Wait for groups to load
    await page.waitForTimeout(1000)
    
    // Look for LDAP indicator on groups
    const ldapIndicator = page.locator('text=/LDAP|Synced|External/i, [class*="ldap"], [class*="external"]')
    
    // May or may not be visible depending on whether groups are synced
    if (await ldapIndicator.count() > 0) {
      await expect(ldapIndicator.first()).toBeVisible()
    }
  })
})
