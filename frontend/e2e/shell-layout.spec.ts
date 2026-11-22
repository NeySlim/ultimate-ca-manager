import { test, expect, createCA, issueCert, createUser } from './support/fixtures'

const EPS = 0.5
type Box = { x: number; y: number; width: number; height: number }
const box = async (locator): Promise<Box> => {
  const b = await locator.boundingBox()
  expect(b).not.toBeNull()
  return b as Box
}
const apart = (a: Box, b: Box) =>
  a.x + a.width <= b.x + EPS || b.x + b.width <= a.x + EPS || a.y + a.height <= b.y + EPS || b.y + b.height <= a.y + EPS

test('the status bar keeps the bottom of the window under the open dock', async ({ api, signIn }) => {
  const cert = await issueCert(api, (await createCA(api)).id)
  // The dock's position is written on an account of this test's own: the shared one is read by specs running beside it
  const user = await createUser(api, 'admin')
  const { page } = await signIn(user.username, user.password)
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

  // The zone's dock goes to the right from 1200 px
  await dock.getByRole('button', { name: 'Dock on the right' }).click()
  await expect(dock.getByRole('button', { name: 'Dock at the bottom' })).toBeVisible()
  await check()
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
      // Measured in one go once the fonts are in, and asked again until the bar holds still: the count and the
      // labels settle as the page loads, and other tests change the count meanwhile
      await page.evaluate(() => document.fonts.ready)
      await expect.poll(() => own.evaluate((a) => {
        const nav = a.parentElement!
        const rect = (e: Element) => { const { x, y, width, height } = e.getBoundingClientRect(); return { x, y, width, height } }
        const badge = a.querySelector('.nav-count')
        if (!badge) return ['no count']
        const b = rect(badge)
        const r = document.createRange()
        r.selectNodeContents([...a.childNodes].find(n => n.nodeType === 3 && n.textContent!.trim())!)
        const near = (o: { x: number, y: number, width: number, height: number }) => !(b.x + b.width <= o.x + 0.5 || o.x + o.width <= b.x + 0.5 || b.y + b.height <= o.y + 0.5 || o.y + o.height <= b.y + 0.5)
        const covered: string[] = []
        if (near(rect(r))) covered.push('label')
        const icon = a.querySelector('svg')
        if (icon && icon.getBoundingClientRect().width && near(rect(icon))) covered.push('icon')
        // A link folded away at this width (a pin another test set) covers nothing
        for (const link of nav.querySelectorAll(':scope > a:not([data-module="certificates"])')) {
          const l = rect(link)
          if (l.width && l.height && getComputedStyle(link).visibility !== 'hidden' && near(l)) covered.push(link.getAttribute('data-module')!)
        }
        return covered
      }), `${path} at ${width}`).toEqual([])
      // The count adds no tab stop and is not clipped by its own pill
      await expect(nav.locator('button.nav-count')).toHaveCount(0)
      expect(await badge.evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true)
    }
  }
})
