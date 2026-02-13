import { test, expect } from '@playwright/test'

test.describe('Account', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/account')
    await page.waitForLoadState('networkidle')
  })

  test('page loads with heading', async ({ page }) => {
    await expect(page.locator('h1')).toBeVisible()
  })

  test('has tab buttons', async ({ page }) => {
    // Account has tabs: Profile, Security, API Keys
    const buttons = page.locator('button')
    expect(await buttons.count()).toBeGreaterThanOrEqual(3)
  })

  test('can click tab buttons', async ({ page }) => {
    const buttons = page.locator('button')
    const count = await buttons.count()
    if (count > 1) {
      await buttons.nth(1).click()
      await page.waitForTimeout(500)
    }
  })

  test('has content area', async ({ page }) => {
    const content = page.locator('main, [class*="content"], [class*="page"]').first()
    await expect(content).toBeVisible()
  })

  test('has action button', async ({ page }) => {
    // Account has Edit/Modify button
    const buttons = page.locator('button')
    expect(await buttons.count()).toBeGreaterThanOrEqual(2)
  })
})
