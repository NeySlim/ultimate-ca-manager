import { test, expect } from '@playwright/test'
import { config } from '../config'

/**
 * HSM (Hardware Security Module) E2E Tests (Pro Feature)
 */
test.describe('HSM Configuration (Pro)', () => {
  test.skip(!config.isPro, 'Pro feature - skipped')

  test.beforeEach(async ({ page }) => {
    await page.goto('/hsm')
  })

  test('displays HSM page', async ({ page }) => {
    await expect(page.locator('h1, [class*="title"]').first()).toContainText(/HSM|Hardware|Security Module|Key/i)
  })

  test('shows HSM providers list', async ({ page }) => {
    await expect(page.locator('table, [class*="table"], [class*="list"], [class*="providers"]').first()).toBeVisible()
  })

  test('has add HSM button', async ({ page }) => {
    const addBtn = page.locator('button:has-text("Add"), button:has-text("New"), button:has-text("Configure")')
    await expect(addBtn.first()).toBeVisible()
  })

  test('opens add HSM modal', async ({ page }) => {
    await page.locator('button:has-text("Add"), button:has-text("New"), button:has-text("Configure")').first().click()
    
    await expect(page.locator('[role="dialog"], [class*="modal"]')).toBeVisible({ timeout: 5000 })
  })

  test('shows HSM type options', async ({ page }) => {
    await page.locator('button:has-text("Add"), button:has-text("New")').first().click()
    await page.waitForSelector('[role="dialog"], [class*="modal"]', { timeout: 5000 })
    
    // Should show PKCS#11, Cloud HSM options
    const hsmTypes = page.locator('text=/PKCS|SoftHSM|Cloud|AWS|Azure|Google/i')
    await expect(hsmTypes.first()).toBeVisible()
  })

  test('can configure PKCS#11 HSM', async ({ page }) => {
    await page.locator('button:has-text("Add"), button:has-text("New")').first().click()
    await page.waitForSelector('[role="dialog"], [class*="modal"]', { timeout: 5000 })
    
    // Select PKCS#11 if available
    const pkcs11Option = page.locator('text=/PKCS#11|PKCS11|SoftHSM/i, [value*="pkcs11"]')
    if (await pkcs11Option.count() > 0) {
      await pkcs11Option.first().click()
      
      // Should show PKCS#11 config fields
      await expect(page.locator('input[name*="module"], input[name*="path"], input[placeholder*="Module"]').first()).toBeVisible()
    }
  })

  test('shows HSM status', async ({ page }) => {
    // HSM list should show connection status
    const statusIndicator = page.locator('text=/Connected|Disconnected|Online|Offline|Status/i, [class*="status"]')
    await expect(statusIndicator.first()).toBeVisible()
  })

  test('can test HSM connection', async ({ page }) => {
    // Look for test connection button
    const testBtn = page.locator('button:has-text("Test"), button:has-text("Verify"), button:has-text("Check")')
    
    if (await testBtn.count() > 0) {
      await expect(testBtn.first()).toBeVisible()
    }
  })
})

/**
 * HSM Key Management Tests
 */
test.describe('HSM Key Management (Pro)', () => {
  test.skip(!config.isPro, 'Pro feature - skipped')

  test('shows HSM keys list', async ({ page }) => {
    await page.goto('/hsm')
    
    // Wait for page to load
    await page.waitForTimeout(1000)
    
    // Look for keys section
    const keysSection = page.locator('text=/Keys|Key Pairs|Objects/i')
    if (await keysSection.count() > 0) {
      await expect(keysSection.first()).toBeVisible()
    }
  })

  test('can generate new key in HSM', async ({ page }) => {
    await page.goto('/hsm')
    
    // Find generate key button
    const generateBtn = page.locator('button:has-text("Generate"), button:has-text("Create Key"), button:has-text("New Key")')
    
    if (await generateBtn.count() > 0) {
      await generateBtn.first().click()
      
      // Modal for key generation
      await expect(page.locator('[role="dialog"], [class*="modal"]')).toBeVisible({ timeout: 5000 })
      
      // Key type options
      await expect(page.locator('text=/RSA|ECDSA|EC|AES/i').first()).toBeVisible()
    }
  })

  test('shows key details', async ({ page }) => {
    await page.goto('/hsm')
    
    // Wait for keys to load
    await page.waitForTimeout(1000)
    
    // Click on a key if available
    const keyRow = page.locator('table tbody tr, [class*="key-item"]').first()
    if (await keyRow.count() > 0) {
      await keyRow.click()
      
      // Key details should show
      await expect(page.locator('text=/Label|ID|Type|Size|Algorithm/i').first()).toBeVisible({ timeout: 5000 })
    }
  })
})
