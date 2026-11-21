import { test, expect } from './support/fixtures'

// Real geometry of the work queue template (Reports page) at 1600 px, after the Atelier mockup
const W = 1600
const H = 1000
const GUTTER = 24
type Box = { x: number; y: number; width: number; height: number }
const box = async (locator): Promise<Box> => {
  const b = await locator.boundingBox()
  expect(b).not.toBeNull()
  return b as Box
}
const css = (locator, prop: string) => locator.evaluate((el, p) => getComputedStyle(el).getPropertyValue(p), prop)

test.use({ viewport: { width: W, height: H } })

test('the queue groups, rows, due dates and history keep the mockup geometry', async ({ page, api }) => {
  // A daily report runs within 24 h: the first group holds it
  const before = await api.get('/reports/schedule')
  await api.put('/reports/schedule', { expiring_certificates: { enabled: true, frequency: 'daily', time: '06:00', recipients: ['pki@example.com'], format: 'csv' } })
  try {
    await page.goto('/reports')
    const main = page.getByRole('main')
    const group = main.locator('[data-work-group="today"]')
    await expect(group).toBeVisible()

    // Panels at the page margins, 16 px apart
    const g = await box(group)
    expect(Math.abs(g.x - GUTTER)).toBeLessThanOrEqual(1)
    expect(Math.abs(W - (g.x + g.width) - GUTTER)).toBeLessThanOrEqual(1)
    expect(await css(group, 'border-radius')).toBe('5px')

    // Group head: 8 px 18 px 8 px 12 px, a 14 px semibold heading
    const head = group.locator('.work-group-head')
    expect(await css(head, 'padding')).toBe('8px 18px 8px 12px')
    const h2 = head.locator('h2')
    expect(await css(h2, 'font-size')).toBe('14px')
    expect(await css(h2, 'font-weight')).toBe('600')

    // Row: 28 px check, flexible main, 170 px due date, actions; two text levels
    const row = group.locator('[data-work-row]').first()
    const cols = (await css(row, 'grid-template-columns')).split(' ')
    expect(cols[0]).toBe('28px')
    expect(cols[2]).toBe('170px')
    expect(await css(row, 'padding')).toBe('8px 18px 8px 12px')
    expect(await css(row.locator('.work-subject'), 'font-size')).toBe('13px')
    expect(await css(row.locator('.queue-kind'), 'border-radius')).toBe('999px')
    expect(await css(row.locator('.work-detail'), 'font-size')).toBe('12px')
    const due = row.locator('.queue-due strong')
    expect(await css(due, 'font-size')).toBe('13px')
    await expect(due).toHaveText(/\d+ h$/)
    const r = await box(row)
    const a = await box(row.locator('.work-action'))
    expect(Math.abs(r.x + r.width - 18 - (a.x + a.width))).toBeLessThanOrEqual(1)

    // History toggle: a 44 px folded band
    const toggle = main.locator('[data-work-history]')
    await expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(Math.round((await box(toggle)).height)).toBeGreaterThanOrEqual(44)

    // Nothing pushes the page sideways
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)

    // A name opens the report in the module dock, with its Report and Runs sections
    await row.locator('.work-subject').click()
    const dock = page.locator('#inspector')
    await expect(dock.getByRole('tab', { name: 'Report', exact: true })).toBeVisible()
    await expect(dock.getByRole('tab', { name: 'Runs' })).toBeVisible()
    await expect(row).toHaveClass(/opened/)
  } finally {
    await api.put('/reports/schedule', { expiring_certificates: before.expiring_certificates })
  }
})
