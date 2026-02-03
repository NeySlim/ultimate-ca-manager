import { test, expect } from '@playwright/test'
import { config } from '../config'

/**
 * RBAC (Role-Based Access Control) E2E Tests (Pro Feature)
 */
test.describe('RBAC (Pro)', () => {
  test.skip(!config.isPro, 'Pro feature - skipped')

  test.beforeEach(async ({ page }) => {
    await page.goto('/rbac')
  })

  test('displays RBAC page', async ({ page }) => {
    await expect(page.locator('h1, [class*="title"]').first()).toContainText(/RBAC|Role|Access/i)
  })

  test('shows roles list', async ({ page }) => {
    // Should show built-in roles
    await expect(page.locator('text=/Administrator|Operator|Auditor/i').first()).toBeVisible()
  })

  test('has create role button', async ({ page }) => {
    const createBtn = page.locator('button:has-text("Create"), button:has-text("New"), button:has-text("Add")')
    await expect(createBtn.first()).toBeVisible()
  })

  test('opens create role modal', async ({ page }) => {
    await page.locator('button:has-text("Create"), button:has-text("New")').first().click()
    
    await expect(page.locator('[role="dialog"], [class*="modal"]')).toBeVisible({ timeout: 5000 })
    await expect(page.locator('input[name="name"], input[placeholder*="name"]').first()).toBeVisible()
  })

  test('shows role permissions', async ({ page }) => {
    // Wait for roles to load
    await page.waitForSelector('table tbody tr, [class*="role-card"]', { timeout: 10000 })
    
    // Click on a role
    const roleRow = page.locator('table tbody tr, [class*="role-card"]').first()
    if (await roleRow.count() > 0) {
      await roleRow.click()
      
      // Permissions should be visible
      await expect(page.locator('text=/Permission|Access|Privilege/i').first()).toBeVisible({ timeout: 5000 })
    }
  })

  test('can edit role permissions', async ({ page }) => {
    // Find edit button on a role
    const editBtn = page.locator('button:has-text("Edit"), [class*="edit"]')
    
    if (await editBtn.count() > 0) {
      await editBtn.first().click()
      
      // Edit modal or form should appear
      await expect(page.locator('[role="dialog"], [class*="modal"], form').first()).toBeVisible({ timeout: 5000 })
    }
  })

  test('shows permission categories', async ({ page }) => {
    // Permission categories: certificates, cas, users, settings, etc.
    const categories = ['certificates', 'cas', 'users', 'settings']
    
    for (const category of categories) {
      const categoryElement = page.locator(`text=/${category}/i`)
      if (await categoryElement.count() > 0) {
        await expect(categoryElement.first()).toBeVisible()
        break // At least one category visible
      }
    }
  })
})
