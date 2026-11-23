import { test, expect, createCA, issueCert, uid } from './support/fixtures'
import { freezeApi } from './support/frozen'

// The list template measured where jsdom cannot (COLONNES-SPEC G1, G2): on Certificates, the authorities' list
// and CRL / OCSP, no horizontal scroll at any desktop width, the chevron always in view, the folded columns said
// in the footer, one column taking the room left, no free text cut while the sum fits (R1), numbers at the right and
// apart from a date, header separators and sort signs readable in the four themes as painted at scale 1 (R3), the sort
// button over its whole cell (R4), the sorted column in weight 600 (R5), the open row under the sticky header (G6), a
// ticked list's names readable (R7), the sort from the keyboard and kept by a reload, the phone's sort and records.

const LISTS = [
  { name: 'certificates', url: '/certificates', region: '#cert-scroll' },
  { name: 'authorities', url: '/cas', region: '#ca-list-scroll' },
  { name: 'crl', url: '/crl-ocsp', region: '#module-scroll' },
]

async function open(page, list) {
  if (list.name === 'authorities') await page.addInitScript(() => localStorage.setItem('ucm-ca-view-mode', 'list'))
  await page.goto(list.url)
  await expect(page.locator(`${list.region} tbody tr`).first()).toBeVisible()
}

// The geometry of a list: horizontal overflow, rows whose chevron is out of the region, clipped headers and fixed cells
const geometry = (page, region) => page.locator(region).evaluate((el) => {
  const box = el.getBoundingClientRect()
  const rows = [...el.querySelectorAll('tbody tr')].filter((tr) => tr.querySelector('[data-open]'))
  const lost = rows.filter((tr) => {
    const chevron = [...tr.querySelectorAll('td:last-child button.icon-btn[data-open]')].pop()
    if (!chevron) return true
    const r = chevron.getBoundingClientRect()
    return !r.width || !r.height || r.left < box.left - 1 || r.right > box.right + 1
  }).length
  const clippedHeads = [...el.querySelectorAll('thead th')].filter((th) => th.scrollWidth > th.clientWidth + 1).map((th) => th.textContent)
  const heads = [...el.querySelectorAll('thead th')]
  const fitCut: string[] = []
  heads.forEach((th, i) => {
    if (!th.classList.contains('fit') || th.querySelector('input, .sr-only')) return
    for (const tr of el.querySelectorAll('tbody tr')) {
      const td = tr.children[i] as HTMLElement
      if (td && !td.classList.contains('text-cell') && !td.classList.contains('entity-cell') && td.scrollWidth > td.clientWidth + 1) fitCut.push(td.textContent || '')
    }
  })
  return { over: el.scrollWidth - el.clientWidth, page: document.documentElement.scrollWidth - document.documentElement.clientWidth, rows: rows.length, lost, clippedHeads, fitCut }
})

for (const width of [1000, 1280, 1600]) {
  test.describe(`at ${width} px, dock closed`, () => {
    test.use({ viewport: { width, height: 900 } })

    test('no list scrolls sideways, every chevron is in view, a folded column is said in the footer', async ({ page, api }) => {
      const ca = await createCA(api, { commonName: `Regional Issuing Authority for the West ${uid('ca')}` })
      await issueCert(api, ca.id, { cn: `${uid('a-long-service-name')}.internal.example.com` })
      for (const list of LISTS) {
        await open(page, list)
        await expect.poll(() => geometry(page, list.region).then((g) => g.over), { message: list.name }).toBeLessThanOrEqual(1)
        const g = await geometry(page, list.region)
        expect(g, list.name).toMatchObject({ lost: 0, clippedHeads: [], fitCut: [] })
        expect(g.page, list.name).toBeLessThanOrEqual(0)
        // The footer names the columns folded for want of room, and only then
        const shown = await page.locator(`${list.region} thead th`).count()
        const note = page.locator('.atl .table-footer .folded-note')
        if (await note.count()) {
          const n = Number((await note.textContent())!.match(/\d+/)![0])
          expect(n, list.name).toBeGreaterThan(0)
          expect((await note.getAttribute('title'))!.split(', ')).toHaveLength(n)
        }
        expect(shown, list.name).toBeGreaterThan(2)
      }
    })
  })
}

test.describe('the columns at 1600 px', () => {
  test.use({ viewport: { width: 1600, height: 1000 } })

  test('one column takes the room left: the description, else the name; a number reads at the right', async ({ page, api }) => {
    await createCA(api)
    const absorbers = {}
    for (const list of LISTS) {
      await open(page, list)
      absorbers[list.name] = await page.locator(`${list.region} thead th`).evaluateAll((ths) => ths
        .filter((th) => !th.classList.contains('fit') && !th.querySelector('input, .sr-only')).map((th) => th.textContent))
    }
    expect(absorbers).toEqual({ certificates: ['Description'], authorities: ['Name'], crl: ['Name'] })
    await open(page, LISTS[1])
    const certs = page.locator('#ca-list-scroll thead th').filter({ hasText: 'Certificates' })
    expect(await certs.evaluate((th) => [getComputedStyle(th).textAlign, getComputedStyle(th).fontVariantNumeric])).toEqual(['right', 'tabular-nums'])
    const index = await certs.evaluate((th) => [...th.parentElement!.children].indexOf(th))
    const cell = page.locator(`#ca-list-scroll tbody tr:first-child td:nth-child(${index + 1})`)
    expect(await cell.evaluate((td) => getComputedStyle(td).textAlign)).toBe('right')
    // The checkbox of the certificates is 40 px wide (D2)
    await open(page, LISTS[0])
    expect(Math.round(await page.locator('#cert-scroll thead th:first-child').evaluate((th) => th.getBoundingClientRect().width))).toBe(40)
  })

  test('no ceiling: a long name and a long issuer stay whole while the sum fits (R1); a number keeps 28 px from a date (G10)', async ({ page, api }) => {
    // An issuer wider than the former ceiling of 280 px
    const ca = await createCA(api, { commonName: `Issuing Authority West ${uid('ca')}` })
    // 58 characters (a CN has 64 at most), wider than the former ceiling of 360 px
    const cn = `${uid('long-service-name-west')}.internal.example.com`
    await issueCert(api, ca.id, { cn })
    await open(page, LISTS[0])
    await page.getByRole('main').getByRole('searchbox').fill(cn)
    await expect(page.locator('#cert-scroll tbody tr')).toHaveCount(1)
    const cut = () => page.locator('#cert-scroll tbody').evaluate((tbody) => [...tbody.querySelectorAll('td.text-cell, .entity-label')]
      .filter((el) => el.scrollWidth > el.clientWidth + 1).map((el) => el.textContent))
    await expect.poll(cut).toEqual([])
    await open(page, LISTS[1])
    const certs = page.locator('#ca-list-scroll thead th.num')
    expect(await certs.locator('button').evaluate((b) => getComputedStyle(b).paddingRight)).toBe('28px')
    expect(await page.locator('#ca-list-scroll tbody tr:first-child td.num').evaluate((td) => getComputedStyle(td).paddingRight)).toBe('28px')
  })
})

test.describe('row actions under 1250 px', () => {
  test.use({ viewport: { width: 1100, height: 900 } })

  test('a module list keeps its first action and its chevron; only the certificates\' Export gives way', async ({ page, api }) => {
    const ca = await createCA(api)
    await issueCert(api, ca.id)
    await open(page, LISTS[1])
    const download = page.locator('#ca-list-scroll tbody tr .table-actions .icon-btn:first-child').first()
    await expect(download).toBeVisible()
    await open(page, LISTS[0])
    const actions = page.locator('#cert-scroll tbody tr').first().locator('.table-actions')
    await expect(actions.locator('[data-spare]')).toBeHidden()
    await expect(actions.locator('button[data-open]')).toBeVisible()
  })
})

// The contrast of two colours as WCAG computes it, from rgb() or color(srgb …)
function contrast(a: string, b: string) {
  const parse = (c: string) => {
    const srgb = c.match(/color\(srgb ([\d.]+) ([\d.]+) ([\d.]+)/)
    if (srgb) return srgb.slice(1, 4).map(Number)
    return c.match(/[\d.]+/g)!.slice(0, 3).map((v) => Number(v) / 255)
  }
  const lum = (c: string) => parse(c).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4))
    .reduce((s, v, i) => s + v * [0.2126, 0.7152, 0.0722][i], 0)
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p)
  return (x + 0.05) / (y + 0.05)
}

// The most contrasted pixel of each icon and how many pixels reach 3:1, against the header's own pixel above it, read
// on a screenshot at scale 1: what a screen paints, not the colour computed (R3). The icons are measured before and
// after the screenshot: a list that lays out again meanwhile (another test's authority arriving) is shot again.
async function painted(page, selector: string) {
  const measure = () => page.locator(selector).evaluateAll((all) => all.map((svg) => {
    const r = svg.getBoundingClientRect()
    return { x: r.x, y: r.y, width: r.width, height: r.height, top: svg.closest('th')!.getBoundingClientRect().top }
  }))
  let boxes = await measure()
  let shot = ''
  for (let i = 0; i < 10; i += 1) {
    shot = (await page.screenshot({ scale: 'css' })).toString('base64')
    const after = await measure()
    if (JSON.stringify(after) === JSON.stringify(boxes)) break
    boxes = after
    shot = ''
  }
  expect(shot, 'the header held still for a screenshot').not.toBe('')
  return page.evaluate(async ({ b64, boxes: bs }) => {
    const img = new Image()
    img.src = `data:image/png;base64,${b64}`
    await img.decode()
    const cv = document.createElement('canvas')
    cv.width = img.width
    cv.height = img.height
    const cx = cv.getContext('2d', { willReadFrequently: true })!
    cx.drawImage(img, 0, 0)
    const at = (x: number, y: number) => [...cx.getImageData(x, y, 1, 1).data].slice(0, 3)
    const lum = (c: number[]) => c.map((v) => v / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4))
      .reduce((s, v, i) => s + v * [0.2126, 0.7152, 0.0722][i], 0)
    const ratio = (a: number[], b: number[]) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05) }
    return bs.map((b) => {
      const bg = at(Math.round(b.x + b.width / 2), Math.round(b.top + 2))
      let max = 0
      let strong = 0
      for (let x = Math.floor(b.x); x <= Math.ceil(b.x + b.width); x += 1) {
        for (let y = Math.floor(b.y); y <= Math.ceil(b.y + b.height); y += 1) {
          const r = ratio(at(x, y), bg)
          max = Math.max(max, r)
          if (r >= 3) strong += 1
        }
      }
      return { max, strong, bg, box: [b.x, b.y, b.width, b.height].map(Math.round) }
    })
  }, { b64: shot, boxes })
}

test.describe('the headers in the four themes', () => {
  test.use({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 1 })

  for (const [family, mode] of [['atelier', 'dark'], ['atelier', 'light'], ['aurore', 'dark'], ['aurore', 'light']]) {
    test(`${family} ${mode}: separators read at 3:1, sort signs painted at 3:1, the sorted arrow at 4.5:1`, async ({ page, api }) => {
      await createCA(api)
      await open(page, LISTS[2])
      await page.evaluate(([f, m]) => { document.documentElement.setAttribute('data-theme', f); document.documentElement.setAttribute('data-mode', m) }, [family, mode])
      await page.mouse.move(0, 0)
      const read = await page.locator('#module-scroll thead').evaluate((thead) => {
        const bg = (el: Element | null): string => {
          for (; el; el = el.parentElement) {
            const c = getComputedStyle(el).backgroundColor
            if (c && c !== 'rgba(0, 0, 0, 0)' && c !== 'transparent') return c
          }
          return 'rgb(0, 0, 0)'
        }
        const ths = [...thead.querySelectorAll('th')]
        const seps = ths.map((th) => th.querySelector(':scope > .col-sep')).filter(Boolean) as Element[]
        const before = seps.map((s) => getComputedStyle(s, '::before'))
        return {
          data: ths.filter((th) => !th.querySelector('.sr-only')).length,
          seps: before.map((b) => [b.width, b.height, b.backgroundColor]),
          background: bg(ths[0]),
          idle: [...thead.querySelectorAll('svg.sort-idle')].map((s) => getComputedStyle(s).color),
          sorted: [...thead.querySelectorAll('th[aria-sort=ascending] svg, th[aria-sort=descending] svg')].map((s) => getComputedStyle(s).color),
          sortable: thead.querySelectorAll('th button[data-sort]').length,
        }
      })
      // A separator between two data headers: all but the last
      expect(read.seps).toHaveLength(read.data - 1)
      for (const [w, h, color] of read.seps) {
        expect([w, h]).toEqual(['1px', '16px'])
        expect(contrast(color, read.background)).toBeGreaterThanOrEqual(3)
      }
      expect(read.idle).toHaveLength(read.sortable - 1)
      expect(read.sorted).toHaveLength(1)
      expect(contrast(read.sorted[0], read.background)).toBeGreaterThanOrEqual(4.5)
      // As painted: each sign has at least 6 pixels at 3:1, the arrow a pixel at 4.5:1
      const idle = await painted(page, '#module-scroll thead svg.sort-idle')
      for (const p of idle) {
        expect(p.strong, JSON.stringify(p)).toBeGreaterThanOrEqual(6)
        expect(p.max, JSON.stringify(p)).toBeGreaterThanOrEqual(3)
      }
      const [arrow] = await painted(page, '#module-scroll thead th[aria-sort] svg.sort-arrow')
      expect(arrow.max).toBeGreaterThanOrEqual(4.5)
    })
  }
})

test.describe('the sort', () => {
  test.use({ viewport: { width: 1600, height: 1000 } })

  test('sorts from the keyboard, keeps the sort in the address and after a reload', async ({ page, api }) => {
    // Two authorities with a published CRL each: their publication dates are what the sort reads
    for (const ca of [await createCA(api), await createCA(api)]) {
      await api.post(`/crl/${ca.id}/regenerate`)
      await expect.poll(async () => (await api.get(`/crl/${ca.id}`))?.crl_number).toBeGreaterThan(0)
    }
    await open(page, LISTS[2])
    const head = (name: string) => page.locator('#module-scroll thead th').filter({ hasText: name })
    await expect(head('Next Update')).toHaveAttribute('aria-sort', 'ascending')
    const button = head('Published').getByRole('button')
    await button.focus()
    await page.keyboard.press('Enter')
    await expect(head('Published')).toHaveAttribute('aria-sort', 'ascending')
    await expect(button).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(head('Published')).toHaveAttribute('aria-sort', 'descending')
    await expect(page).toHaveURL(/[?&]sort=published&order=desc/)
    // The same order after a reload, read on the dates themselves: authorities other tests create meanwhile may come in
    await page.reload()
    await expect(head('Published')).toHaveAttribute('aria-sort', 'descending')
    await expect(page.locator('#module-scroll tbody tr .entity-name').first()).toBeVisible()
    const dates = await page.locator('#module-scroll').evaluate((el) => {
      const at = [...el.querySelectorAll('thead th')].findIndex((th) => th.textContent === 'Published')
      return [...el.querySelectorAll('tbody tr')].map((tr) => Date.parse(tr.children[at].textContent || ''))
    })
    const known = dates.filter((d) => !Number.isNaN(d))
    expect(known.length).toBeGreaterThan(1)
    expect(known).toEqual([...known].sort((x, y) => y - x))
    // An authority without a CRL comes last
    expect(dates.slice(0, known.length).every((d) => !Number.isNaN(d))).toBe(true)
    // The change is said to a screen reader
    await head('Name').getByRole('button').click()
    await expect(page.locator('.atl .table-container [aria-live=polite]')).toHaveText('Sorted by Name, ascending order')
  })
})

test.describe('the sort button and the sorted column', () => {
  test.use({ viewport: { width: 1600, height: 1000 } })

  test('fills its cell, answers the pointer and the keyboard, says what a click does; the sorted label in weight 600', async ({ page, api }) => {
    await createCA(api)
    await open(page, LISTS[2])
    const head = (name: string) => page.locator('#module-scroll thead th').filter({ hasText: name })
    // The button is the cell (R4): same box, and a click at the cell's right sorts
    const boxes = await page.locator('#module-scroll thead th:has(> button[data-sort])').evaluateAll((ths) => ths.map((th) => {
      const a = th.getBoundingClientRect()
      const b = th.querySelector(':scope > button')!.getBoundingClientRect()
      return [Math.round(a.left - b.left), Math.round(a.right - b.right), Math.round(a.height - b.height)]
    }))
    expect(boxes.length).toBeGreaterThan(3)
    for (const d of boxes) expect(d.map(Math.abs).every((v) => v <= 1)).toBe(true)
    await expect(head('Published').getByRole('button')).toHaveAttribute('title', 'Sort by Published')
    await expect(head('Next Update').getByRole('button')).toHaveAttribute('title', 'Sorted by Next Update, ascending order. Click to reverse')
    // The sorted column in weight 600 (R5), the others 400
    expect(await head('Next Update').evaluate((th) => getComputedStyle(th.querySelector('button')!).fontWeight)).toBe('600')
    expect(await head('Published').evaluate((th) => getComputedStyle(th.querySelector('button')!).fontWeight)).toBe('400')
    // Hover turns the label and its sign to the text colour, the sorted column's
    const text = await head('Next Update').evaluate((th) => getComputedStyle(th).color)
    const colours = () => head('Published').evaluate((th) => [getComputedStyle(th.querySelector('button')!).color, getComputedStyle(th.querySelector('svg')!).color])
    expect((await colours())[0]).not.toBe(text)
    await head('Published').hover({ position: { x: 20, y: 17 } })
    expect(await colours()).toEqual([text, text])
    // The keyboard's ring stays inside the 34 px header (G7); Tab passes the column's handle (C2) before the next header
    await page.mouse.move(0, 0)
    await head('Name').getByRole('button').focus()
    await page.keyboard.press('Tab')
    expect(await page.evaluate(() => document.activeElement!.getAttribute('role'))).toBe('separator')
    await page.keyboard.press('Tab')
    const ring = await page.evaluate(() => { const b = document.activeElement as HTMLElement; return [b.matches(':focus-visible'), getComputedStyle(b).outlineOffset, b.closest('th') !== null] })
    expect(ring).toEqual([true, '-2px', true])
    const cell = (await head('Published').boundingBox())!
    await page.mouse.click(cell.x + cell.width - 16, cell.y + cell.height / 2)
    await expect(head('Published')).toHaveAttribute('aria-sort', 'ascending')
  })
})

test.describe('the open row and a selection', () => {
  test.use({ viewport: { width: 1000, height: 800 } })

  test('the open row brought back into view stops under the sticky header (G6)', async ({ page, api }) => {
    for (let i = 0; i < 14; i += 1) await createCA(api)
    await open(page, LISTS[2])
    await page.locator('#module-scroll tbody tr').nth(1).locator('button.entity-name').click()
    await expect(page.locator('#module-scroll tbody tr.opened')).toHaveCount(1)
    const region = page.locator('#module-scroll')
    // Scrolled until the open row is above the region, then the window narrows: the list brings it back
    await region.evaluate((el) => { el.scrollTop = el.scrollHeight })
    await page.setViewportSize({ width: 980, height: 800 })
    await expect.poll(() => region.evaluate((el) => {
      const row = el.querySelector('tbody tr.opened')!.getBoundingClientRect()
      const head = el.querySelector('thead')!.getBoundingClientRect()
      const box = el.getBoundingClientRect()
      return row.top >= head.bottom - 1 && row.bottom <= box.bottom + 1
    })).toBe(true)
  })

  test('while rows are ticked the names do not open but stay readable (R7)', async ({ page, api }) => {
    const ca = await createCA(api)
    await issueCert(api, ca.id)
    await issueCert(api, ca.id)
    await open(page, LISTS[0])
    await page.locator('#cert-scroll tbody tr').first().locator('input[type=checkbox]').check()
    const name = page.locator('#cert-scroll tbody tr').nth(1).locator('button.entity-name')
    await expect(name).toBeDisabled()
    expect(await name.evaluate((b) => [getComputedStyle(b).opacity, getComputedStyle(b).cursor])).toEqual(['1', 'default'])
  })
})

// The certificates read the dock at the right; the shared account's preference is never written
async function dockRight(page) {
  const right = { position: 'right', height: 278, width: 460 }
  await page.route('**/api/v2/account/preferences', async (route) => {
    if (route.request().method() !== 'GET') return route.fulfill({ status: 200, contentType: 'application/json', body: '{"data":{}}' })
    const response = await route.fetch()
    const body = await response.json()
    body.data = { ...(body.data || {}), inspector: right }
    return route.fulfill({ response, json: body })
  })
  await page.route('**/api/v2/auth/verify', async (route) => {
    const response = await route.fetch()
    const body = await response.json()
    if (body?.data) body.data.preferences = { ...(body.data.preferences || {}), inspector: right }
    return route.fulfill({ response, json: body })
  })
}

test.describe('the column handles (C2)', () => {
  test.use({ viewport: { width: 1600, height: 1000 } })

  test('drag, keyboard, double-click, kept after a reload, reset from the footer; never a sideways scroll', async ({ page, api }) => {
    await createCA(api)
    // The widths follow the rows: read once, as other tests create authorities, and measured once laid out
    await freezeApi(page)
    await open(page, LISTS[2])
    await expect(page.locator('#module-scroll tbody tr.sk-row')).toHaveCount(0)
    await expect(page.locator('#module-scroll table.measuring')).toHaveCount(0)
    // The second data column, a fitted one: the name absorbs the room left
    const th = page.locator('#module-scroll thead th:has(> [role=separator])').nth(1)
    const grip = th.locator(':scope > [role=separator]')
    const width = () => th.evaluate((el) => Math.round(el.getBoundingClientRect().width))
    const near = (expected: number) => async () => Math.abs((await width()) - expected) <= 1
    const auto = await width()
    // The handle is the separator: the same 1 by 16 line at rest, 12 px to grab, the accent across the header on hover
    const line = () => grip.evaluate((g) => { const b = getComputedStyle(g, '::before'); return [b.width, b.height] })
    expect(await line()).toEqual(['1px', '16px'])
    const box = (await grip.boundingBox())!
    expect(Math.round(box.width)).toBe(12)
    expect(await grip.evaluate((g) => getComputedStyle(g).cursor)).toBe('col-resize')
    // The pointer is brought onto the handle where it is drawn now
    await expect.poll(async () => {
      const at = (await grip.boundingBox())!
      await page.mouse.move(at.x + 6, at.y + at.height / 2)
      return line()
    }).toEqual(['2px', `${Math.round(box.height)}px`])

    // Drag 80 px to the right
    const drag = async (dx: number) => {
      const b = (await grip.boundingBox())!
      await page.mouse.move(b.x + 6, b.y + b.height / 2)
      await page.mouse.down()
      await page.mouse.move(b.x + 6 + dx / 2, b.y + b.height / 2, { steps: 4 })
      await page.mouse.move(b.x + 6 + dx, b.y + b.height / 2, { steps: 4 })
      await page.mouse.up()
    }
    await drag(80)
    await expect.poll(near(auto + 80)).toBe(true)
    const g = await geometry(page, '#module-scroll')
    expect([g.over <= 1, g.page <= 0]).toEqual([true, true])
    // Kept after a reload, under the list's own key
    await page.reload()
    await expect(page.locator('#module-scroll tbody tr').first()).toBeVisible()
    await expect.poll(near(auto + 80)).toBe(true)

    // The keyboard: 16 px a step, 64 with Shift, Escape gives the width back, Enter keeps; the accent while focused
    await page.mouse.move(0, 0)
    await grip.focus()
    await page.keyboard.press('ArrowRight')
    await expect.poll(near(auto + 96)).toBe(true)
    await expect(grip).toHaveAttribute('aria-valuenow', String(auto + 96))
    expect((await line())[0]).toBe('2px')
    await page.keyboard.press('Shift+ArrowRight')
    await expect.poll(near(auto + 160)).toBe(true)
    await page.keyboard.press('Escape')
    await expect.poll(near(auto + 80)).toBe(true)
    await page.keyboard.press('ArrowLeft')
    await page.keyboard.press('Enter')
    await expect.poll(near(auto + 64)).toBe(true)

    // A double-click gives the column its automatic width back
    await page.mouse.move(0, 0)
    await grip.dblclick()
    await expect.poll(near(auto)).toBe(true)
    await expect(page.locator('.atl .table-footer [data-action=reset-columns]')).toHaveCount(0)

    // Réinitialiser les colonnes, in the footer while a width is set, clears them all
    await drag(60)
    await expect.poll(near(auto + 60)).toBe(true)
    await page.locator('.atl .table-footer [data-action=reset-columns]').click()
    await expect.poll(near(auto)).toBe(true)
    await expect(page.locator('.atl .table-footer [data-action=reset-columns]')).toHaveCount(0)
    expect(await page.evaluate(() => Object.keys(localStorage).filter((k) => k.startsWith('ucm-widths:')))).toEqual([])

    // A widened column never makes the list scroll sideways, at any desktop width
    await drag(300)
    for (const w of [1280, 1000]) {
      await page.setViewportSize({ width: w, height: 900 })
      await expect.poll(() => geometry(page, '#module-scroll').then((r) => r.over)).toBeLessThanOrEqual(1)
      expect((await geometry(page, '#module-scroll')).page).toBeLessThanOrEqual(0)
    }
  })

  test('beside the dock, a widened issuer keeps its width while other columns fold first; the Columns dialog resets it', async ({ page, api }) => {
    const ca = await createCA(api, { commonName: `Production Intermediate Authority ${uid('ca')}` })
    const cert = await issueCert(api, ca.id)
    await page.setViewportSize({ width: 1406, height: 809 })
    await dockRight(page)
    await page.goto('/certificates')
    await page.getByRole('main').getByRole('searchbox').fill(cert.common_name)
    await expect(page.locator('#cert-scroll tbody tr')).toHaveCount(1)
    await page.getByRole('main').getByRole('button', { name: cert.common_name, exact: true }).click()
    await expect(page.locator('.atl #app')).toHaveClass(/dock-right/)
    const folded = async () => {
      const note = page.locator('.atl .table-footer .folded-note')
      return (await note.count()) ? (await note.getAttribute('title'))!.split(', ') : []
    }
    const before = await folded()
    const issuer = page.locator('#cert-scroll thead th.col-ca')
    await page.evaluate(() => localStorage.setItem('ucm-certs-table-widths', JSON.stringify({ ca: 320 })))
    await page.reload()
    await expect(page.locator('.atl #app')).toHaveClass(/dock-right/)
    await expect(page.locator('#cert-scroll tbody tr').first()).toBeVisible()
    await expect.poll(() => issuer.evaluate((el) => Math.round(el.getBoundingClientRect().width))).toBe(320)
    // The columns that folded without it are still folded, more may be, never the issuer
    const after = await folded()
    expect(after).toEqual(expect.arrayContaining(before))
    expect(after.length).toBeGreaterThanOrEqual(before.length)
    const g = await geometry(page, '#cert-scroll')
    expect([g.over <= 1, g.page <= 0, g.lost]).toEqual([true, true, 0])
    // The Columns dialog of the certificates resets the widths and the hidden columns
    await page.getByRole('main').getByRole('button', { name: 'Columns', exact: true }).click()
    await page.getByRole('dialog').getByRole('button', { name: 'Reset columns' }).click()
    await expect.poll(() => issuer.evaluate((el) => Math.round(el.getBoundingClientRect().width))).not.toBe(320)
    expect(await page.evaluate(() => localStorage.getItem('ucm-certs-table-widths'))).toBeNull()
  })
})

test.describe('on a phone', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('every record keeps its chevron on screen; the toolbar sorts the records', async ({ page, api }) => {
    // One authority with a CRL: the nearest next update comes first, the authorities without one last
    const ca = await createCA(api)
    await api.post(`/crl/${ca.id}/regenerate`)
    await expect.poll(async () => (await api.get(`/crl/${ca.id}`))?.crl_number).toBeGreaterThan(0)
    await createCA(api)
    await page.goto('/crl-ocsp')
    const records = page.locator('.atl .mobile-list article.mobile-record.opens')
    await expect(records.first()).toBeVisible()
    for (const chevron of await records.locator('.row-top > button.icon-btn').all()) {
      const box = await chevron.boundingBox()
      expect(box!.x + box!.width).toBeLessThanOrEqual(390)
    }
    // A date after its column's label, no fact reduced to a dash
    const facts = await records.locator('.row-meta > span').allTextContents()
    expect(facts.filter((f) => f.trim() === '—')).toEqual([])
    // A record names the column in full, as its title does (E6)
    expect(await records.first().locator('.row-meta > span').first().textContent()).toMatch(/^Next Update \S/)
    // The fact's label is muted beside its value (G9)
    const fact = records.first().locator('.row-meta > span').first()
    expect(await fact.evaluate((s) => getComputedStyle(s).color)).not.toBe(await fact.locator('.fact-label').evaluate((l) => getComputedStyle(l).color))
    const select = page.getByRole('combobox', { name: 'Sort by' })
    await expect(select).toHaveValue('next')
    await select.selectOption('name')
    // The sort goes through the address: the records are read once it has applied
    const byName = async () => {
      const names = await records.locator('.entity-name').allTextContents()
      return names.join('|') === [...names].sort((a, b) => a.localeCompare(b, 'en', { sensitivity: 'base', numeric: true })).join('|')
    }
    await expect.poll(byName).toBe(true)
    // The reverse button shows the direction and says it (G8)
    await page.getByRole('button', { name: 'Ascending order, reverse' }).click()
    await expect(page).toHaveURL(/sort=name&order=desc/)
    await expect(page.getByRole('button', { name: 'Descending order, reverse' })).toBeVisible()
  })
})
