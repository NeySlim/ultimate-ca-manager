import { test, expect, createCA, issueCert, createUser } from './support/fixtures'

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

// Other tests issue certificates at the same time: the list is searched down to this one
async function openListOn(page, name: string) {
  await page.goto('/certificates')
  await page.getByRole('main').getByRole('searchbox').fill(name)
}

test.use({ viewport: { width: W, height: H } })

// The inspector's size and fold are preferences of the account: tests that change them take their own
async function ownSession(api, signIn) {
  const user = await createUser(api, 'viewer')
  return (await signIn(user.username, user.password)).page
}

test('the list shows its seven columns whole and the inspector opens in the page flow', async ({ api, signIn }) => {
  const cert = await issueCert(api, (await createCA(api)).id)
  const page = await ownSession(api, signIn)
  await openListOn(page, cert.common_name)
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

test('the inspector band grows to 420 px and Escape closes it from the list', async ({ api, signIn }) => {
  const cert = await issueCert(api, (await createCA(api)).id)
  const page = await ownSession(api, signIn)
  await openListOn(page, cert.common_name)
  const main = page.getByRole('main')
  await main.getByRole('button', { name: cert.common_name, exact: true }).click()
  const dock = page.getByTestId('inspector-dock')
  await expect(dock).toBeVisible()
  expect(Math.round((await box(dock)).height)).toBe(278)
  await dock.getByRole('button', { name: 'Enlarge the inspector' }).click()
  expect(Math.round((await box(dock)).height)).toBe(420)
  // The focus back on the list, Escape still closes the inspector
  await main.getByRole('searchbox').fill('')
  await main.getByRole('searchbox').focus()
  await page.keyboard.press('Escape')
  await expect(dock).toBeHidden()
})

// The page scrolls under a finger or a wheel until the pagination of the list is on screen
async function footerReachedByScrolling(page, api, height: number) {
  const ca = await createCA(api)
  for (let i = 0; i < 8; i++) await issueCert(api, ca.id)
  await page.goto('/certificates')
  const main = page.getByRole('main')
  await expect(main.getByRole('listitem').first()).toBeVisible()
  const next = main.locator('.lv-footer').getByRole('button', { name: 'Next page' })
  await expect(next).toBeAttached()
  expect((await box(next)).y).toBeGreaterThan(height)
  await page.mouse.move(195, height / 2)
  for (let i = 0; i < 8; i++) await page.mouse.wheel(0, 500)
  // Above the status bar, which stays on screen
  const bar = (await box(page.getByRole('contentinfo'))).y
  await expect.poll(async () => { const b = await box(next); return b.y >= 0 && b.y + b.height <= bar }).toBe(true)
}

for (const [w, h] of [[390, 844], [800, 1000]]) {
  test.describe(`the list at ${w} x ${h}`, () => {
    test.use({ viewport: { width: w, height: h } })
    test('scrolls down to its pagination', async ({ page, api }) => {
      await footerReachedByScrolling(page, api, h)
    })
  })
}

// The mockup's two filters keep its widths beside the export button (151 px at 390, 356 at 800) and the
// toolbar its 90 px; the product's template filter follows them in the strip, reached by Tab or a swipe
for (const w of [390, 800]) {
  test.describe(`the filters at ${w} px`, () => {
    test.use({ viewport: { width: w, height: 1000 } })
    test('keep the mockup widths, with no line added, the third one in the strip', async ({ page, api }) => {
      await createCA(api)
      await page.goto('/certificates')
      const main = page.getByRole('main')
      const filters = main.locator('.lv-toolbar .lv-filter > button')
      await expect(filters.first()).toBeVisible()
      await expect(filters).toHaveCount(3)
      const half = (w - 32 - 8 - 40 - 8) / 2
      const [a, b] = [await box(filters.nth(0)), await box(filters.nth(1))]
      expect(Math.round(a.x)).toBe(16)
      expect(Math.round(a.width)).toBe(Math.round(half))
      expect(Math.round(b.width)).toBe(Math.round(half))
      expect(Math.round(b.y)).toBe(Math.round(a.y))
      expect(Math.round(b.x)).toBe(Math.round(a.x + a.width + 8))
      const exportButton = await box(main.getByRole('button', { name: 'Export data' }))
      expect(Math.round(exportButton.x)).toBe(w - 16 - 40)
      expect(Math.round((await box(main.locator('.lv-toolbar'))).height)).toBe(90)
      // The labels are whole: no ellipsis on the mockup's two
      for (const i of [0, 1]) {
        expect(await filters.nth(i).locator('span').evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
      }
      // Tab from the second filter brings the third one whole into the strip, the export button in place
      await filters.nth(1).focus()
      await page.keyboard.press('Tab')
      await expect(filters.nth(2)).toBeFocused()
      await expect.poll(async () => {
        const c = await box(filters.nth(2))
        return Math.round(c.x + c.width) <= w - 16 - 40 - 8 + 1 && c.x >= 16 - 1
      }).toBe(true)
      expect(Math.round((await box(main.getByRole('button', { name: 'Export data' }))).x)).toBe(w - 16 - 40)
      // Its menu opens whole inside the window, not clipped by the strip
      await page.keyboard.press('Enter')
      const menu = main.locator('.lv-toolbar .lv-filter .ui-pop')
      await expect(menu).toBeVisible()
      const m = await box(menu)
      expect(m.x).toBeGreaterThanOrEqual(0)
      expect(m.x + m.width).toBeLessThanOrEqual(w + EPS)
      const hit = await menu.evaluate((el) => {
        const r = el.getBoundingClientRect()
        return el.contains(document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2))
      })
      expect(hit).toBe(true)
    })
  })
}

test.describe('on a phone', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('each certificate is a record inside the 16 px gutter, and the inspector takes the screen', async ({ page, api }) => {
    const cert = await issueCert(api, (await createCA(api)).id)
    await openListOn(page, cert.common_name)
    const main = page.getByRole('main')
    await expect(main.getByRole('table')).toHaveCount(0)
    const record = main.getByRole('listitem').filter({ has: page.getByRole('button', { name: cert.common_name, exact: true }) })
    await expect(record).toBeVisible()
    const r = await box(record)
    expect(r.x).toBeGreaterThanOrEqual(16 - EPS)
    expect(r.x + r.width).toBeLessThanOrEqual(390 - 16 + EPS)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    const name = await box(record.getByRole('button', { name: cert.common_name, exact: true }))
    expect(name.height).toBeGreaterThanOrEqual(42 - EPS)
    await record.getByRole('button', { name: cert.common_name, exact: true }).click()
    const dock = page.getByTestId('inspector-dock')
    await expect(dock).toBeVisible()
    const d = await box(dock)
    expect(Math.round(d.x)).toBe(0)
    expect(Math.round(d.width)).toBe(390)
    expect(Math.round(d.height)).toBe(844)
  })
})


test.describe('at 1000 px', () => {
  test.use({ viewport: { width: 1000, height: 1000 } })

  test('keeps one row action, the columns tool by its icon, an overview in two columns', async ({ page, api }) => {
    const cert = await issueCert(api, (await createCA(api)).id)
    await openListOn(page, cert.common_name)
    const main = page.getByRole('main')
    const row = main.getByRole('row', { name: new RegExp(cert.common_name.replace(/\./g, '\\.')) })
    await expect(row).toBeVisible()
    await expect(row.locator('.lv-row-actions .lv-icon-btn:visible')).toHaveCount(1)
    expect(Math.round((await box(main.getByRole('button', { name: 'Columns' }))).width)).toBe(41)
    await main.getByRole('button', { name: cert.common_name, exact: true }).click()
    const overview = page.getByTestId('certificate-overview')
    await expect(overview).toBeVisible()
    expect(await overview.evaluate(el => getComputedStyle(el).gridTemplateColumns.split(' ').length)).toBe(2)
    await expect(overview.locator('.ins-overview-chain')).toBeHidden()
  })
})
