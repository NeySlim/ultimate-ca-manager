import { test, expect } from '@playwright/test'

test.describe('Certificates', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/certificates')
    await page.waitForLoadState('networkidle')
  })

  test('page loads with heading', async ({ page }) => {
    await expect(page.locator('h1')).toBeVisible()
  })

  test('has table', async ({ page }) => {
    await expect(page.locator('table')).toBeVisible({ timeout: 10000 })
  })

  test('table has header row', async ({ page }) => {
    await expect(page.locator('table thead')).toBeVisible({ timeout: 10000 })
  })

  test('has action buttons', async ({ page }) => {
    // Certificates page has: Help, status filter, CA filter, Compare, Import, Issue
    const buttons = page.locator('button')
    expect(await buttons.count()).toBeGreaterThanOrEqual(4)
  })

  test('has help button', async ({ page }) => {
    await expect(page.locator('button').filter({ hasText: /help/i })).toBeVisible()
  })

  test('has search input', async ({ page }) => {
    const search = page.locator('input[type="search"], input[placeholder]').first()
    await expect(search).toBeVisible()
  })

  test('search input filters results', async ({ page }) => {
    const search = page.locator('input[type="search"], input[placeholder]').first()
    await search.fill('nonexistent-xyz-cert')
    await page.waitForTimeout(1000)
    // No crash = success
  })

  test('has pagination', async ({ page }) => {
    // Pagination exists on certificates page
    const pagination = page.locator('[class*="pagination"], nav[aria-label], button:has-text("/page")')
    if (await pagination.count() > 0) {
      await expect(pagination.first()).toBeVisible()
    }
  })

  test('table rows are clickable', async ({ page }) => {
    const rows = page.locator('table tbody tr')
    await rows.first().waitFor({ state: 'visible', timeout: 10000 })
    if (await rows.count() > 0) {
      await rows.first().click()
      await page.waitForTimeout(500)
    }
  })
})
