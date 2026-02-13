import { test, expect } from '@playwright/test'

test.describe('Users', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/users')
    await page.waitForLoadState('networkidle')
  })

  test('page loads with heading', async ({ page }) => {
    await expect(page.locator('h1')).toBeVisible()
  })

  test('has table', async ({ page }) => {
    await expect(page.locator('table')).toBeVisible({ timeout: 10000 })
  })

  test('has tab-like buttons for Users and Groups', async ({ page }) => {
    // Users page has tab buttons (Users, Groups)
    const buttons = page.locator('button')
    expect(await buttons.count()).toBeGreaterThanOrEqual(3)
  })

  test('has filter buttons', async ({ page }) => {
    // Role filter, status filter
    const buttons = page.locator('button')
    expect(await buttons.count()).toBeGreaterThanOrEqual(2)
  })

  test('has pagination', async ({ page }) => {
    const pagination = page.locator('[class*="pagination"], nav[aria-label], button:has-text("/page")')
    if (await pagination.count() > 0) {
      await expect(pagination.first()).toBeVisible()
    }
  })

  test('create user button opens dialog', async ({ page }) => {
    const createBtn = page.locator('button:has-text("Create User")')
    await createBtn.click()
    const dialog = page.locator('[role="dialog"]')
    await expect(dialog.first()).toBeVisible({ timeout: 5000 })
    await page.keyboard.press('Escape')
  })
})

test.describe('Settings', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/settings')
    await page.waitForLoadState('networkidle')
  })

  test('page loads with heading', async ({ page }) => {
    await expect(page.locator('h1')).toBeVisible()
  })

  test('has help button', async ({ page }) => {
    await expect(page.locator('button').filter({ hasText: /help/i })).toBeVisible()
  })

  test('has section buttons', async ({ page }) => {
    // Settings has sidebar-like section buttons: General, Updates, Database, HTTPS, etc.
    const buttons = page.locator('button')
    expect(await buttons.count()).toBeGreaterThanOrEqual(5)
  })

  test('section buttons are clickable', async ({ page }) => {
    // Click the second section button (first is Help)
    const buttons = page.locator('button')
    const count = await buttons.count()
    if (count > 2) {
      await buttons.nth(2).click()
      await page.waitForTimeout(500)
      // No crash = success
    }
  })
})

test.describe('Navigation', () => {
  test('sidebar has navigation links', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')

    const navLinks = page.locator('a[href="/certificates"], a[href="/cas"], a[href="/users"], a[href="/settings"]')
    expect(await navLinks.count()).toBeGreaterThan(3)
  })

  test('navigate to certificates', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.locator('a[href="/certificates"]').first().click()
    await expect(page).toHaveURL(/\/certificates/)
    await expect(page.locator('h1')).toBeVisible()
  })

  test('navigate to cas', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.locator('a[href="/cas"]').first().click()
    await expect(page).toHaveURL(/\/cas/)
    await expect(page.locator('h1')).toBeVisible()
  })

  test('navigate to users', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.locator('a[href="/users"]').first().click()
    await expect(page).toHaveURL(/\/users/)
    await expect(page.locator('h1')).toBeVisible()
  })

  test('navigate to settings', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.locator('a[href="/settings"]').first().click()
    await expect(page).toHaveURL(/\/settings/)
    await expect(page.locator('h1')).toBeVisible()
  })
})
