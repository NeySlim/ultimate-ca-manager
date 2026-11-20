import { test, expect } from './support/fixtures'

// Real geometry of the Activity page, as the Atelier mockup draws it (its style.css, copied): jsdom measures nothing
const W = 1600
const H = 1000
type Box = { x: number; y: number; width: number; height: number }
const box = async (locator): Promise<Box> => {
  const b = await locator.boundingBox()
  expect(b).not.toBeNull()
  return b as Box
}
const css = (locator, prop: string) => locator.evaluate((el, p) => getComputedStyle(el).getPropertyValue(p), prop)

test.describe('desktop', () => {
  test.use({ viewport: { width: W, height: H } })

  test('the journal keeps the mockup\'s head, toolbar, rows and detail', async ({ page, api }) => {
    expect(api).toBeTruthy()
    await page.goto('/audit')
    const main = page.getByRole('main')
    const rows = main.locator('.audit-table tbody tr:not(.sk-row)')
    await expect(rows.first()).toBeVisible()

    // Head: 24 px gutter, 22 px above the title, a 25 px title
    const head = await box(main.locator('.page-head'))
    expect(Math.round(head.x)).toBe(24)
    expect(await css(main.locator('h1'), 'font-size')).toBe('25px')
    expect(await css(main.locator('.page-head'), 'padding-top')).toBe('22px')

    // Toolbar: the search takes the room left, 12 px under it the summary
    const search = await box(main.locator('.toolbar .search'))
    expect(search.height).toBeGreaterThanOrEqual(34)
    expect(await css(main.locator('.audit-summary'), 'font-size')).toBe('12px')

    // Table: 34 px header, 45 px rows, all of one height, framed with a 5 px radius
    expect(Math.round((await box(main.locator('.audit-table thead th').first())).height)).toBe(34)
    const heights = await rows.evaluateAll(list => list.map(r => Math.round(r.getBoundingClientRect().height)))
    expect(new Set(heights)).toEqual(new Set([45]))
    expect(await css(main.locator('.audit-container'), 'border-top-left-radius')).toBe('5px')

    // Detail: the mockup's narrow dialog (520 px), its title the operation, focus back on the opener on Escape
    const opener = main.locator('.audit-table .resource').first()
    await opener.click()
    const dialog = page.locator('dialog[open]')
    await expect(dialog).toBeVisible()
    expect(Math.round((await box(dialog)).width)).toBe(520)
    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)
    await expect(opener).toBeFocused()
  })
})

test.describe('phone', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('the journal scrolls sideways in its frame and hides the head\'s export', async ({ page, api }) => {
    expect(api).toBeTruthy()
    await page.goto('/audit')
    const main = page.getByRole('main')
    await expect(main.locator('.audit-table tbody tr:not(.sk-row)').first()).toBeVisible()
    expect(Math.round((await box(main.locator('.audit-table'))).width)).toBeGreaterThanOrEqual(750)
    const scroller = main.locator('#audit-scroll')
    expect(await scroller.evaluate(el => el.scrollWidth > el.clientWidth)).toBe(true)
    await expect(main.getByRole('button', { name: /Export the log|Exporter le journal/ })).toBeHidden()
    // the export stays reachable from the « ⋯ » menu
    await main.locator('[data-action=journal-menu]').click()
    await expect(page.locator('dialog[open]').getByRole('button', { name: /Export the log|Exporter le journal/ })).toBeVisible()
  })
})
