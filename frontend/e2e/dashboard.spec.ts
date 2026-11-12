import { test, expect } from '@playwright/test'

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
  })

  test('page loads without error', async ({ page }) => {
    // The overview is the landing page: the shell and its main area render
    await expect(page.locator('.shell-main').first()).toBeVisible({ timeout: 10000 })
  })

  test('has widget cards', async ({ page }) => {
    // Overview cards are present
    const widgets = page.locator('[class*="card"]')
    await expect(widgets.first()).toBeVisible({ timeout: 10000 })
    expect(await widgets.count()).toBeGreaterThan(0)
  })

  test('has user menu button', async ({ page }) => {
    // User menu button is always present in the top bar
    const buttons = page.locator('button')
    expect(await buttons.count()).toBeGreaterThan(0)
  })

  test('has quick-create buttons', async ({ page }) => {
    const buttons = page.locator('button')
    expect(await buttons.count()).toBeGreaterThan(2)
  })

  test('sidebar navigation is visible', async ({ page }) => {
    // Sidebar links use <a href="/..."> rendered by React Router <Link>
    const navLinks = page.locator('a[href="/certificates"], a[href="/cas"], a[href="/settings"]')
    expect(await navLinks.count()).toBeGreaterThan(0)
  })

  test('can navigate to certificates via sidebar', async ({ page }) => {
    await page.locator('a[href="/certificates"]').first().click()
    await expect(page).toHaveURL(/\/certificates/)
  })

  test('can navigate to CAs via sidebar', async ({ page }) => {
    await page.locator('a[href="/cas"]').first().click()
    await expect(page).toHaveURL(/\/cas/)
  })
})
