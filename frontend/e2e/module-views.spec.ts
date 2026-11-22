import { test, expect } from './support/fixtures'

// The views of a protocol page are tabs under its head, the row scrolling on its own when narrower
// than its tabs
const EPS = 1
type Box = { x: number; y: number; width: number; height: number }
const box = async (locator): Promise<Box> => {
  const b = await locator.boundingBox()
  expect(b).not.toBeNull()
  return b as Box
}

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
    // At 1600 px every tab of the eleven shows: the row does not scroll
    expect(await tabs.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
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

    test('the row of ACME views keeps to the page and its last tab is reached', async ({ page, api }) => {
      await page.goto('/acme')
      const tabs = page.getByRole('tablist', { name: 'View' })
      const t = await box(tabs)
      const head = await box(page.locator('.page-head'))
      expect(t.x).toBeGreaterThanOrEqual(head.x - EPS)
      expect(t.x + t.width).toBeLessThanOrEqual(head.x + head.width + EPS)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
      // The row overflows: a shadow marks the hidden end
      expect(await tabs.evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true)
      await expect(page.locator('.page-views')).toHaveAttribute('data-more-end', '')
      const last = tabs.getByRole('tab', { name: /^Issued certificates/ })
      await last.focus()
      await expect(page).toHaveURL(/\/acme$/)
      await last.press('Enter')
      await expect(page).toHaveURL(/\/acme\?tab=history$/)
      // The shown tab is brought into the row, clear of its edge
      await expect.poll(async () => {
        const l = await box(last)
        return l.x + l.width <= t.x + t.width + EPS && l.x >= t.x - EPS
      }).toBe(true)
      await expect(page.locator('.page-views')).toHaveAttribute('data-more-start', '')
    })
  })
}
