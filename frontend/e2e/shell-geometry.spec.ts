import { test, expect } from './support/fixtures'

// Geometry of the Atelier shell: bars, Modules menu and notification panel, measured in the browser
const EPS = 1
type Box = { x: number; y: number; width: number; height: number }
const box = async (locator): Promise<Box> => {
  const b = await locator.boundingBox()
  expect(b).not.toBeNull()
  return b as Box
}

test('the top bar, its links and the status bar keep the mockup heights', async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1000 })
  await page.goto('/certificates')
  const top = await box(page.locator('.shell-topbar'))
  expect(top.y).toBeLessThanOrEqual(EPS)
  expect(Math.abs(top.height - 62)).toBeLessThanOrEqual(EPS)
  const nav = page.getByRole('navigation', { name: 'Main navigation' })
  // The four main pages, Activity last, as links of the bar's full height
  const links = nav.locator('a.shell-navlink')
  await expect(links.nth(3)).toHaveAttribute('href', '/audit')
  for (const link of await links.all()) {
    const b = await box(link)
    expect(b.y).toBeLessThanOrEqual(EPS)
    expect(Math.abs(b.y + b.height - (top.y + top.height))).toBeLessThanOrEqual(2)
  }
  const status = await box(page.getByRole('contentinfo'))
  expect(Math.abs(status.height - 25)).toBeLessThanOrEqual(EPS)
  expect(Math.abs(status.y + status.height - 1000)).toBeLessThanOrEqual(EPS)
  // The live connection lives in the status bar, not the top bar
  await expect(page.locator('.shell-topbar .shell-ws')).toHaveCount(0)
  await expect(page.locator('.shell-statusbar .shell-ws')).toHaveCount(1)
})

test('the Modules menu opens under its button, inside the window', async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1000 })
  await page.goto('/')
  const button = page.getByRole('button', { name: 'Modules' })
  await button.click()
  const menu = page.getByRole('navigation', { name: 'Product modules' })
  await expect(menu).toBeVisible()
  const b = await box(button)
  const m = await box(menu)
  const top = await box(page.locator('.shell-topbar'))
  expect(Math.abs(m.y - (top.y + top.height))).toBeLessThanOrEqual(2)
  expect(m.x).toBeGreaterThanOrEqual(16 - EPS)
  expect(m.x + m.width).toBeLessThanOrEqual(1600 - 16 + EPS)
  expect(m.x).toBeLessThanOrEqual(b.x + EPS)
  // Every item carries the line that says what its page is for
  const items = menu.locator('a[data-module]')
  expect(await items.count()).toBeGreaterThan(0)
  for (const item of await items.all()) await expect(item.locator('small')).toHaveText(/\S/)
})

for (const width of [1600, 390]) {
  test(`the notification panel holds its place at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/certificates')
    await page.getByRole('button', { name: /^Notifications/ }).click()
    const panel = page.getByRole('complementary', { name: 'Notifications' })
    await expect(panel).toBeVisible()
    const p = await box(panel)
    const top = await box(page.locator('.shell-topbar'))
    expect(Math.abs(p.x + p.width - width)).toBeLessThanOrEqual(EPS)
    expect(Math.abs(p.width - Math.min(420, width))).toBeLessThanOrEqual(EPS)
    if (width > 700) {
      expect(Math.abs(p.y - (top.y + top.height))).toBeLessThanOrEqual(EPS)
      const status = await box(page.getByRole('contentinfo'))
      expect(Math.abs(p.y + p.height - status.y)).toBeLessThanOrEqual(EPS)
    } else {
      // On a phone the panel covers the screen, bars included
      expect(p.y).toBeLessThanOrEqual(EPS)
      expect(Math.abs(p.height - 900)).toBeLessThanOrEqual(EPS)
    }
    await page.keyboard.press('Escape')
    await expect(panel).toBeHidden()
  })
}
