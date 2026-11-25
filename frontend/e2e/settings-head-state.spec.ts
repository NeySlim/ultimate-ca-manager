import { test, expect, createUser } from './support/fixtures'

// Settings and Account (#455): on a wide screen the save state and its buttons belong to the page head,
// centred over the form column, as head text without a frame, whatever the scroll; nothing of the save
// is left over the form. A phone keeps the bar at the foot of the form, static while clean, sticky while a change waits.
const EPS = 1
// How far the centre of the state and its buttons may sit from the centre of the form column
const CENTRE = 8
// The room kept between the title and the state when the head is short of it
const BESIDE = 20
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

// The head, its title block, the bar and the form column under them, as drawn; `leftover`: save elements found under the head
const layout = (page) => page.evaluate(() => {
  const r = (el: Element | null) => {
    if (!el) return null
    const b = el.getBoundingClientRect()
    return { x: b.x, y: b.y, right: b.right, bottom: b.bottom, width: b.width, height: b.height }
  }
  const head = document.querySelector('.page-head') as HTMLElement
  const bar = document.querySelector('#settings-savebar')
  const state = document.querySelector('#settings-state')
  const intent = head.querySelector(':scope > div:first-child > p')
  const css = bar && getComputedStyle(bar)
  const text = (el: Element | null) => {
    if (!el) return null
    const c = getComputedStyle(el)
    return { size: c.fontSize, family: c.fontFamily, color: c.color }
  }
  return {
    head: r(head) as Rect,
    title: r(head.firstElementChild) as Rect,
    bar: r(bar),
    // A card of the form: the column the state is centred over
    form: r(document.querySelector('#settings-form .settings-section')) as Rect,
    frame: css && {
      border: ['Top', 'Right', 'Bottom', 'Left'].reduce((n, side) => n + parseFloat(css[`border${side}Width`]), 0),
      background: css.backgroundColor,
      image: css.backgroundImage,
      shadow: css.boxShadow,
      radius: parseFloat(css.borderTopLeftRadius),
      outline: css.outlineStyle,
    },
    stateText: text(state),
    intentText: text(intent),
    inHead: !!bar && head.contains(bar),
    leftover: document.querySelectorAll('#view-scroll .settings-savebar, #view-scroll #settings-save, #view-scroll #settings-state').length,
    headOverflow: head.scrollWidth - head.clientWidth,
    pageOverflow: document.documentElement.scrollWidth - window.innerWidth,
    vh: window.innerHeight,
  }
})

const mid = (b: Rect) => ({ x: b.x + b.width / 2, y: b.y + b.height / 2 })

// `centred`: over the form column; else (a state too long to centre) just right of the title, from the column's edge at least
const expectInHead = (m, centred = true) => {
  expect(m.inHead).toBe(true)
  expect(m.leftover).toBe(0)
  const bar = m.bar as Rect
  // inside the head, on screen, level with the title block
  expect(bar.y).toBeGreaterThanOrEqual(m.head.y - EPS)
  expect(bar.bottom).toBeLessThanOrEqual(m.head.bottom + EPS)
  expect(bar.y).toBeGreaterThanOrEqual(0)
  expect(Math.abs(mid(bar).y - mid(m.title).y)).toBeLessThanOrEqual(EPS)
  // clear of the title and within the form column
  expect(bar.x).toBeGreaterThanOrEqual(m.title.right - EPS)
  expect(bar.x).toBeGreaterThanOrEqual(m.form.x - EPS)
  expect(bar.right).toBeLessThanOrEqual(m.form.right + EPS)
  if (centred) expect(Math.abs(mid(bar).x - mid(m.form).x), `state centre ${mid(bar).x} for form centre ${mid(m.form).x}`).toBeLessThanOrEqual(CENTRE)
  else expect(bar.x - Math.max(m.title.right, m.form.x)).toBeLessThanOrEqual(BESIDE + EPS)
  // head text, not a capsule: no border, ground, shadow nor rounded corner
  expect(m.frame).toEqual({ border: 0, background: 'rgba(0, 0, 0, 0)', image: 'none', shadow: 'none', radius: 0, outline: 'none' })
  expect(m.stateText.size).toBe(m.intentText.size)
  expect(m.stateText.family).toBe(m.intentText.family)
  expect(m.headOverflow).toBeLessThanOrEqual(0)
  expect(m.pageOverflow).toBeLessThanOrEqual(0)
}

for (const width of [1912, 1280]) {
  test.describe(`at ${width} px`, () => {
    test.use({ viewport: { width, height: 867 } })
    for (const { path, field, route } of PAGES) {
      test(`${path}: the state and its buttons stay centred over the form in the page head as the page scrolls`, async ({ page, api: _api }) => {
        await page.goto(path)
        const state = page.locator('.page-head #settings-state')
        await expect(state).toBeVisible()
        const headY = (await layout(page)).head.y
        for (const where of ['top', 'middle', 'end'] as const) {
          const s = await scrollTo(page, where)
          if (where !== 'top') expect(s.scrolls).toBe(true)
          const m = await layout(page)
          expectInHead(m)
          // clean: the colour of the description under the title
          expect(m.stateText.color).toBe(m.intentText.color)
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
        const dirty = await layout(page)
        expectInHead(dirty)
        // modified: the warning colour on the state alone, no frame around it
        expect(dirty.stateText.color).not.toBe(dirty.intentText.color)
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

    // The title of /account runs past the contents column, that of /settings stops short of it
    for (const { path } of PAGES) {
      test(`${path}: a state too long to centre sits right of the title, cut to two lines, whole in its title`, async ({ page, api: _api }) => {
        await page.goto(path)
        const text = page.locator('.page-head #settings-state .settings-state-text')
        await expect(text).toBeVisible()
        const m = await text.evaluate((el) => {
          el.textContent = 'Modified, not saved: '.concat(Array.from({ length: 40 }, (_, i) => `Field number ${i}`).join(', '))
          const lh = parseFloat(getComputedStyle(el).lineHeight)
          return { height: el.getBoundingClientRect().height, lines: el.scrollHeight / lh, lh }
        })
        expect(m.lines).toBeGreaterThan(2)
        expect(m.height).toBeLessThanOrEqual(2 * m.lh + EPS)
        expectInHead(await layout(page), false)
      })
    }
  })
}

// Just past the phone width, the longest titles leave the bar short of room: its buttons pass under the state,
// nothing leaves the head nor the window. Account of a 21-character user name (createUser), in Russian and in English.
const narrow = (page) => page.evaluate(() => {
  const head = (document.querySelector('.page-head') as HTMLElement).getBoundingClientRect()
  const bar = document.querySelector('.page-head #settings-savebar') as HTMLElement
  const rect = (id: string) => (document.getElementById(id) as HTMLElement).getBoundingClientRect()
  const title = (document.querySelector('.page-head > div:first-child') as HTMLElement).getBoundingClientRect()
  return {
    inHead: !!bar,
    headRight: head.right,
    titleRight: title.right,
    state: { x: rect('settings-state').x, right: rect('settings-state').right, bottom: rect('settings-state').bottom },
    reset: { x: rect('settings-reset').x, y: rect('settings-reset').y, right: rect('settings-reset').right },
    save: { x: rect('settings-save').x, y: rect('settings-save').y, right: rect('settings-save').right },
    barX: bar?.getBoundingClientRect().x ?? 0,
    headOverflow: (document.querySelector('.page-head') as HTMLElement).scrollWidth - (document.querySelector('.page-head') as HTMLElement).clientWidth,
    pageOverflow: document.documentElement.scrollWidth - window.innerWidth,
    vw: window.innerWidth,
  }
})

for (const [lang, width, h1] of [['ru', 801, 'Моя учётная запись'], ['ru', 820, 'Моя учётная запись'], ['en', 801, 'My Account']] as const) {
  test.describe(`${lang} at ${width} px`, () => {
    test.use({ viewport: { width, height: 867 } })
    for (const { path, input } of [{ path: '/settings', input: '#set-system_name' }, { path: '/account', input: '#set-full_name' }]) {
      test(`${path}: the state and its buttons stay inside the head and the window, clean and modified`, async ({ page: adminPage, api, signIn }) => {
        let page = adminPage
        if (path === '/account') {
          const user = await createUser(api, 'viewer')
          expect(user.username).toHaveLength(21)
          page = (await signIn(user.username, user.password)).page
          await page.setViewportSize({ width, height: 867 })
        }
        await page.addInitScript((l) => { try { localStorage.setItem('i18nextLng', l) } catch { /* noop */ } }, lang)
        await page.goto(path)
        await expect(page.locator('.page-head #settings-state')).toBeVisible()
        if (path === '/account') await expect(page.locator('#main-title')).toHaveText(h1)
        for (const dirty of [false, true]) {
          if (dirty) {
            await page.locator(input).fill(`e2e-${Date.now()}`)
            await expect(page.locator('.page-head #settings-savebar')).toHaveClass(/dirty/)
          }
          const m = await narrow(page)
          const where = `${path} ${lang} ${width} ${dirty ? 'modified' : 'clean'} ${JSON.stringify(m)}`
          expect(m.inHead, where).toBe(true)
          expect(m.save.right, where).toBeLessThanOrEqual(m.headRight + EPS)
          expect(m.save.right, where).toBeLessThanOrEqual(m.vw + EPS)
          expect(m.headOverflow, where).toBeLessThanOrEqual(0)
          expect(m.pageOverflow, where).toBeLessThanOrEqual(0)
          // clear of the title; the two buttons side by side, beside the state or together under it
          expect(m.barX, where).toBeGreaterThanOrEqual(m.titleRight - EPS)
          expect(Math.abs(m.reset.y - m.save.y), where).toBeLessThanOrEqual(EPS)
          expect(m.save.x, where).toBeGreaterThan(m.reset.right)
          if (m.reset.y > m.state.bottom - EPS) expect(Math.abs(m.reset.x - m.state.x), where).toBeLessThanOrEqual(EPS)
          else expect(m.reset.x, where).toBeGreaterThanOrEqual(m.state.right - EPS)
        }
      })
    }
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
