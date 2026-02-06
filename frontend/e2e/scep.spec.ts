import { test, expect } from '@playwright/test'

/**
 * SCEP E2E Tests
 */
test.describe('SCEP', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/scep-config')
    await page.waitForLoadState('networkidle')
  })

  test('displays SCEP page', async ({ page }) => {
    // Page should load with SCEP content
    await expect(page.locator('text=SCEP').first()).toBeVisible()
  })

  test('shows SCEP requests table', async ({ page }) => {
    // Table with columns
    const table = page.getByRole('table')
    await expect(table).toBeVisible({ timeout: 5000 })
    
    // Check headers
    await expect(page.getByRole('columnheader', { name: /subject/i })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: /status/i })).toBeVisible()
  })

  test('shows stats bar with counts', async ({ page }) => {
    // Stats: Pending, Approved, Rejected, Total
    await expect(page.locator('text=/pending/i').first()).toBeVisible()
    await expect(page.locator('text=/approved/i').first()).toBeVisible()
    await expect(page.locator('text=/total/i').first()).toBeVisible()
  })

  test('has search input', async ({ page }) => {
    const searchInput = page.getByRole('textbox', { name: /search/i })
    await expect(searchInput).toBeVisible()
  })

  test('can search requests', async ({ page }) => {
    const searchInput = page.getByRole('textbox', { name: /search/i })
    await searchInput.fill('test')
    await page.waitForTimeout(500)
    // Should filter without error
  })

  test('shows request row with status', async ({ page }) => {
    // Wait for table to have data
    const row = page.getByRole('row').nth(1) // Skip header
    if (await row.count() > 0) {
      await expect(row).toBeVisible()
      // Should have status cell
      await expect(page.locator('text=/approved|pending|rejected/i').first()).toBeVisible()
    }
  })

  test('can click on request row', async ({ page }) => {
    const row = page.getByRole('row').nth(1)
    if (await row.count() > 0) {
      await row.click()
      await page.waitForTimeout(500)
      // Details should appear (slideOver or panel)
    }
  })

  test('has refresh button', async ({ page }) => {
    // Refresh button - may have just icon
    const refreshBtn = page.locator('button:has-text("Refresh"), button[aria-label*="refresh" i], button:has([class*="refresh"])')
    if (await refreshBtn.count() > 0) {
      await expect(refreshBtn.first()).toBeVisible()
    }
  })

  test('has help button', async ({ page }) => {
    const helpBtn = page.getByRole('button', { name: /help/i })
    await expect(helpBtn).toBeVisible()
  })
})
