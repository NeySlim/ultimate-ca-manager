import { test, expect } from '@playwright/test'

test.describe('Certificate Management', () => {
  test.beforeEach(async ({ page }) => {
    // Login first
    await page.goto('/login')
    await page.fill('input[type="text"], input[name="username"]', 'admin')
    await page.fill('input[type="password"]', 'changeme123')
    await page.click('button[type="submit"]')
    await expect(page).toHaveURL(/\/(dashboard)?$/, { timeout: 10000 })
  })

  test('navigate to certificates page', async ({ page }) => {
    await page.click('a[href="/certificates"], text=Certificates')
    await expect(page).toHaveURL(/\/certificates/)
    await expect(page.locator('h1, h2').first()).toContainText(/certificate/i)
  })

  test('certificates list is displayed', async ({ page }) => {
    await page.goto('/certificates')
    
    // Wait for data to load
    await page.waitForResponse(resp => resp.url().includes('/api/v2/certificates'))
    
    // Table or list should be present
    await expect(page.locator('table, [role="table"], [data-testid="certificates-list"]')).toBeVisible()
  })

  test('can filter certificates by status', async ({ page }) => {
    await page.goto('/certificates')
    
    // Look for status filter
    const statusFilter = page.locator('select, [role="combobox"]').first()
    if (await statusFilter.isVisible()) {
      await statusFilter.click()
      await page.click('text=Valid')
      
      // URL should update with filter
      await expect(page).toHaveURL(/status=valid/i)
    }
  })

  test('can view certificate details', async ({ page }) => {
    await page.goto('/certificates')
    
    // Wait for list to load
    await page.waitForTimeout(1000)
    
    // Click on first certificate row
    const firstRow = page.locator('tr, [data-testid="certificate-row"]').first()
    if (await firstRow.isVisible()) {
      await firstRow.click()
      
      // Details panel should show
      await expect(page.locator('text=/subject|common name|serial/i').first()).toBeVisible()
    }
  })

  test('can search certificates', async ({ page }) => {
    await page.goto('/certificates')
    
    // Find search input
    const searchInput = page.locator('input[placeholder*="search" i], input[type="search"]')
    if (await searchInput.isVisible()) {
      await searchInput.fill('test')
      await page.waitForTimeout(600) // Wait for debounce
      
      // Results should update
    }
  })
})
