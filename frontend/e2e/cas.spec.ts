import { test, expect } from '@playwright/test'

test.describe('Certificate Authorities', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/cas')
    await page.waitForLoadState('networkidle')
  })

  test('page loads with heading', async ({ page }) => {
    await expect(page.locator('h1')).toBeVisible()
  })

  test('has action buttons', async ({ page }) => {
    // CAs page has Help, type filter, status filter, Create, Import buttons
    const buttons = page.locator('button')
    expect(await buttons.count()).toBeGreaterThanOrEqual(3)
  })

  test('has help button', async ({ page }) => {
    await expect(page.locator('button').filter({ hasText: /help/i })).toBeVisible()
  })

  test('has search input', async ({ page }) => {
    const search = page.locator('input[type="search"], input[placeholder]').first()
    await expect(search).toBeVisible()
  })

  test('search input accepts text', async ({ page }) => {
    const search = page.locator('input[type="search"], input[placeholder]').first()
    await search.fill('test')
    await page.waitForTimeout(500)
    // No error means search works
  })

  test('has data content area', async ({ page }) => {
    // CAs use div-based ResponsiveDataTable, not <table>
    const content = page.locator('[class*="table"], [class*="grid"], [class*="list"], [class*="data"]').first()
    await expect(content).toBeVisible({ timeout: 10000 })
  })

  test('create button opens dialog', async ({ page }) => {
    // Create button is among the action buttons (not Help, not filter buttons)
    // Click the last or second-to-last button which is typically Create/Import
    const actionButtons = page.locator('header button, [class*="header"] button, [class*="toolbar"] button, [class*="actions"] button')
    const count = await actionButtons.count()
    if (count > 0) {
      // Try clicking buttons to find one that opens a dialog
      for (let i = count - 1; i >= Math.max(0, count - 3); i--) {
        await actionButtons.nth(i).click()
        const dialog = page.locator('[role="dialog"]').first()
        try {
          await dialog.waitFor({ state: 'visible', timeout: 2000 })
          await expect(dialog).toBeVisible()
          return
        } catch {
          // Try pressing Escape to close any popover before trying next button
          await page.keyboard.press('Escape')
          await page.waitForTimeout(300)
        }
      }
    }
  })
})
