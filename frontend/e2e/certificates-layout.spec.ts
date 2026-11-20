import { test, expect, createCA, issueCert } from './support/fixtures'

// Real geometry of the certificates page at 1600 px: jsdom measures nothing
const EPS = 1
const W = 1600
const H = 1000
const GUTTER = 24
type Box = { x: number; y: number; width: number; height: number }
const box = async (locator): Promise<Box> => {
  const b = await locator.boundingBox()
  expect(b).not.toBeNull()
  return b as Box
}

test.use({ viewport: { width: W, height: H } })

test('the list shows its seven columns whole and the inspector opens in the page flow', async ({ page, api }) => {
  const cert = await issueCert(api, (await createCA(api)).id)
  await page.goto('/certificates')
  const main = page.getByRole('main')
  await expect(main.getByRole('button', { name: cert.common_name, exact: true })).toBeVisible()

  // Seven data columns, none cut and none pushing the table sideways
  const headers = main.locator('thead th').filter({ hasNotText: /^$/ }).filter({ hasNotText: 'Actions' })
  await expect(headers).toHaveCount(7)
  for (const th of await headers.all()) {
    await expect(th).toBeVisible()
    // The words of the header inside its box (the resize grip straddles the border on purpose)
    const inside = await th.evaluate((el) => {
      const cell = el.getBoundingClientRect()
      const walk = document.createTreeWalker(el, NodeFilter.SHOW_TEXT)
      const range = document.createRange()
      let ok = true
      for (let n = walk.nextNode(); n; n = walk.nextNode()) {
        range.selectNodeContents(n)
        const r = range.getBoundingClientRect()
        if (r.width && (r.left < cell.left - 1 || r.right > cell.right + 1)) ok = false
      }
      const sort = el.querySelector('.lv-sort')
      return ok && (!sort || sort.scrollWidth <= sort.clientWidth + 1)
    })
    expect(inside, await th.textContent()).toBe(true)
  }
  const scroller = main.locator('.lv-scroll')
  expect(await scroller.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true)

  // One line per row: every row has the same height
  const heights = await main.locator('tbody tr').evaluateAll(rows => rows.map(r => Math.round(r.getBoundingClientRect().height)))
  expect(heights.length).toBeGreaterThan(0)
  expect(new Set(heights).size).toBe(1)

  // Opened: the inspector follows the list inside the page margins, above the status bar
  await main.getByRole('button', { name: cert.common_name, exact: true }).click()
  const dock = page.getByTestId('inspector-dock')
  await expect(dock).toBeVisible()
  await expect(dock.getByRole('heading', { name: cert.common_name })).toBeVisible()
  const d = await box(dock)
  const bar = await box(page.getByRole('contentinfo'))
  const list = await box(main)
  expect(Math.abs(d.x - GUTTER)).toBeLessThanOrEqual(EPS)
  expect(Math.abs(W - (d.x + d.width) - GUTTER)).toBeLessThanOrEqual(EPS)
  expect(Math.abs(bar.y + bar.height - H)).toBeLessThanOrEqual(EPS)
  expect(Math.abs(d.y + d.height - bar.y)).toBeLessThanOrEqual(EPS)
  expect(list.y + list.height).toBeLessThanOrEqual(d.y + EPS)
  expect(await dock.evaluate(el => getComputedStyle(el).position)).not.toBe('fixed')
  // The row of the open certificate is marked
  await expect(main.getByRole('row', { name: new RegExp(cert.common_name.replace(/\./g, '\\.')) })).toHaveClass(/is-opened/)

  // Folded to its tab strip, it gives the room back to the list
  await dock.getByRole('button', { name: 'Fold the inspector' }).click()
  const folded = await box(dock)
  expect(folded.height).toBeLessThan(48)
  expect((await box(main)).height).toBeGreaterThan(list.height)
  await dock.getByRole('button', { name: 'Unfold the inspector' }).click()
})
