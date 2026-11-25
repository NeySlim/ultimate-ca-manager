import { test, expect } from './support/fixtures'

// The floating save bar sits flush on the bottom of the scroll area: no field shows in a band under it (#455)
const EPS = 1
const gap = (page) => page.evaluate(() => {
  const view = document.querySelector('#view-scroll') as HTMLElement
  const bar = document.querySelector('#settings-savebar') as HTMLElement
  const v = view.getBoundingClientRect()
  const b = bar.getBoundingClientRect()
  return { gap: v.bottom - b.bottom, scrolls: view.scrollHeight > view.clientHeight, vh: window.innerHeight, barBottom: b.bottom }
})
const middle = (page) => page.evaluate(() => {
  const view = document.querySelector('#view-scroll') as HTMLElement
  view.scrollTop = (view.scrollHeight - view.clientHeight) / 3
})
const end = (page) => page.evaluate(() => {
  const view = document.querySelector('#view-scroll') as HTMLElement
  view.scrollTop = view.scrollHeight
})

const PAGES = [
  { path: '/settings', field: 'Syslog hostname' },
  { path: '/account', field: 'Full Name' },
]

test.describe('wide screen', () => {
  test.use({ viewport: { width: 1912, height: 867 } })
  for (const { path, field } of PAGES) {
    test(`${path}: the bar is flush with the bottom of the scroll area, clean and dirty`, async ({ page, api }) => {
      await page.goto(path)
      await expect(page.locator('#settings-savebar')).toBeVisible()
      await middle(page)
      let m = await gap(page)
      expect(m.scrolls).toBe(true)
      expect(Math.abs(m.gap)).toBeLessThanOrEqual(EPS)
      await page.getByLabel(field, { exact: true }).first().fill(`e2e-${Date.now()}`)
      await middle(page)
      m = await gap(page)
      expect(Math.abs(m.gap)).toBeLessThanOrEqual(EPS)
    })

    test(`${path}: at the end of the page the bar does not cover the last block`, async ({ page, api }) => {
      await page.goto(path)
      await expect(page.locator('#settings-savebar')).toBeVisible()
      const measure = async () => {
        await end(page)
        return page.evaluate(() => {
          const bar = document.querySelector('#settings-savebar') as HTMLElement
          const prev = bar.previousElementSibling as HTMLElement
          const b = bar.getBoundingClientRect()
          const p = prev.getBoundingClientRect()
          return { overlap: p.bottom - b.top, barBottom: b.bottom, viewBottom: document.querySelector('#view-scroll')!.getBoundingClientRect().bottom }
        })
      }
      // the sections render after the data arrives: measure once the page has settled at its end
      await expect.poll(async () => (await measure()).overlap).toBeLessThanOrEqual(EPS)
      const r = await measure()
      expect(r.overlap).toBeLessThanOrEqual(EPS)
      expect(r.barBottom).toBeLessThanOrEqual(r.viewBottom + EPS)
    })
  }
})

test.describe('narrow screen', () => {
  test.use({ viewport: { width: 390, height: 844 } })
  for (const { path, field } of PAGES) {
    test(`${path}: a dirty bar stays fully visible at the bottom of the screen`, async ({ page, api }) => {
      await page.goto(path)
      await page.getByLabel(field, { exact: true }).first().fill(`e2e-${Date.now()}`)
      await page.evaluate(() => window.scrollTo(0, (document.documentElement.scrollHeight) / 3))
      const bar = page.locator('#settings-savebar')
      await expect(bar).toHaveClass(/dirty/)
      const m = await bar.evaluate((el) => { const b = el.getBoundingClientRect(); return { bottom: b.bottom, vh: window.innerHeight, pos: getComputedStyle(el).position } })
      expect(m.pos).toBe('sticky')
      expect(Math.abs(m.vh - m.bottom)).toBeLessThanOrEqual(EPS)
    })
  }
})
