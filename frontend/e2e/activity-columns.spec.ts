import { test, expect, createCA } from './support/fixtures'

// The maintainer's two deviations from the Atelier mockup, measured in a real browser (jsdom lays
// nothing out): short columns as wide as their content, and on a phone a record per entry whose
// chevron stays on screen, a 44 px target, the whole record opening the detail.

// Per column of a table: its width, its padding and the widest content of its cells
const columns = (table) => table.evaluate((t: HTMLTableElement) => {
  const ths = [...t.querySelectorAll('thead th')] as HTMLElement[]
  const rows = [...t.querySelectorAll('tbody tr:not(.sk-row)')].filter(r => r.children.length === ths.length)
  const contentRight = (td: Element) => {
    let right = -Infinity
    const walk = (n: Node) => {
      if (n.nodeType === 3 && n.textContent!.trim()) {
        const r = document.createRange(); r.selectNodeContents(n)
        for (const x of r.getClientRects()) right = Math.max(right, x.right)
      } else if (n instanceof SVGElement || (n instanceof HTMLElement && /badge|icon-btn/.test(n.className))) {
        right = Math.max(right, (n as Element).getBoundingClientRect().right)
      } else if (n instanceof HTMLElement && !n.classList.contains('sr-only')) n.childNodes.forEach(walk)
    }
    walk(td)
    return right
  }
  return ths.map((th, i) => {
    const cs = getComputedStyle(th)
    const inner = th.getBoundingClientRect().width - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight)
    // the widest content of the column, its header included
    const used = Math.max(...[th, ...rows.map(r => r.children[i] as HTMLElement)].map(cell => {
      const ccs = getComputedStyle(cell)
      return contentRight(cell) - cell.getBoundingClientRect().left - parseFloat(ccs.paddingLeft)
    }))
    return { fit: th.classList.contains('fit'), inner: Math.round(inner), used: Math.round(used) }
  })
})

for (const width of [1600, 1250, 1000]) {
  test.describe(`desktop ${width}`, () => {
    test.use({ viewport: { width, height: 1000 } })

    test('the time, user, result and chevron columns are as wide as their content', async ({ page, api }) => {
      expect(api).toBeTruthy()
      await page.goto('/audit')
      const table = page.getByRole('main').locator('.audit-table')
      await expect(table.locator('tbody tr:not(.sk-row)').first()).toBeVisible()
      const cols = await columns(table)
      expect(cols.map(c => c.fit)).toEqual([true, false, false, true, true, true])
      for (const c of cols.filter(col => col.fit)) {
        // no room left at the right of the widest cell
        expect(c.inner - c.used).toBeLessThanOrEqual(2)
      }
      // operation and resource share what is left: each has room beyond its content
      for (const c of cols.filter(col => !col.fit)) expect(c.inner).toBeGreaterThanOrEqual(c.used)
      const scroller = page.locator('#audit-scroll')
      expect(await scroller.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true)
    })
  })
}

test.describe('phone', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('each entry is a record whose chevron stays on screen and opens the detail, keyboard included', async ({ page, api }) => {
    expect(api).toBeTruthy()
    await page.goto('/audit')
    const records = page.getByRole('main').locator('.mobile-record:not(.sk-record)')
    await expect(records.first()).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
    const chevrons = records.locator('.row-top > .icon-btn')
    expect(await chevrons.count()).toBe(await records.count())
    const boxes = await chevrons.evaluateAll(list => list.slice(0, 10).map(el => el.getBoundingClientRect().toJSON()))
    for (const b of boxes) {
      expect(b.left).toBeGreaterThanOrEqual(0)
      expect(b.right).toBeLessThanOrEqual(390)
      expect(b.width).toBeGreaterThanOrEqual(44)
      expect(b.height).toBeGreaterThanOrEqual(44)
    }

    // the whole record opens the detail
    await records.first().locator('.row-status .remaining').click()
    const dialog = page.locator('dialog[open]')
    await expect(dialog).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)

    // from the keyboard: Enter on the chevron, the focus back on it after Escape
    const chevron = chevrons.nth(1)
    await chevron.focus()
    await page.keyboard.press('Enter')
    await expect(dialog).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(dialog).toHaveCount(0)
    await expect(chevron).toBeFocused()
  })

  test('the CA list keeps a chevron on screen at the right of each record', async ({ page, api }) => {
    await createCA(api)
    await page.addInitScript(() => { try { localStorage.setItem('ucm-ca-view-mode', 'list') } catch { /* optional */ } })
    await page.goto('/cas')
    const records = page.locator('.lv-mrecord.is-opening')
    await expect(records.first()).toBeVisible()
    const boxes = await records.locator('.lv-mrecord-open').evaluateAll(list => list.slice(0, 10).map(el => el.getBoundingClientRect().toJSON()))
    expect(boxes.length).toBeGreaterThan(0)
    for (const b of boxes) {
      expect(b.right).toBeLessThanOrEqual(390)
      expect(b.width).toBeGreaterThanOrEqual(44)
      expect(b.height).toBeGreaterThanOrEqual(44)
    }
  })
})
