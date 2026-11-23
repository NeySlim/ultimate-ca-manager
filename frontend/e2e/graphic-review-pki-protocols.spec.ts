import { test, expect, createCA, issueCert, uid } from './support/fixtures'
import type { Page } from '@playwright/test'

// The graphic review's layout defects of the PKI and protocol pages, measured on a phone: the head's other actions
// reachable from a menu, the EAB setting kept in view, the ACME proxy card no wider than its neighbours
const UPSTREAM = [
  { id: 1, label: "Let's Encrypt", directory_url: 'https://acme-v02.api.letsencrypt.org/directory', email: 'pki-operations@example-corporation.com',
    is_default: true, is_registered: true, proxy_enabled: true, proxy_slug: 'letsencrypt' },
]
const CLIENT_SETTINGS = {
  proxy_acme_account_id: 1, proxy_account_url: 'https://acme-v02.api.letsencrypt.org/acme/acct/290352504290352504290352504', proxy_verify_ssl: true,
}

async function feedProxy(page: Page) {
  await page.route('**/api/v2/acme/client/**', async (route) => {
    const url = new URL(route.request().url())
    if (route.request().method() !== 'GET') return route.continue()
    if (url.pathname === '/api/v2/acme/client/accounts') return route.fulfill({ json: { data: UPSTREAM } })
    if (url.pathname === '/api/v2/acme/client/settings') {
      const response = await route.fetch()
      const body = await response.json()
      body.data = { ...(body.data || {}), ...CLIENT_SETTINGS }
      return route.fulfill({ response, json: body })
    }
    return route.continue()
  })
}

test.describe('phone', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  for (const [path, name] of [['/certificates', 'Import'], ['/ssh/cas', 'Import'], ['/ssh/certificates', 'Import']]) {
    test(`${path}: the head's other actions are in a menu, not lost`, async ({ page, api }) => {
      await page.goto(path)
      const head = page.locator('.page-head')
      await expect(head.locator('.btn.primary')).toBeVisible()
      const more = head.locator('[data-action="page-actions"]')
      await expect(more).toBeVisible()
      await more.click()
      await expect(page.getByRole('dialog').getByRole('button', { name, exact: true })).toBeVisible()
    })
  }

  test('ACME EAB: the « require EAB » box stays on the page', async ({ page, api }) => {
    await page.goto('/acme?tab=eab')
    const box = page.locator('label.eab-required')
    await expect(box).toBeVisible()
    const b = await box.boundingBox()
    expect(b!.width).toBeGreaterThan(40)
    expect(b!.x + b!.width).toBeLessThanOrEqual(390)
  })

  test('ACME client: the proxy card is no wider than the page, its URLs and lists whole', async ({ page, api }) => {
    await feedProxy(page)
    await page.goto('/acme?tab=letsencrypt')
    const card = page.locator('#set-sec-proxy')
    await card.scrollIntoViewIfNeeded()
    await expect(card.locator('.acme-proxy')).toBeVisible()
    const widths = await page.locator('.settings-section').evaluateAll((els) => els.map((el) => Math.round(el.getBoundingClientRect().width)))
    const proxy = await card.evaluate((el) => Math.round(el.getBoundingClientRect().width))
    expect(proxy).toBeLessThanOrEqual(Math.min(...widths))
    // Nothing inside runs past the card's padding box
    const overflow = await card.evaluate((el) => {
      const right = el.getBoundingClientRect().right
      return [...el.querySelectorAll('select, .code-value, .notice, pre, .btn')].filter((n) => n.getBoundingClientRect().right > right + 0.5).length
    })
    expect(overflow).toBe(0)
  })
})

// A separator never starts a line: each « · » sits on the line of the character before it
async function separatorsStartingALine(page: Page, selector: string) {
  return page.locator(selector).evaluateAll((els) => els.flatMap((el) => {
    const found: string[] = []
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT)
    let prev: DOMRect | null = null
    for (let n = walker.nextNode() as Text | null; n; n = walker.nextNode() as Text | null) {
      for (let i = 0; i < n.data.length; i++) {
        if (/\s|\u2060/.test(n.data[i])) continue
        const r = document.createRange()
        r.setStart(n, i)
        r.setEnd(n, i + 1)
        const rect = r.getBoundingClientRect()
        if (!rect.width) continue
        if (n.data[i] === '·' && prev && rect.top > prev.top + 4) found.push((el.textContent || '').trim())
        prev = rect
      }
    }
    return found
  }))
}

test.describe('phone, PKI', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('overview: no metric line starts with its separator', async ({ page, api }) => {
    const ca = await createCA(api)
    await issueCert(api, ca.id)
    // Critical entries in the queue: its figure reads « N critical · N to do · N to watch »
    await page.route('**/api/v2/dashboard/queue**', (route) => route.fulfill({ json: { data: {
      total: 20, counts: { manual_renewal_due: 16, ca_expiring: 4 },
      items: Array.from({ length: 10 }, (_, i) => ({ kind: 'ca_expiring', tier: 'critical', id: 900 + i, label: `CA ${i}`, due_at: null, href_hint: '/cas' })),
    } } }))
    await page.goto('/')
    await expect(page.locator('.metric-strip [data-metric="queue"] small')).toContainText('critical')
    await expect(page.locator('.metric-strip .metric').first()).toBeVisible()
    await expect(page.locator('.metric-strip small').first()).not.toBeEmpty()
    expect(await separatorsStartingALine(page, '.metric-strip .metric')).toEqual([])
  })

  test('authorities: a CA line keeps its count and its date together', async ({ page, api }) => {
    await createCA(api, { commonName: uid('a-root-with-a-rather-long-common-name') })
    await page.goto('/cas')
    const ends = page.locator('.ca-line .ca-line-end')
    await expect(ends.first()).toBeVisible()
    const lines = await ends.evaluateAll((els) => els.map((el) => {
      const tops = [...el.children].map((c) => Math.round(c.getBoundingClientRect().top))
      return Math.max(...tops) - Math.min(...tops)
    }))
    expect(lines.every((d) => d <= 2)).toBe(true)
  })
})

test.describe('desktop, PKI and protocols', () => {
  test.use({ viewport: { width: 1600, height: 1000 } })

  test('overview: the hierarchy\'s roots stack in columns, without a hole under a short one', async ({ page, api }) => {
    const root = await createCA(api)
    await createCA(api, { parentCAId: root.id })
    await createCA(api)
    await createCA(api)
    await page.goto('/')
    const trees = page.locator('.hier-columns > .hier-tree')
    await expect(trees.nth(1)).toBeVisible()
    const gaps = await trees.evaluateAll((els) => {
      const boxes = els.map((e) => e.getBoundingClientRect())
      const out: number[] = []
      boxes.forEach((b, i) => {
        // The tree just above in the same column: the gap between them is the column's own spacing
        const above = boxes.filter((o, j) => j !== i && Math.abs(o.left - b.left) < 2 && o.bottom <= b.top + 1)
          .sort((x, y) => y.bottom - x.bottom)[0]
        if (above) out.push(Math.round(b.top - above.bottom))
      })
      return out
    })
    expect(gaps.every((g) => g <= 16)).toBe(true)
  })

  test('ACME: the filters rows have one height, with counters, without, or with the EAB setting', async ({ page, api }) => {
    expect(api).toBeTruthy()
    const heights: number[] = []
    for (const tab of ['accounts', 'history', 'eab']) {
      await page.goto(`/acme?tab=${tab}`)
      const row = page.locator('.filters-row').first()
      await expect(row).toBeVisible()
      heights.push(Math.round((await row.boundingBox())!.height))
    }
    expect(new Set(heights).size).toBe(1)
  })
})

test.describe('wide screen', () => {
  test.use({ viewport: { width: 3440, height: 1300 } })

  test('a detached certificate opens in the free margin right of the page, clear of its title and names', async ({ page, api }) => {
    const ca = await createCA(api)
    const cert = await issueCert(api, ca.id, { cn: `${uid('right')}.example.com` })
    await page.goto('/certificates')
    await page.getByRole('main').getByRole('searchbox').fill(cert.common_name)
    await page.getByRole('main').getByRole('button', { name: cert.common_name, exact: true }).click()
    await page.locator('#inspector').getByRole('button', { name: 'Detach into a window' }).click()
    const win = page.getByRole('dialog', { name: cert.common_name })
    await expect(win).toBeVisible()
    const w = (await win.boundingBox())!
    const head = (await page.locator('.page-head').first().boundingBox())!
    expect(w.x).toBeGreaterThanOrEqual(head.x + head.width)
    expect(w.x + w.width).toBeLessThanOrEqual(3440)
  })
})
