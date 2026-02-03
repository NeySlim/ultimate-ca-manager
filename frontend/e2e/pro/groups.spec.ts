import { test, expect } from '@playwright/test'
import { config } from '../config'

/**
 * Groups Management E2E Tests (Pro Feature)
 */
test.describe('Groups (Pro)', () => {
  test.skip(!config.isPro, 'Pro feature - skipped')

  test.beforeEach(async ({ page }) => {
    await page.goto('/groups')
  })

  test('displays groups page', async ({ page }) => {
    await expect(page.locator('h1, [class*="title"]').first()).toContainText(/Groups/i)
  })

  test('shows groups list', async ({ page }) => {
    await expect(page.locator('table, [class*="table"], [class*="list"]').first()).toBeVisible()
  })

  test('has create group button', async ({ page }) => {
    const createBtn = page.locator('button:has-text("Create"), button:has-text("New"), button:has-text("Add")')
    await expect(createBtn.first()).toBeVisible()
  })

  test('opens create group modal', async ({ page }) => {
    await page.locator('button:has-text("Create"), button:has-text("New")').first().click()
    
    await expect(page.locator('[role="dialog"], [class*="modal"]')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('input[name="name"], input[placeholder*="name"]').first()).toBeVisible()
  })

  test('can configure LDAP sync', async ({ page }) => {
    // Look for LDAP sync option
    const ldapOption = page.locator('text=/LDAP|Sync|Directory/i')
    await expect(ldapOption.first()).toBeVisible()
  })

  test('shows group members', async ({ page }) => {
    // Wait for groups to load
    await page.waitForSelector('table tbody tr, [class*="group-card"]', { timeout: 10000 })
    
    // Click on first group
    const groupRow = page.locator('table tbody tr, [class*="group-card"]').first()
    if (await groupRow.count() > 0) {
      await groupRow.click()
      
      // Members section should be visible
      await expect(page.locator('text=/Members|Users/i').first()).toBeVisible({ timeout: 5000 })
    }
  })
})
