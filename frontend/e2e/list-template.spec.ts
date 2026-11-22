import { test, expect, createCA, issueCert, uid } from './support/fixtures'

// The list template measured where jsdom cannot (COLONNES-SPEC G1, G2): on Certificates, the authorities' list
// and CRL / OCSP, no horizontal scroll at any desktop width, the chevron always in view, the folded columns said
// in the footer, one column taking the room left, numbers at the right, header separators and sort signs readable
// in the four themes, the sort from the keyboard and kept by a reload, the phone's sort and records.

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

test.describe('the headers in the four themes', () => {
  test.use({ viewport: { width: 1600, height: 1000 } })

  for (const [family, mode] of [['atelier', 'dark'], ['atelier', 'light'], ['aurore', 'dark'], ['aurore', 'light']]) {
    test(`${family} ${mode}: separators and sort signs read at 3:1, the sorted arrow at 4.5:1`, async ({ page, api }) => {
      await createCA(api)
      await open(page, LISTS[2])
      await page.evaluate(([f, m]) => { document.documentElement.setAttribute('data-theme', f); document.documentElement.setAttribute('data-mode', m) }, [family, mode])
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
      for (const c of read.idle) expect(contrast(c, read.background)).toBeGreaterThanOrEqual(3)
      expect(read.sorted).toHaveLength(1)
      expect(contrast(read.sorted[0], read.background)).toBeGreaterThanOrEqual(4.5)
    })
  }
})

test.describe('the sort', () => {
  test.use({ viewport: { width: 1600, height: 1000 } })

  test('sorts from the keyboard, keeps the sort in the address and after a reload', async ({ page, api }) => {
    await createCA(api)
    await createCA(api)
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
    const first = await page.locator('#module-scroll tbody tr:first-child .entity-name').textContent()
    await page.reload()
    await expect(head('Published')).toHaveAttribute('aria-sort', 'descending')
    await expect(page.locator('#module-scroll tbody tr:first-child .entity-name')).toHaveText(first!)
    // The change is said to a screen reader
    await head('Name').getByRole('button').click()
    await expect(page.locator('.atl .table-container [aria-live=polite]')).toHaveText('Sorted by Name, ascending order')
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
    expect(await records.first().locator('.row-meta > span').first().textContent()).toMatch(/^Next Update \S/)
    const select = page.getByRole('combobox', { name: 'Sort by' })
    await expect(select).toHaveValue('next')
    await select.selectOption('name')
    const names = await records.locator('.entity-name').allTextContents()
    expect(names).toEqual([...names].sort((a, b) => a.localeCompare(b, 'en', { sensitivity: 'base', numeric: true })))
    await page.getByRole('button', { name: 'Reverse the order' }).click()
    await expect(page).toHaveURL(/sort=name&order=desc/)
  })
})
