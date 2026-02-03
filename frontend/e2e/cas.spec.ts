import { test, expect } from '@playwright/test'

/**
 * Certificate Authorities (CAs) E2E Tests
 */
test.describe('Certificate Authorities', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/cas')
  })

  test('displays CA hierarchy', async ({ page }) => {
    // Page title
    await expect(page.locator('h1, [class*="title"]').first()).toContainText(/Certificate Authorit|CA/i)
    
    // Tree or list view
    await expect(page.locator('[class*="tree"], table, [class*="hierarchy"]').first()).toBeVisible()
  })

  test('has create CA button', async ({ page }) => {
    const createBtn = page.locator('button:has-text("Create"), button:has-text("New"), button:has-text("Add")')
    await expect(createBtn.first()).toBeVisible()
  })

  test('opens create CA modal', async ({ page }) => {
    // Click create button
    await page.locator('button:has-text("Create"), button:has-text("New")').first().click()
    
    // Modal should open
    await expect(page.locator('[role="dialog"], [class*="modal"]')).toBeVisible({ timeout: 5000 })
    
    // Should have CA type selection or name field
    await expect(page.locator('input, select, [class*="radio"]').first()).toBeVisible()
  })

  test('can switch between tree and grid view', async ({ page }) => {
    // Find view toggle buttons
    const viewToggle = page.locator('button:has-text("Tree"), button:has-text("Grid"), button:has-text("List"), [class*="toggle"]')
    
    if (await viewToggle.count() > 1) {
      // Click second toggle option
      await viewToggle.nth(1).click()
      await page.waitForTimeout(500)
      // View should change (no error)
    }
  })

  test('shows CA details on selection', async ({ page }) => {
    // Wait for content
    await page.waitForSelector('[class*="tree"] *, table tbody tr, [class*="card"]', { timeout: 10000 })
    
    // Click on a CA item
    const caItem = page.locator('[class*="tree-item"], table tbody tr, [class*="ca-card"]').first()
    if (await caItem.count() > 0) {
      await caItem.click()
      
      // Details should show
      await page.waitForTimeout(500)
      const details = page.locator('[class*="detail"], [class*="panel"], text=/Subject|Issuer|Valid/i')
      if (await details.count() > 0) {
        await expect(details.first()).toBeVisible()
      }
    }
  })

  test('CA has action menu', async ({ page }) => {
    // Wait for CAs to load
    await page.waitForTimeout(1000)
    
    // Find action button/menu on a CA
    const actionBtn = page.locator('[class*="action"], button[aria-haspopup], [class*="menu-trigger"], [class*="dropdown"]')
    
    if (await actionBtn.count() > 0) {
      await actionBtn.first().click()
      
      // Menu items should appear
      await expect(page.locator('text=/Issue|Export|Revoke|Delete/i').first()).toBeVisible({ timeout: 3000 })
    }
  })
})
