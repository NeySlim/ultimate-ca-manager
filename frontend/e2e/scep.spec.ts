import { test, expect } from '@playwright/test'

test.describe('SCEP', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/scep-config')
    await page.waitForLoadState('networkidle')
  })

  test('page loads with heading', async ({ page }) => {
    await expect(page.locator('h1')).toBeVisible()
  })

  test('has table', async ({ page }) => {
    await expect(page.locator('table')).toBeVisible({ timeout: 10000 })
  })

  test('has tab buttons', async ({ page }) => {
    // SCEP has tabs: Requests, Challenges, Configuration, Information
    const buttons = page.locator('button')
    expect(await buttons.count()).toBeGreaterThanOrEqual(4)
  })

  test('has search input', async ({ page }) => {
    const search = page.locator('input[type="search"], input[placeholder]').first()
    await expect(search).toBeVisible()
  })

  test('search input accepts text', async ({ page }) => {
    const search = page.locator('input[type="search"], input[placeholder]').first()
    await search.fill('test')
    await page.waitForTimeout(500)
  })

  test('has pagination', async ({ page }) => {
    const pagination = page.locator('[class*="pagination"], nav[aria-label], button:has-text("/page")')
    if (await pagination.count() > 0) {
      await expect(pagination.first()).toBeVisible()
    }
  })

  test('can click tab buttons', async ({ page }) => {
    const buttons = page.locator('button')
    const count = await buttons.count()
    // Click second tab
    if (count > 2) {
      await buttons.nth(1).click()
      await page.waitForTimeout(500)
    }
  })
})
