import { test, expect } from '@playwright/test'

/**
 * Certificate Authorities (CAs) E2E Tests
 */
test.describe('Certificate Authorities', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/cas')
    await page.waitForLoadState('networkidle')
  })

  test('displays CA list', async ({ page }) => {
    // Page title
    await expect(page.getByText('Certificate Authorities')).toBeVisible()
    
    // Stats badges
    await expect(page.getByText(/Root|Intermediate/i).first()).toBeVisible()
  })

  test('has create CA button', async ({ page }) => {
    const createBtn = page.getByRole('button', { name: /Create/i })
    await expect(createBtn).toBeVisible()
  })

  test('opens create CA modal', async ({ page }) => {
    // Click create button
    await page.getByRole('button', { name: /Create/i }).click()
    
    // Modal should open
    await expect(page.locator('[role="dialog"]')).toBeVisible({ timeout: 5000 })
  })

  test('CA list displays data', async ({ page }) => {
    // Wait for page to load
    await page.waitForTimeout(1000)
    
    // Page should show "6 CAs" or similar count
    await expect(page.getByText(/\d+\s*CAs?/i).first()).toBeVisible()
  })

  test('has import button', async ({ page }) => {
    const importBtn = page.getByRole('button', { name: /Import/i })
    await expect(importBtn).toBeVisible()
  })
})
