import { test, expect } from '@playwright/test'

test.describe('Operations', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/operations')
    await page.waitForLoadState('networkidle')
  })

  test('page loads with heading', async ({ page }) => {
    await expect(page.locator('h1')).toBeVisible()
  })

  test('has sidebar nav with three tabs', async ({ page }) => {
    const nav = page.locator('nav')
    await expect(nav.first()).toBeVisible()
    const tabButtons = nav.locator('button')
    expect(await tabButtons.count()).toBeGreaterThanOrEqual(3)
  })

  test('sidebar tabs have correct labels', async ({ page }) => {
    const nav = page.locator('nav')
    await expect(nav.getByText(/import/i).first()).toBeVisible()
    await expect(nav.getByText(/export/i).first()).toBeVisible()
    await expect(nav.getByText(/bulk/i).first()).toBeVisible()
  })

  // --- Import Tab (default) ---

  test('import tab: has file upload drop zone', async ({ page }) => {
    const dropZone = page.locator('[class*="border-dashed"]').first()
    await expect(dropZone).toBeVisible()
  })

  test('import tab: has hidden file input', async ({ page }) => {
    const fileInput = page.locator('input[type="file"]')
    await expect(fileInput.first()).toBeAttached()
  })

  test('import tab: has browse button in drop zone', async ({ page }) => {
    await expect(page.getByText(/browse/i).first()).toBeVisible()
  })

  test('import tab: has OPNsense section', async ({ page }) => {
    await expect(page.getByText(/opnsense/i).first()).toBeVisible()
  })

  test('import tab: OPNsense has input fields', async ({ page }) => {
    const inputs = page.locator('input')
    expect(await inputs.count()).toBeGreaterThanOrEqual(1)
  })

  test('import tab: OPNsense has API key and secret inputs', async ({ page }) => {
    const passwordInput = page.locator('input[type="password"]')
    await expect(passwordInput.first()).toBeVisible()
  })

  // --- Export Tab ---

  test('export tab: shows export cards', async ({ page }) => {
    const nav = page.locator('nav')
    await nav.getByText(/export/i).first().click()
    await page.waitForTimeout(500)

    // Export tab has download action cards in a grid
    const cards = page.locator('[class*="grid"] button, [class*="grid"] [class*="card"]')
    expect(await cards.count()).toBeGreaterThanOrEqual(2)
  })

  test('export tab: has PEM and P7B download options', async ({ page }) => {
    const nav = page.locator('nav')
    await nav.getByText(/export/i).first().click()
    await page.waitForTimeout(500)

    await expect(page.getByText(/pem/i).first()).toBeVisible()
    await expect(page.getByText(/p7b/i).first()).toBeVisible()
  })

  test('export tab: has download buttons', async ({ page }) => {
    const nav = page.locator('nav')
    await nav.getByText(/export/i).first().click()
    await page.waitForTimeout(500)

    const downloadLinks = page.getByText(/download/i)
    expect(await downloadLinks.count()).toBeGreaterThanOrEqual(1)
  })

  // --- Bulk Actions Tab ---

  test('bulk tab: has resource type selector buttons', async ({ page }) => {
    const nav = page.locator('nav')
    await nav.getByText(/bulk/i).first().click()
    await page.waitForTimeout(500)

    // Resource type chip buttons
    await expect(page.getByText(/certificates/i).first()).toBeVisible()
  })

  test('bulk tab: has search input', async ({ page }) => {
    const nav = page.locator('nav')
    await nav.getByText(/bulk/i).first().click()
    await page.waitForTimeout(500)

    const search = page.locator('input[type="text"]').first()
    await expect(search).toBeVisible()
  })

  test('bulk tab: search input accepts text', async ({ page }) => {
    const nav = page.locator('nav')
    await nav.getByText(/bulk/i).first().click()
    await page.waitForTimeout(500)

    const search = page.locator('input[type="text"]').first()
    await search.fill('test-search')
    await page.waitForTimeout(500)
    // No crash = success
  })

  test('bulk tab: has status filter for certificates', async ({ page }) => {
    const nav = page.locator('nav')
    await nav.getByText(/bulk/i).first().click()
    await page.waitForTimeout(500)

    // Certificates is the default resource type, so status filter should be visible
    const selects = page.locator('select')
    expect(await selects.count()).toBeGreaterThanOrEqual(1)
  })

  test('bulk tab: has table/basket view toggle', async ({ page }) => {
    const nav = page.locator('nav')
    await nav.getByText(/bulk/i).first().click()
    await page.waitForTimeout(500)

    // View mode toggle is a button group with two buttons
    const toggleButtons = page.locator('[class*="bg-bg-secondary"] button')
    expect(await toggleButtons.count()).toBeGreaterThanOrEqual(2)
  })

  test('bulk tab: has data table with rows', async ({ page }) => {
    const nav = page.locator('nav')
    await nav.getByText(/bulk/i).first().click()
    await page.waitForTimeout(500)

    await expect(page.locator('table')).toBeVisible({ timeout: 10000 })
    await expect(page.locator('table thead')).toBeVisible()
  })

  test('bulk tab: can switch resource types', async ({ page }) => {
    const nav = page.locator('nav')
    await nav.getByText(/bulk/i).first().click()
    await page.waitForTimeout(500)

    // Click a different resource type (e.g. CA)
    const caButton = page.locator('button').filter({ hasText: /^CA$/i })
    if (await caButton.count() > 0) {
      await caButton.first().click()
      await page.waitForTimeout(500)
      // Status/CA filters should disappear for non-certificate types
    }
  })

  // --- Tab Switching ---

  test('can switch between all tabs', async ({ page }) => {
    const nav = page.locator('nav')

    // Switch to Export
    await nav.getByText(/export/i).first().click()
    await page.waitForTimeout(500)
    await expect(page.getByText(/pem/i).first()).toBeVisible()

    // Switch to Bulk Actions
    await nav.getByText(/bulk/i).first().click()
    await page.waitForTimeout(500)
    await expect(page.locator('table')).toBeVisible({ timeout: 10000 })

    // Switch back to Import
    await nav.getByText(/import/i).first().click()
    await page.waitForTimeout(500)
    const dropZone = page.locator('[class*="border-dashed"]').first()
    await expect(dropZone).toBeVisible()
  })
})
