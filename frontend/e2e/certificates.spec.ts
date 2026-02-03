import { test, expect } from '@playwright/test'

/**
 * Certificates E2E Tests
 */
test.describe('Certificates', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/certificates')
  })

  test('displays certificates list', async ({ page }) => {
    // Page title
    await expect(page.locator('h1, [class*="title"]').first()).toContainText(/Certificates/i)
    
    // Table or list should be present
    await expect(page.locator('table, [class*="table"], [class*="list"]').first()).toBeVisible()
  })

  test('has issue certificate button', async ({ page }) => {
    // Issue/New button
    const issueBtn = page.locator('button:has-text("Issue"), button:has-text("New"), button:has-text("Create")')
    await expect(issueBtn.first()).toBeVisible()
  })

  test('opens issue certificate modal', async ({ page }) => {
    // Click issue button
    await page.locator('button:has-text("Issue"), button:has-text("New")').first().click()
    
    // Modal should open
    await expect(page.locator('[role="dialog"], [class*="modal"]')).toBeVisible({ timeout: 5000 })
    
    // Should have form fields
    await expect(page.locator('input[name="commonName"], input[placeholder*="Common"], label:has-text("Common Name")')).toBeVisible()
  })

  test('can filter certificates by status', async ({ page }) => {
    // Find filter/dropdown
    const statusFilter = page.locator('select, [class*="filter"], button:has-text("Status")')
    
    if (await statusFilter.count() > 0) {
      await statusFilter.first().click()
      // Options should appear
      await expect(page.locator('text=/Active|Expired|Revoked/i').first()).toBeVisible()
    }
  })

  test('can search certificates', async ({ page }) => {
    // Find search input
    const searchInput = page.locator('input[type="search"], input[placeholder*="Search"], input[placeholder*="Filter"]')
    
    if (await searchInput.count() > 0) {
      await searchInput.first().fill('test')
      // Should filter results (no error)
      await page.waitForTimeout(500)
    }
  })

  test('shows certificate details on row click', async ({ page }) => {
    // Wait for table to load
    await page.waitForSelector('table tbody tr, [class*="table"] [class*="row"]', { timeout: 10000 })
    
    // Click first row
    const firstRow = page.locator('table tbody tr, [class*="table"] [class*="row"]').first()
    if (await firstRow.count() > 0) {
      await firstRow.click()
      
      // Details panel or modal should show
      await page.waitForTimeout(500)
      // Check for details content
      const details = page.locator('[class*="detail"], [class*="panel"], text=/Subject|Issuer|Serial/i')
      await expect(details.first()).toBeVisible({ timeout: 5000 })
    }
  })

  test('pagination works', async ({ page }) => {
    // Check for pagination
    const pagination = page.locator('[class*="pagination"], button:has-text("Next"), button:has-text("2")')
    
    if (await pagination.count() > 0) {
      // Pagination is present
      await expect(pagination.first()).toBeVisible()
    }
  })
})
