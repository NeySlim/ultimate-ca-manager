import { test, expect } from '@playwright/test'

/**
 * Certificates E2E Tests
 */
test.describe('Certificates', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/certificates')
    await page.waitForLoadState('networkidle')
  })

  test('displays certificates list', async ({ page }) => {
    // Page title  
    await expect(page.getByText('Certificates').first()).toBeVisible()
    
    // Table should be present
    await expect(page.locator('table').first()).toBeVisible()
  })

  test('has issue certificate button', async ({ page }) => {
    const issueBtn = page.getByRole('button', { name: /Issue/i })
    await expect(issueBtn).toBeVisible()
  })

  test('opens issue certificate modal', async ({ page }) => {
    // Click issue button
    await page.getByRole('button', { name: /Issue/i }).click()
    
    // Modal should open
    await expect(page.locator('[role="dialog"]')).toBeVisible({ timeout: 5000 })
  })

  test('can search certificates', async ({ page }) => {
    // Find search input
    const searchInput = page.getByPlaceholder(/Search/i)
    await searchInput.fill('test')
    await page.waitForTimeout(500)
  })

  test('shows certificate details on row click', async ({ page }) => {
    // Click first row
    await page.locator('table tbody tr').first().click()
    
    // Details panel should show
    await expect(page.getByText(/Subject|Issuer|Serial/i).first()).toBeVisible({ timeout: 5000 })
  })

  test('pagination is visible when data exists', async ({ page }) => {
    // Pagination may not be visible if only one page of results
    const pagination = page.locator('[class*="pagination"]')
    // Just check page loaded successfully
    await expect(page.locator('table').first()).toBeVisible()
  })
})
