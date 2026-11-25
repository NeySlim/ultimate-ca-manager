import { test, expect, open, createCA, issueCert } from './support/fixtures'

// The measures of the page: past a 1920 px window the page and the bars' contents hold
// 1852 px, centred, the bars' grounds edge to edge; the settings' cards 960 px beside their contents; their help 62ch.
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

for (const width of [1440, 1920, 3440]) {
  test(`at ${width}px the settings' cards hold 960 px beside their contents, their help 62ch`, async ({ page, api: _api }) => {
    await page.setViewportSize({ width, height: 1000 })
    await open(page, '/settings')
    const m = side(width)
    const toc = await box(page.locator('.atl .settings-toc'))
    near(toc.x, m, 'contents at the left of the page')
    const column = width - 2 * m - 224
    const cards = await page.locator('.atl .settings-layout .settings-section').evaluateAll((els) => els.map((el) => {
      const r = el.getBoundingClientRect()
      return { id: el.id, x: r.x, width: r.width }
    }))
    expect(cards.length).toBeGreaterThan(10)
    for (const c of cards) {
      near(c.x, toc.x + 200 + 24, `${c.id} beside the contents`)
      // The scheduler's table of nine columns is the exception: it keeps the whole column
      near(c.width, c.id === 'set-sec-scheduler' ? column : Math.min(960, column), `${c.id} width`)
    }
    // The save state is in the page head, centred over the cards' column (#455)
    const bar = await box(page.locator('.page-head #settings-savebar'))
    near(bar.x + bar.width / 2, toc.x + 200 + 24 + Math.min(960, column) / 2, 'save state over the middle of the cards')
    // Every help and description of a section, a block, at most 62ch of its own font
    const over = await page.locator('.atl .settings-layout').evaluate((layout) => {
      const out: string[] = []
      for (const el of layout.querySelectorAll('.settings-body small, .settings-body p, .settings-section .panel-heading p')) {
        if (getComputedStyle(el).display === 'inline' || !(el as HTMLElement).offsetParent) continue
        const probe = document.createElement('span')
        probe.style.cssText = 'position:absolute;visibility:hidden;width:62ch'
        el.appendChild(probe)
        const limit = probe.getBoundingClientRect().width
        probe.remove()
        const w = el.getBoundingClientRect().width
        if (w > limit + 1) out.push(`${el.textContent?.slice(0, 40)}: ${Math.round(w)} > ${Math.round(limit)}`)
      }
      return out
    })
    expect(over).toEqual([])
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
