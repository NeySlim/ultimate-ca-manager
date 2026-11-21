import { test, expect, createCA } from './support/fixtures'

// CSRs, Templates, Trust Store and User Certificates as the mockup's module list: geometry jsdom cannot measure
type Box = { x: number; y: number; width: number; height: number }
const box = async (locator): Promise<Box> => {
  const b = await locator.boundingBox()
  expect(b).not.toBeNull()
  return b as Box
}
const css = (locator, prop: string) => locator.evaluate((el, p) => getComputedStyle(el).getPropertyValue(p), prop)
const PAGES = ['/csrs', '/templates', '/truststore', '/user-certificates']

test.describe('desktop', () => {
  test.use({ viewport: { width: 1600, height: 1000 } })

  for (const path of PAGES) {
    test(`${path} draws the module list of the mockup`, async ({ page, api }) => {
      await page.goto(path)
      const zone = page.locator('.atl')
      const title = zone.locator('h1#main-title')
      await expect(title).toBeVisible()
      expect(await css(title, 'font-size')).toBe('25px')
      // The state chips, 38 px high, then the table frame with its 5 px radius and 34 px headers
      const chip = zone.locator('.views .view-btn').first()
      expect(Math.round((await box(chip)).height)).toBe(38)
      const frame = zone.locator('.table-container')
      expect(await css(frame, 'border-top-left-radius')).toBe('5px')
      const th = zone.locator('thead th').first()
      expect(Math.round((await box(th)).height)).toBe(34)
      // The page content sits 24 px from the edge of the stage
      const stage = await box(zone.locator('main.stage'))
      expect(Math.round((await box(zone.locator('.page-head'))).x - stage.x)).toBe(24)
    })
  }

  test('a trust anchor opens in the dock under the list, and Escape gives the focus back to its name', async ({ page, api }) => {
    await createCA(api)
    await page.goto('/truststore')
    const zone = page.locator('.atl')
    const name = zone.locator('tbody .entity-name').first()
    await expect(name).toBeVisible()
    await name.click()
    const dock = zone.locator('#inspector')
    await expect(dock).toBeVisible()
    // The dock sits under the table, the full width of the page content
    const list = await box(zone.locator('.table-container'))
    const frame = await box(dock)
    expect(frame.y).toBeGreaterThan(list.y + list.height - 1)
    expect(Math.round(frame.width)).toBe(Math.round(list.width))
    await expect(dock.getByRole('tab')).toHaveText(['Overview', 'Details', 'PEM'])
    await page.keyboard.press('Escape')
    await expect(dock).toBeHidden()
    await expect(name).toBeFocused()
  })
})

test.describe('phone', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  for (const path of PAGES) {
    test(`${path} lists cards with their chevron on screen`, async ({ page, api }) => {
      await page.goto(path)
      const zone = page.locator('.atl')
      await expect(zone.locator('h1#main-title')).toBeVisible()
      // No table that scrolls sideways: the page keeps the width of the screen
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
      const cards = zone.locator('.mobile-list .mobile-record:not(.sk-record)')
      if (await cards.count()) {
        const chevron = cards.first().locator('.row-top > .icon-btn')
        const b = await box(chevron)
        expect(b.x + b.width).toBeLessThanOrEqual(390)
        expect(Math.round(b.height)).toBeGreaterThanOrEqual(44)
      }
    })
  }
})
