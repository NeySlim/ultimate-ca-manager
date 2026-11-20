import { test, expect } from './support/fixtures'

// Approvals, Reports and Key recovery against the Atelier mockup: head, dialogs, focus, phone head
type Box = { x: number; y: number; width: number; height: number }
const box = async (locator): Promise<Box> => {
  const b = await locator.boundingBox()
  expect(b).not.toBeNull()
  return b as Box
}
const css = (locator, prop: string) => locator.evaluate((el, p) => getComputedStyle(el).getPropertyValue(p), prop)

test.describe('desktop', () => {
  test.use({ viewport: { width: 1600, height: 1000 } })

  test('the schedule dialog keeps the mockup geometry and gives the focus back on Escape', async ({ page }) => {
    await page.goto('/reports')
    const open = page.getByRole('main').getByRole('button', { name: 'Schedule a report' }).first()
    await open.focus()
    await open.click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    // 520 px wide, 36 px fields, Content first and focused
    expect(Math.round((await box(dialog)).width)).toBe(520)
    const content = dialog.getByLabel('Content')
    await expect(content).toBeFocused()
    expect(Math.round((await box(content)).height)).toBe(36)
    expect(await css(content, 'font-size')).toBe('12px')
    // The notice of the mockup above the buttons, 36 px buttons
    await expect(dialog.locator('.wk-notice')).toBeVisible()
    const confirm = dialog.locator('.lv-dialog-actions .wk-btn').last()
    expect(Math.round((await box(confirm)).height)).toBe(36)
    // A wrong time is said under its field, which takes the focus
    await dialog.getByLabel(/^Sending time/).fill('25:00')
    await confirm.click()
    await expect(dialog.getByText('Invalid time: HH:MM format, from 00:00 to 23:59.')).toBeVisible()
    await expect(dialog.getByLabel(/^Sending time/)).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
    await expect(open).toBeFocused()
  })

  test('Clear selection gives the focus to the page title', async ({ page, api }) => {
    const before = await api.get('/reports/schedule')
    await api.put('/reports/schedule', { expiring_certificates: { enabled: true, frequency: 'daily', time: '06:00', recipients: ['pki@example.com'], format: 'csv' } })
    try {
      await page.goto('/reports')
      const group = page.getByRole('main').locator('[data-work-group]').first()
      await group.locator('.wk-row input[type=checkbox]').first().check()
      await page.getByRole('button', { name: 'Clear selection' }).click()
      await expect(page.getByRole('heading', { level: 1 })).toBeFocused()
      // The group box is clear or ticked, never mixed
      expect(await group.locator('.wk-group-head input').evaluate((e: HTMLInputElement) => e.indeterminate)).toBe(false)
    } finally {
      await api.put('/reports/schedule', { expiring_certificates: before.expiring_certificates })
    }
  })

  test('an empty approvals queue says so in the mockup panel', async ({ page }) => {
    await page.goto('/approvals')
    const main = page.getByRole('main')
    const empty = main.getByTestId('work-empty')
    // A fresh instance holds no pending request; skip when the bench left some
    test.skip(!(await empty.isVisible()), 'pending requests on this instance')
    const icon = empty.locator(':scope > svg')
    expect(Math.round((await box(icon)).width)).toBe(28)
    expect(await css(empty.locator('h3'), 'font-weight')).toBe('600')
  })
})

test.describe('phone', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('the reports head keeps its actions on the title line, 40 px, nothing sideways', async ({ page }) => {
    await page.goto('/reports')
    const head = page.locator('.lv-head')
    const h1 = await box(head.locator('h1'))
    const primary = head.getByRole('button', { name: 'Schedule a report' })
    const p = await box(primary)
    expect(Math.abs(p.y - h1.y)).toBeLessThanOrEqual(1)
    expect(Math.round(p.height)).toBe(40)
    expect(Math.round(390 - (p.x + p.width))).toBe(16)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  })
})
