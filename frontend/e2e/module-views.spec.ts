import { test, expect } from './support/fixtures'

// The views of a protocol page are tabs under its head, those past the room in a « More » menu at the
// end of the row (never a scroll); the settings table of contents scrolls on its own when taller than the page
const EPS = 1
type Box = { x: number; y: number; width: number; height: number }
const box = async (locator): Promise<Box> => {
  const b = await locator.boundingBox()
  expect(b).not.toBeNull()
  return b as Box
}
// The element a click at the centre of the locator would reach is the locator itself (nothing covers it)
const reachable = (locator) => locator.evaluate((el) => {
  const r = el.getBoundingClientRect()
  const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)
  return !!hit && (hit === el || el.contains(hit))
})

test.describe('the views of a protocol page', () => {
  test.use({ viewport: { width: 1600, height: 1000 } })

  test('ACME: a view is reached by its tab and kept in the address; the arrows go on', async ({ page, api }) => {
    await page.goto('/acme')
    const tabs = page.getByRole('tablist', { name: 'View' })
    const dns = tabs.getByRole('tab', { name: /^DNS providers/ })
    await dns.click()
    await expect(page).toHaveURL(/\/acme\?tab=dns$/)
    await expect(dns).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByRole('tabpanel')).toHaveAttribute('aria-labelledby', 'acme-view-tab-dns')
    await expect(page.getByRole('button', { name: 'Add Provider' }).first()).toBeVisible()
    await dns.press('ArrowRight')
    await expect(page).toHaveURL(/\/acme\?tab=domains$/)
    await expect(tabs.getByRole('tab', { name: /^Client domains/ })).toBeFocused()
    // At 1600 px every tab of the eleven shows: no « More »
    await expect(tabs.getByRole('tab')).toHaveCount(11)
    await expect(page.getByRole('button', { name: 'More', exact: true })).toHaveCount(0)
  })

  test('SCEP: a view is reached by its tab and kept in the address', async ({ page, api }) => {
    await page.goto('/scep-config')
    const requests = page.getByRole('tablist', { name: 'View' }).getByRole('tab', { name: /^Requests/ })
    await requests.click()
    await expect(page).toHaveURL(/\/scep-config\?tab=requests$/)
    await expect(requests).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByRole('tabpanel').locator('.table-workspace')).toBeVisible()
  })
})

for (const [width, height] of [[1000, 800], [390, 844]]) {
  test.describe(`${width} px`, () => {
    test.use({ viewport: { width, height } })

    test('the ACME views past the room go into « More », the row never scrolls, the shown one stays in it', async ({ page, api }) => {
      await page.goto('/acme')
      const tabs = page.getByRole('tablist', { name: 'View' })
      const t = await box(page.locator('.page-views'))
      const head = await box(page.locator('.page-head'))
      expect(t.x).toBeGreaterThanOrEqual(head.x - EPS)
      expect(t.x + t.width).toBeLessThanOrEqual(head.x + head.width + EPS)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
      expect(await tabs.evaluate((el) => el.scrollWidth <= el.clientWidth + 1)).toBe(true)
      const shown = await tabs.getByRole('tab').count()
      expect(shown).toBeLessThan(11)
      const more = page.getByRole('button', { name: 'More', exact: true })
      const m = await box(more)
      expect(m.x + m.width).toBeLessThanOrEqual(t.x + t.width + EPS)
      expect(await reachable(more)).toBe(true)
      // The menu holds the others, counters with them; the last view taken from it comes into the row
      await more.click()
      const menu = page.getByRole('menu', { name: 'Other views' })
      await expect(menu.getByRole('menuitem')).toHaveCount(11 - shown)
      await expect(menu.getByRole('menuitem', { name: /^Issued certificates/ }).locator('.counter')).toBeVisible()
      await menu.getByRole('menuitem', { name: /^Issued certificates/ }).click()
      await expect(page).toHaveURL(/\/acme\?tab=history/)
      const last = tabs.getByRole('tab', { name: /^Issued certificates/ })
      await expect(last).toHaveAttribute('aria-selected', 'true')
      await expect(last).toBeFocused()
      expect(await reachable(last)).toBe(true)
      // From the keyboard the arrows walk every view, the menu ones included
      await last.press('ArrowRight')
      // The first view is the page's own address
      await expect(page).toHaveURL(/\/acme$/)
      await expect(tabs.getByRole('tab', { name: /^Accounts/ })).toBeFocused()
    })
  })
}

for (const [width, height] of [[1000, 700], [1600, 800]]) {
  test.describe(`settings at ${width} × ${height}`, () => {
    test.use({ viewport: { width, height } })

    test('the table of contents scrolls on its own: its last entry shows and opens its section', async ({ page, api }) => {
      await page.goto('/settings')
      const nav = page.getByRole('navigation', { name: 'Settings sections', exact: true })
      await expect(nav).toBeVisible()
      const view = await box(page.locator('#view-scroll'))
      // Never taller than the scroll area it sticks in
      const n = await box(nav)
      expect(n.y + n.height).toBeLessThanOrEqual(view.y + view.height + EPS)
      expect(await nav.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true)
      // The wheel over the contents scrolls them, not the page
      await nav.hover()
      await page.mouse.wheel(0, 3000)
      const last = nav.getByRole('link').last()
      await expect.poll(async () => {
        const l = await box(last)
        return l.y >= n.y - EPS && l.y + l.height <= n.y + n.height + EPS
      }).toBe(true)
      expect(await reachable(last)).toBe(true)
      const target = await last.getAttribute('data-jump')
      await last.click()
      await expect(page).toHaveURL(new RegExp(`[?&]tab=${target}`))
      await expect(page.locator(`#set-title-${target}`)).toBeFocused()
      // The entry shown is still in view inside the contents
      const l = await box(last)
      const after = await box(nav)
      expect(l.y + l.height).toBeLessThanOrEqual(after.y + after.height + EPS)
    })

    test('a link to the last section shows its entry in the contents', async ({ page, api }) => {
      await page.goto('/settings')
      const nav = page.getByRole('navigation', { name: 'Settings sections', exact: true })
      const target = await nav.getByRole('link').last().getAttribute('data-jump')
      await page.goto(`/settings?tab=${target}`)
      const current = nav.locator('a[aria-current="true"]')
      await expect(current).toHaveAttribute('data-jump', target as string)
      // Inside the contents and inside the scroll area the page shows
      const view = await box(page.locator('#view-scroll'))
      await expect.poll(async () => {
        const c = await box(current)
        const n = await box(nav)
        return c.y >= Math.max(n.y, view.y) - EPS && c.y + c.height <= Math.min(n.y + n.height, view.y + view.height) + EPS
      }).toBe(true)
      expect(await reachable(current)).toBe(true)
    })
  })
}
