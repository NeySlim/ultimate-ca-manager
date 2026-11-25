import { test, expect, createUser } from './support/fixtures'

// Settings and Account (#455): on a wide screen the save state and its buttons sit in the page head,
// right of the title, whatever the scroll; nothing of the save is left over the form. A phone keeps
// the bar at the foot of the form, static while clean, sticky while a change waits.
const EPS = 1
const PAGES = [
  { path: '/settings', field: 'Syslog hostname', route: /\/api\/v2\/settings\/general$/ },
  { path: '/account', field: 'Full Name', route: /\/api\/v2\/account\/profile$/ },
]
type Rect = { x: number; y: number; right: number; bottom: number; width: number; height: number }

const scrollTo = (page, where: 'top' | 'middle' | 'end') => page.evaluate((w) => {
  const view = document.querySelector('#view-scroll') as HTMLElement
  const max = view.scrollHeight - view.clientHeight
  view.scrollTop = w === 'top' ? 0 : w === 'middle' ? max / 2 : max
  return { scrolls: max > 0, top: view.scrollTop }
}, where)

// The head, its title block and the bar, as drawn; `leftover`: save elements found under the head
const layout = (page) => page.evaluate(() => {
  const r = (el: Element | null) => {
    if (!el) return null
    const b = el.getBoundingClientRect()
    return { x: b.x, y: b.y, right: b.right, bottom: b.bottom, width: b.width, height: b.height }
  }
  const head = document.querySelector('.page-head') as HTMLElement
  const bar = document.querySelector('#settings-savebar')
  return {
    head: r(head) as Rect,
    title: r(head.firstElementChild) as Rect,
    bar: r(bar),
    inHead: !!bar && head.contains(bar),
    leftover: document.querySelectorAll('#view-scroll .settings-savebar, #view-scroll #settings-save, #view-scroll #settings-state').length,
    headOverflow: head.scrollWidth - head.clientWidth,
    pageOverflow: document.documentElement.scrollWidth - window.innerWidth,
    vh: window.innerHeight,
  }
})

const expectInHead = (m) => {
  expect(m.inHead).toBe(true)
  expect(m.leftover).toBe(0)
  const bar = m.bar as Rect
  // inside the head, on screen, right of the title and at the right edge of the head
  expect(bar.y).toBeGreaterThanOrEqual(m.head.y - EPS)
  expect(bar.bottom).toBeLessThanOrEqual(m.head.bottom + EPS)
  expect(bar.y).toBeGreaterThanOrEqual(0)
  expect(bar.x).toBeGreaterThanOrEqual(m.title.right - EPS)
  expect(Math.abs(bar.right - m.head.right)).toBeLessThanOrEqual(EPS)
  expect(m.headOverflow).toBeLessThanOrEqual(0)
  expect(m.pageOverflow).toBeLessThanOrEqual(0)
}

for (const width of [1912, 1280]) {
  test.describe(`at ${width} px`, () => {
    test.use({ viewport: { width, height: 867 } })
    for (const { path, field, route } of PAGES) {
      test(`${path}: the state and its buttons stay in the page head as the page scrolls`, async ({ page, api: _api }) => {
        await page.goto(path)
        const state = page.locator('.page-head #settings-state')
        await expect(state).toBeVisible()
        const headY = (await layout(page)).head.y
        for (const where of ['top', 'middle', 'end'] as const) {
          const s = await scrollTo(page, where)
          if (where !== 'top') expect(s.scrolls).toBe(true)
          const m = await layout(page)
          expectInHead(m)
          // the head does not scroll with the form
          expect(Math.abs(m.head.y - headY)).toBeLessThanOrEqual(EPS)
        }
        await expect(page.locator('.page-head #settings-savebar')).not.toHaveClass(/dirty/)
        await expect(page.locator('.page-head #settings-save')).toBeDisabled()
        await expect(state).toHaveAttribute('title', /No changes pending\./)
      })

      test(`${path}: a change is pending in the head, saved by Save, undone by Undo`, async ({ page: adminPage, api, signIn }) => {
        // The administrator's address (admin@localhost) is refused by a profile save: the account is a user's own
        let page = adminPage
        if (path === '/account') {
          const user = await createUser(api, 'viewer')
          page = (await signIn(user.username, user.password)).page
          await page.setViewportSize({ width, height: 867 })
        }
        await page.goto(path)
        const bar = page.locator('.page-head #settings-savebar')
        const save = bar.getByRole('button', { name: 'Save', exact: true })
        const undo = bar.getByRole('button', { name: 'Undo changes' })
        const input = page.getByLabel(field, { exact: true }).first()
        await expect(save).toBeDisabled()
        const before = await input.inputValue()

        await input.fill(`e2e-undo-${Date.now()}`)
        await expect(bar).toHaveClass(/dirty/)
        await expect(bar.locator('#settings-state')).toContainText(`Modified, not saved: ${field}.`)
        await scrollTo(page, 'middle')
        expectInHead(await layout(page))
        await undo.click()
        await expect(input).toHaveValue(before)
        await expect(bar).not.toHaveClass(/dirty/)

        const value = `e2e-${width}-${Date.now()}`
        await input.fill(value)
        await expect(save).toBeEnabled()
        const [response] = await Promise.all([
          page.waitForResponse((r) => r.request().method() === 'PATCH' && route.test(new URL(r.url()).pathname)),
          save.click(),
        ])
        expect(response.ok()).toBe(true)
        await expect(bar).not.toHaveClass(/dirty/)
        await expect(save).toBeDisabled()
        await expect(input).toHaveValue(value)
      })
    }

    test('/settings: a state too long for the head is cut to two lines, whole in its title', async ({ page, api: _api }) => {
      await page.goto('/settings')
      const text = page.locator('.page-head #settings-state .settings-state-text')
      await expect(text).toBeVisible()
      const m = await text.evaluate((el) => {
        el.textContent = 'Modified, not saved: '.concat(Array.from({ length: 40 }, (_, i) => `Field number ${i}`).join(', '))
        const lh = parseFloat(getComputedStyle(el).lineHeight)
        return { height: el.getBoundingClientRect().height, lines: el.scrollHeight / lh, lh }
      })
      expect(m.lines).toBeGreaterThan(2)
      expect(m.height).toBeLessThanOrEqual(2 * m.lh + EPS)
      expectInHead(await layout(page))
    })
  })
}

test.describe('on a phone', () => {
  test.use({ viewport: { width: 390, height: 844 } })
  for (const { path, field } of PAGES) {
    test(`${path}: the bar sits at the foot of the form, static while clean, sticky while dirty`, async ({ page, api: _api }) => {
      await page.goto(path)
      const bar = page.locator('#settings-form #settings-savebar')
      await expect(bar).toBeAttached()
      await expect(page.locator('.page-head #settings-savebar')).toHaveCount(0)
      expect(await bar.evaluate((el) => getComputedStyle(el).position)).toBe('static')
      await page.getByLabel(field, { exact: true }).first().fill(`e2e-${Date.now()}`)
      await expect(bar).toHaveClass(/dirty/)
      await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight / 3))
      const m = await bar.evaluate((el) => {
        const b = el.getBoundingClientRect()
        return { bottom: b.bottom, vh: window.innerHeight, pos: getComputedStyle(el).position }
      })
      expect(m.pos).toBe('sticky')
      expect(Math.abs(m.vh - m.bottom)).toBeLessThanOrEqual(EPS)
    })
  }
})
