import { test, expect, open, createCA, issueCert } from './support/fixtures'

// The measures of the page: past a 1920 px window the page and the bars' contents hold
// 1852 px, centred, the bars' grounds edge to edge; the form cards and their texts have their own (below).
const EPS = 1
const PAGE = 1852
// The stage's side margin: the mockup's 24 px, 34 px from 1800 px, then what the page measure leaves
const side = (w: number) => (w > 1920 ? (w - PAGE) / 2 : w >= 1800 ? 34 : 24)

type Box = { x: number; y: number; width: number; height: number }
const box = async (locator): Promise<Box> => {
  await expect(locator).toBeVisible()
  return (await locator.boundingBox()) as Box
}
// The box inside an element's side paddings
const content = (locator) => locator.evaluate((el) => {
  const r = el.getBoundingClientRect(), c = getComputedStyle(el)
  const l = parseFloat(c.paddingLeft), rt = parseFloat(c.paddingRight)
  return { x: r.x + l, width: r.width - l - rt }
})
const near = (a: number, b: number, what: string) => expect(Math.abs(a - b), `${what}: ${a} for ${b}`).toBeLessThanOrEqual(EPS)

for (const width of [1600, 1880, 1920, 2560, 3440]) {
  test(`at ${width}px the page and the bars' contents keep the 1920 px layout, centred past it`, async ({ page, api: _api }) => {
    await page.setViewportSize({ width, height: 1000 })
    await open(page, '/certificates')
    const m = side(width)
    // The grounds and rules of the bars run from edge to edge
    for (const bar of ['.masthead', '.statusbar']) {
      const b = await box(page.locator(`.atl ${bar}`))
      near(b.x, 0, `${bar} left`)
      near(b.width, width, `${bar} width`)
    }
    // Their contents and the stage's sit in the measure
    for (const part of ['.masthead', '.statusbar', '#app > .stage']) {
      const c = await content(page.locator(`.atl ${part}`).first())
      near(c.x, m, `${part} content left`)
      near(c.width, width - 2 * m, `${part} content width`)
    }
    near((await box(page.locator('.masthead .brand'))).x, m, 'brand')
    const tools = await box(page.locator('.masthead .global-tools'))
    near(tools.x + tools.width, width - m, 'tools right edge')
    near((await box(page.locator('.statusbar .live .dot'))).x, m, 'status dot')
    const head = await box(page.locator('.atl .page-head'))
    near(head.x, m, 'page head left')
    near(head.width, width - 2 * m, 'page head width')
  })
}

test('at 3440px the Modules menu follows its button and the notification panel stays at the window\'s edge', async ({ page, api: _api }) => {
  await page.setViewportSize({ width: 3440, height: 1440 })
  await open(page, '/certificates')
  await expect(page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Activity' })).toBeVisible()
  const button = page.getByRole('button', { name: 'Modules' })
  await button.click()
  const menu = await box(page.getByRole('navigation', { name: 'Product modules' }))
  near(menu.x, (await box(button)).x, 'Modules menu under its button')
  expect(menu.x + menu.width).toBeLessThanOrEqual(3440 - side(3440) + EPS)
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: /^Notifications/ }).click()
  const panel = await box(page.getByRole('complementary', { name: 'Notifications' }))
  near(panel.x + panel.width, 3440, 'notification panel right edge')
})

for (const width of [1920, 3440]) {
  test(`at ${width}px a certificate's inspector and its detached window stay in the page`, async ({ page, api }) => {
    await page.setViewportSize({ width, height: 1200 })
    const cert = await issueCert(api, (await createCA(api)).id)
    await page.goto('/certificates')
    await page.getByRole('main').getByRole('searchbox').fill(cert.common_name)
    await page.getByRole('main').getByRole('button', { name: cert.common_name, exact: true }).click()
    const dock = page.locator('#inspector')
    await expect(dock.getByRole('heading', { name: cert.common_name })).toBeVisible()
    const m = side(width)
    const d = await box(dock)
    expect(d.x).toBeGreaterThanOrEqual(m - EPS)
    expect(d.x + d.width).toBeLessThanOrEqual(width - m + EPS)
    await dock.getByRole('button', { name: 'Detach into a window' }).click()
    const win = page.getByRole('dialog', { name: cert.common_name })
    const w = await box(win)
    expect(w.x).toBeGreaterThanOrEqual(m - EPS)
    expect(w.x + w.width).toBeLessThanOrEqual(width - m + EPS)
    // Maximized: the stage's content box, as at 1920 px
    await win.getByRole('button', { name: 'Maximize the window' }).click()
    const full = await box(win)
    near(full.x, m, 'maximized left')
    near(full.width, width - 2 * m, 'maximized width')
  })
}

// The form pages (Settings, Account): a card holds 960 px beside the
// contents while its column is narrower than 1280 px; from 1280 px it takes the column and lays its groups of
// fields in two columns 48 px apart. No field nor text grows: helps 62ch, notices 78ch, fields 640 px (220 px short).
const FORM = 960
const WIDE = 1280
const GUTTER = 48
const FIELD = 640
const SHORT = 220
const column = (w: number) => Math.min(w, 1920) - 2 * side(Math.min(w, 1920)) - 224

// Every card of the page: its box, the blocks of its body (a plain group of fields, or what keeps the whole card), its fields
const cardsOf = (page) => page.locator('.atl .settings-layout .settings-section').evaluateAll((els) => els.map((el) => {
  const r = el.getBoundingClientRect()
  const body = el.querySelector(':scope > .settings-body') as HTMLElement
  const c = getComputedStyle(body)
  const inner = { x: body.getBoundingClientRect().x + parseFloat(c.paddingLeft), width: body.clientWidth - parseFloat(c.paddingLeft) - parseFloat(c.paddingRight) }
  const blocks = [...body.children].filter((k) => (k as HTMLElement).offsetParent && getComputedStyle(k).position === 'static').map((k) => {
    const b = k.getBoundingClientRect()
    return { plain: k.matches('.settings-group:not(.wide)'), what: `${k.tagName.toLowerCase()}.${k.className}`, x: b.x, y: b.y, width: b.width, bottom: b.bottom }
  })
  const fields = [...body.querySelectorAll('.field > :is(input:not([type=checkbox],[type=radio],[type=file]), select, textarea)')]
    .filter((f) => (f as HTMLElement).offsetParent && !f.closest('dialog'))
    .map((f) => ({ id: f.id, short: !!f.closest('.field.short'), width: f.getBoundingClientRect().width }))
  const grids = [...body.querySelectorAll(':scope > .settings-group:not(.wide) > .settings-grid')]
    .map((g) => getComputedStyle(g).gridTemplateColumns.split(' ').length)
  return { id: el.id, x: r.x, width: r.width, inner, blocks, fields, grids }
}))

// Texts wider than `measure` characters of their own font
const overMeasure = (page, selector: string, measure: number) => page.locator('.atl .settings-layout').evaluate((layout, [sel, ch]) => {
  const out: string[] = []
  for (const el of layout.querySelectorAll(sel as string)) {
    if (getComputedStyle(el).display === 'inline' || !(el as HTMLElement).offsetParent) continue
    const probe = document.createElement('span')
    probe.style.cssText = `position:absolute;visibility:hidden;width:${ch}ch`
    el.appendChild(probe)
    const limit = probe.getBoundingClientRect().width
    probe.remove()
    const w = el.getBoundingClientRect().width
    if (w > limit + 1) out.push(`${el.textContent?.slice(0, 40)}: ${Math.round(w)} > ${Math.round(limit)}`)
  }
  return out
}, [selector, measure] as const)

const expectCards = async (page, width: number, where: string) => {
  const toc = await box(page.locator('.atl .settings-toc'))
  near(toc.x, side(width), `${where}: contents at the left of the page`)
  const col = column(width)
  const wide = col >= WIDE
  const cards = await cardsOf(page)
  expect(cards.length, where).toBeGreaterThan(0)
  for (const c of cards) {
    near(c.x, toc.x + 200 + 24, `${where} ${c.id} beside the contents`)
    near(c.width, wide ? col : Math.min(FORM, col), `${where} ${c.id} width`)
    const half = (c.inner.width - GUTTER) / 2
    const plain = c.blocks.filter((b) => b.plain)
    for (const b of c.blocks) {
      // a table, a notice, a test line, a group marked wide: the whole card; a group of fields: half of it from 1280 px
      near(b.width, wide && b.plain ? half : c.inner.width, `${where} ${c.id} ${b.what} width`)
      if (!wide || !b.plain) near(b.x, c.inner.x, `${where} ${c.id} ${b.what} left`)
      else expect([c.inner.x, c.inner.x + half + GUTTER].some((x) => Math.abs(b.x - x) <= EPS), `${where} ${c.id} ${b.what} in a column: ${b.x}`).toBe(true)
    }
    if (wide) {
      // runs of groups between two blocks on the whole card: both columns start level, their groups 20 px apart, none left alone at the right
      let run: typeof plain = []
      const close = () => {
        const left = run.filter((b) => Math.abs(b.x - c.inner.x) <= EPS), right = run.filter((b) => Math.abs(b.x - c.inner.x) > EPS)
        if (run.length > 1) expect(right.length, `${where} ${c.id}: two columns`).toBeGreaterThan(0)
        if (right.length) near(right[0].y, left[0].y, `${where} ${c.id}: columns start level`)
        for (const side of [left, right]) for (let i = 1; i < side.length; i++) near(side[i].y - side[i - 1].bottom, 20, `${where} ${c.id}: 20 px between groups`)
        run = []
      }
      for (const b of c.blocks) { if (b.plain) run.push(b); else close() }
      close()
      // a group on half a card: two columns of fields under 700 px, four from there
      for (const n of c.grids) expect(n, `${where} ${c.id}: columns of a group of ${Math.round(half)} px`).toBe(half < 700 ? 2 : 4)
      for (const f of c.fields) expect(f.width, `${where} ${c.id} #${f.id}`).toBeLessThanOrEqual((f.short ? SHORT : FIELD) + EPS)
    }
  }
  expect(await overMeasure(page, '.settings-body small, .settings-body p, .settings-section .panel-heading p', 62), `${where}: helps`).toEqual([])
  expect(await overMeasure(page, '.notice > span', 78), `${where}: notices`).toEqual([])
  return { toc, cards, wide, col }
}

for (const width of [1280, 1440, 1600, 1920, 2560, 3440]) {
  test(`at ${width}px the settings' cards hold 960 px or, from 1280 px of column, the column with two groups abreast`, async ({ page, api: _api }) => {
    await page.setViewportSize({ width, height: 1000 })
    await open(page, '/settings')
    const { toc, cards, wide, col } = await expectCards(page, width, '/settings')
    expect(cards.length).toBeGreaterThan(10)
    // the limits themselves are on the page: a notice and a help long enough to be cut, a long field at its cap
    const general = cards.find((c) => c.id === 'set-sec-general')!
    expect(general.blocks.filter((b) => b.plain).length).toBeGreaterThanOrEqual(4)
    if (wide) near(general.fields.find((f) => f.id === 'set-base_url')!.width, Math.min(FIELD, (general.inner.width - GUTTER) / 2), 'public URL')
    // The save state is in the page head, centred over the cards' column (#455)
    const bar = await box(page.locator('.page-head #settings-savebar'))
    near(bar.x + bar.width / 2, toc.x + 200 + 24 + (wide ? col : Math.min(FORM, col)) / 2, 'save state over the middle of the cards')
    // A help held to the measure in a centred empty block stays centred under its title
    const empties = await page.locator('.atl .settings-layout').evaluate((layout) => [...layout.querySelectorAll('.settings-body .empty p')]
      .filter((p) => (p as HTMLElement).offsetParent)
      .map((p) => {
        const a = p.getBoundingClientRect(), b = p.closest('.empty')!.getBoundingClientRect()
        return Math.round(Math.abs((a.left + a.right) / 2 - (b.left + b.right) / 2))
      }))
    expect(empties.length).toBeGreaterThan(0)
    expect(empties.filter((d) => d > 1)).toEqual([])
  })
}

for (const width of [1280, 1600, 1920, 2560]) {
  test(`at ${width}px the account follows the same rule`, async ({ page, api: _api }) => {
    await page.setViewportSize({ width, height: 1000 })
    for (const path of ['/account']) {
      await open(page, path)
      await expect(page.locator('.atl .settings-layout .settings-section').first()).toBeVisible()
      const { cards, wide } = await expectCards(page, width, path)
      // a card of one group of fields keeps it in the first column
      if (wide) for (const c of cards) {
        const plain = c.blocks.filter((b) => b.plain)
        if (plain.length === 1) near(plain[0].x, c.inner.x, `${path} ${c.id}: its only group at the left`)
      }
    }
  })
}

for (const width of [820, 1024]) {
  test(`at ${width}px the settings keep one group per line in cards of 960 px at most`, async ({ page, api: _api }) => {
    await page.setViewportSize({ width, height: 1000 })
    await open(page, '/settings')
    const m = width <= 1000 ? 18 : 24
    await expect(page.locator('#set-sec-general')).toBeVisible()
    const cards = await cardsOf(page)
    expect(cards.length).toBeGreaterThan(10)
    for (const c of cards) {
      near(c.width, Math.min(FORM, width - 2 * m - 224), `${c.id} width`)
      for (const b of c.blocks) near(b.width, c.inner.width, `${c.id} ${b.what} width`)
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0)
  })
}

test('on a phone the settings keep one column', async ({ page, api: _api }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await open(page, '/settings')
  const columns = await page.locator('.atl .settings-layout').evaluate((el) => getComputedStyle(el).gridTemplateColumns.split(' ').length)
  expect(columns).toBe(1)
})

for (const width of [1920, 3440]) {
  test(`at ${width}px the guide keeps its own measure, its bar's contents in the page`, async ({ page, api: _api }) => {
    await page.setViewportSize({ width, height: 1000 })
    await page.goto('/guide/acme')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('ACME')
    // The guide scrolls the document: the page is the width its scroll bar leaves
    const view = await page.evaluate(() => document.querySelector('.guide-app')!.clientWidth)
    const m = side(view)
    near((await box(page.locator('.guide-head .brand'))).x, m, 'guide brand')
    const back = await box(page.locator('.guide-head .guide-back'))
    near(back.x + back.width, view - m, 'guide back button')
    near((await box(page.locator('.guide-toc'))).width, 220, 'guide contents')
    near((await box(page.locator('.guide-main'))).width, 972, 'guide reading column')
  })
}
