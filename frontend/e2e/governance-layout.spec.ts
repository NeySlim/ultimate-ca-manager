import { test, expect, createCA } from './support/fixtures'

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

  test('the schedule dialog keeps the mockup geometry and gives the focus back on Escape', async ({ page, api }) => {
    await page.goto('/reports')
    // The page head sits beside the main area, not inside it
    const open = page.locator('.page-head').getByRole('button', { name: 'Schedule a report' })
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
    await expect(dialog.locator('.notice')).toBeVisible()
    const confirm = dialog.locator('.modal-actions .btn').last()
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

  test('Escape closes the schedule dialog while a toast sits above it', async ({ page, api }) => {
    // The server's events reach the page once its socket has said "connected"
    const socket = page.waitForEvent('websocket', (ws) => ws.url().includes('/socket.io'))
      .then((ws) => ws.waitForEvent('framereceived', { predicate: (f) => String(f.payload).includes('"connected"'), timeout: 30000 }))
    await page.goto('/reports')
    const open = page.locator('.page-head').getByRole('button', { name: 'Schedule a report' })
    await open.click()
    const dialog = page.getByRole('dialog')
    await expect(dialog.getByLabel('Content')).toBeFocused()
    // An event of the server announced while the dialog is open: the toast is the topmost layer
    await socket
    await createCA(api)
    await expect(page.locator('#toast.visible').filter({ hasText: /^CA created: / })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
    await expect(open).toBeFocused()
  })

  test('the close button of a queue dialog fades only in Aurore, as the mockup', async ({ page, api }) => {
    await page.goto('/reports')
    await page.locator('.page-head').getByRole('button', { name: 'Schedule a report' }).click()
    const close = page.getByRole('dialog').locator('.modal-head .icon-btn')
    await expect(close).toBeVisible()
    const family = (name: string) => page.evaluate((n) => document.documentElement.setAttribute('data-theme', n), name)
    await family('atelier')
    expect(await css(close, 'transition-duration')).toBe('0s')
    await family('aurore')
    expect(await css(close, 'transition-property')).toBe('background-color, border-color, box-shadow, transform')
    expect(await css(close, 'transition-duration')).toBe('0.16s, 0.16s, 0.16s, 0.16s')
  })

  test('Clear selection gives the focus to the page title', async ({ page, api }) => {
    const before = await api.get('/reports/schedule')
    await api.put('/reports/schedule', { expiring_certificates: { enabled: true, frequency: 'daily', time: '06:00', recipients: ['pki@example.com'], format: 'csv' } })
    try {
      await page.goto('/reports')
      const group = page.getByRole('main').locator('[data-work-group]').first()
      await group.locator('.work-row input[type=checkbox]').first().check()
      await page.getByRole('button', { name: 'Clear selection' }).click()
      await expect(page.getByRole('heading', { level: 1 })).toBeFocused()
      // The group box is clear or ticked, never mixed
      expect(await group.locator('.work-group-head input').evaluate((e: HTMLInputElement) => e.indeterminate)).toBe(false)
    } finally {
      await api.put('/reports/schedule', { expiring_certificates: before.expiring_certificates })
    }
  })

  test('the figure link of a report is the mockup text link, 13 px on a 24 px line', async ({ page, api }) => {
    await page.goto('/reports')
    const main = page.getByRole('main')
    // The inventory is queued or folded, as other tests leave the schedule
    const folded = main.getByRole('button', { name: /^Not scheduled/ })
    if ((await folded.getAttribute('aria-expanded')) === 'false') await folded.click()
    await main.getByRole('button', { name: 'Certificate Inventory', exact: true }).first().click()
    const link = page.getByRole('link', { name: 'See these certificates' })
    await expect(link).toBeVisible()
    expect(Math.round((await box(link)).height)).toBe(24)
    expect(await css(link, 'font-size')).toBe('13px')
    expect(Math.round((await box(link.locator('svg'))).width)).toBe(17)
  })

  test('an empty approvals queue says so in the mockup panel', async ({ page, api }) => {
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

  test('the reports head keeps its actions on the title line, 40 px, nothing sideways', async ({ page, api }) => {
    await page.goto('/reports')
    const head = page.locator('.page-head')
    const h1 = await box(head.locator('h1'))
    const primary = head.getByRole('button', { name: 'Schedule a report' })
    const p = await box(primary)
    expect(Math.abs(p.y - h1.y)).toBeLessThanOrEqual(1)
    expect(Math.round(p.height)).toBe(40)
    expect(Math.round(390 - (p.x + p.width))).toBe(16)
    // Asked at once: the loading skeleton fits the screen too
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  })

  test('the reports head keeps the mockup one action; the PDF composer is under the queue, 40 px', async ({ page, api }) => {
    await page.goto('/reports')
    const head = page.locator('.page-head')
    await expect(head.getByRole('button', { name: 'Schedule a report' })).toBeVisible()
    await expect(head.getByRole('button', { name: 'Build a PDF…' })).toBeHidden()
    const pdf = page.getByRole('main').locator('.phone-only').getByRole('button', { name: 'Build a PDF…' })
    await expect(pdf).toBeVisible()
    expect(Math.round((await box(pdf)).height)).toBe(40)
  })

  test('discovery: the actions under the list wrap inside the page, nothing sideways', async ({ page, api }) => {
    await page.goto('/discovery')
    const row = page.getByRole('main').locator('.phone-only')
    await expect(row.getByRole('button', { name: 'Quick scan…' })).toBeVisible()
    const content = await box(page.locator('.page-content'))
    for (const b of await row.getByRole('button').all()) {
      const r = await box(b)
      expect(r.x).toBeGreaterThanOrEqual(content.x - 0.5)
      expect(r.x + r.width).toBeLessThanOrEqual(content.x + content.width + 0.5)
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  })

  test('the buttons of a report inspector heading are 40 px, as the mockup dock', async ({ page, api }) => {
    await page.goto('/reports')
    const main = page.getByRole('main')
    const folded = main.getByRole('button', { name: /^Not scheduled/ })
    if ((await folded.getAttribute('aria-expanded')) === 'false') await folded.click()
    await main.getByRole('button', { name: 'Certificate Inventory', exact: true }).first().click()
    const download = page.locator('#inspector .dock-heading .actions').getByRole('button', { name: 'Download' })
    await expect(download).toBeVisible()
    expect(Math.round((await box(download)).height)).toBe(40)
  })
})
