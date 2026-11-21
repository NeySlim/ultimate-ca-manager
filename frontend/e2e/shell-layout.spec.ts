import { test, expect, createCA, issueCert } from './support/fixtures'

const EPS = 0.5
type Box = { x: number; y: number; width: number; height: number }
const box = async (locator): Promise<Box> => {
  const b = await locator.boundingBox()
  expect(b).not.toBeNull()
  return b as Box
}
const apart = (a: Box, b: Box) =>
  a.x + a.width <= b.x + EPS || b.x + b.width <= a.x + EPS || a.y + a.height <= b.y + EPS || b.y + b.height <= a.y + EPS

test('the status bar keeps the bottom of the window under the open dock', async ({ page, api }) => {
  const cert = await issueCert(api, (await createCA(api)).id)
  await page.goto('/certificates')
  await page.getByRole('main').getByRole('searchbox').fill(cert.common_name)
  await page.getByRole('main').getByRole('button', { name: cert.common_name, exact: true }).click()
  const dock = page.locator('#inspector')
  await expect(dock).toBeVisible()
  const view = page.viewportSize()!
  const bar = page.getByRole('contentinfo')
  await expect(bar).toHaveCount(1)
  // The bar of the 2.x window manager is gone, and the dock leaves close-on-navigate to the account preferences
  await expect(page.getByText('Close on navigate')).toHaveCount(0)
  await expect(dock.getByRole('button', { name: 'Close on navigate' })).toHaveCount(0)

  const check = async () => {
    const b = await box(bar)
    const d = await box(dock)
    const main = await box(page.getByRole('main'))
    expect(Math.abs(b.y + b.height - view.height)).toBeLessThanOrEqual(EPS)
    expect(Math.abs(b.width - view.width)).toBeLessThanOrEqual(EPS)
    expect(d.y + d.height).toBeLessThanOrEqual(b.y + EPS)
    // The dock sits in the page as in the Atelier; the list ends where it starts, so its last row scrolls into view
    expect(apart(await box(page.getByRole('main').locator('.table-container')), d)).toBe(true)
    expect(d.y + d.height).toBeLessThanOrEqual(main.y + main.height + EPS)
    expect(main.y + main.height).toBeLessThanOrEqual(b.y + EPS)
  }
  await check()

  // The position is a preference of the account: put it back
  const toRight = dock.getByRole('button', { name: 'Dock on the right' })
  if (await toRight.count()) {
    await toRight.click()
    try {
      await expect(dock.getByRole('button', { name: 'Dock at the bottom' })).toBeVisible()
      await check()
    } finally {
      await dock.getByRole('button', { name: 'Dock at the bottom' }).click()
    }
  }
})

test('the expiry count sits on its own link: no other link covered, the link keeps its width', async ({ page, api }) => {
  await issueCert(api, (await createCA(api)).id, { validity_days: 3 })
  for (const width of [1440, 1280, 1100, 900]) {
    await page.setViewportSize({ width, height: 900 })
    for (const path of ['/certificates', '/cas']) {
      await page.goto(path)
      const nav = page.getByRole('navigation', { name: 'Main navigation' })
      const badge = nav.locator('.nav-count')
      await expect(badge).toBeVisible()
      const own = nav.locator(':scope > a[data-module="certificates"]')
      await expect(own).toContainText(/certificates? expir/)
      const b = await box(badge)
      // It covers neither the icon of its own link nor its label
      // The label is the link's bare text, as the mockup's: measured as a range
      const label = await own.evaluate((a) => {
        const r = document.createRange()
        const text = [...a.childNodes].find(n => n.nodeType === 3 && n.textContent.trim())
        r.selectNodeContents(text)
        const { x, y, width, height } = r.getBoundingClientRect()
        return { x, y, width, height }
      })
      expect(apart(b, label), `${path} at ${width}: label`).toBe(true)
      const icon = own.locator('svg')
      if (await icon.isVisible()) expect(apart(b, await box(icon)), `${path} at ${width}: icon`).toBe(true)
      // A link folded away at this width (a pin another test set) covers nothing
      for (const link of await nav.locator(':scope > a:not([data-module="certificates"]):visible').all()) {
        expect(apart(b, await box(link)), `${path} at ${width}: ${await link.getAttribute('data-module')}`).toBe(true)
      }
      // The count adds no tab stop and is not clipped by its own pill
      await expect(nav.locator('button.nav-count')).toHaveCount(0)
      expect(await badge.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true)
    }
  }
})
