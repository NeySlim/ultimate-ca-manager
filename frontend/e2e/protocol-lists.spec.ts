import { test, expect, createCA, type Api } from './support/fixtures'
import type { Page } from '@playwright/test'

// The protocol lists (ACME, SCEP, EST, TSA, CRL / OCSP) measured on the list template: at
// 1600, 1406 with the dock on the right, 1280, 1000 and 390 px, no list scrolls sideways, every chevron stays in view,
// no header is clipped, no fit cell is cut, a cut text keeps its whole value in a title, one column takes the room left
// (the name, or a free text that is long), one column is sorted from the first render, a short header stays near its
// values; on a phone every record keeps its chevron and names its dates. The lists are fed by routing the rows the
// review measured (long account URLs, long names), so the geometry does not depend on what other tests create.

const DAY = 864e5
const at = (days: number) => new Date(Date.UTC(2026, 10, 1) + days * DAY).toISOString()
const hex = (n: number, len = 32) => Array.from({ length: len }, (_, i) => ((n * 7 + i * 13) % 16).toString(16)).join('')

const ACCOUNTS = Array.from({ length: 25 }, (_, i) => ({
  id: i + 1, account_id: `${hex(i, 22)}`, contact: [`mailto:operations-team-${i + 1}@example-corporation.com`],
  status: i % 5 ? 'valid' : 'deactivated', orders_count: i % 4, key_type: 'EC-P256', created_at: at(-i),
}))
const LOCAL_ORDERS = Array.from({ length: 21 }, (_, i) => ({
  id: i + 1, order_id: hex(i, 16), domain: `host-${i + 1}.services.example.com`, account: `https://pki.example.com/acme/acct/${hex(i, 32)}`,
  status: ['Pending', 'Valid', 'Invalid'][i % 3], method: i % 2 ? 'HTTP-01' : 'DNS-01', expires: at(7 - i).slice(0, 10), created_at: at(-i),
}))
const HISTORY = Array.from({ length: 22 }, (_, i) => ({
  id: i + 1, common_name: `ACME Certificate - Order ${hex(i, 10)} for www-${i + 1}.example.com`, serial: hex(i, 20),
  issuer: i % 2 ? "Let's Encrypt R11 Intermediate Certification Authority" : 'Corporate ACME Issuing Authority for Services',
  source: ['acme', 'acme_client', 'letsencrypt'][i % 3], challenge_type: i % 2 ? 'http-01' : 'dns-01', revoked: i % 6 === 0,
  valid_from: at(-i - 1), valid_to: at(90 - i), created_at: at(-i), order: {},
}))
const EAB = Array.from({ length: 25 }, (_, i) => ({
  id: i + 1, kid: `kid-${hex(i, 22)}`, label: `Team credential ${i + 1}`, status: ['active', 'used', 'revoked'][i % 3],
  allowed_domains: i % 4 ? [`*.team-${i + 1}.example.com`, `api.team-${i + 1}.example.com`] : ['*'], created_at: at(-i), notes: null,
}))
const CLIENT_ORDERS = Array.from({ length: 10 }, (_, i) => ({
  id: i + 1, primary_domain: `portal-${i + 1}.example.org`, domains: [`portal-${i + 1}.example.org`], status: ['valid', 'pending', 'invalid'][i % 3],
  environment: i % 2 ? 'production' : 'staging', challenge_type: i % 2 ? 'http-01' : 'dns-01', created_at: at(-i),
  acme_client_account_label: i % 2 ? "Let's Encrypt Production" : 'ZeroSSL', renewal_failures: i === 3 ? 4 : 0,
}))
const UPSTREAM = [
  { id: 1, label: "Let's Encrypt", directory_url: 'https://acme-v02.api.letsencrypt.org/directory', email: 'pki-operations@example-corporation.com', is_default: true, is_registered: true, proxy_enabled: true, proxy_slug: 'letsencrypt' },
  { id: 2, label: 'ZeroSSL', directory_url: 'https://acme.zerossl.com/v2/DV90', email: 'pki-operations@example-corporation.com', is_default: false, is_registered: true },
  { id: 3, label: 'Actalis', directory_url: 'https://acme-api.actalis.com/acme/directory', email: 'pki-operations@example-corporation.com', is_default: false, is_registered: false },
]
const PROVIDERS = [
  { id: 1, name: 'Cloudflare production zone', provider_type: 'cloudflare', enabled: true, is_default: true, credential_keys: ['api_token'] },
  { id: 2, name: 'Route 53', provider_type: 'route53', enabled: true, credential_keys: [] },
]
const DOMAINS = [
  { id: 1, domain: '*.services.example.com', dns_provider_name: 'Cloudflare production zone', issuing_ca_name: 'Corporate Issuing CA', is_wildcard_allowed: true, auto_approve: true },
  { id: 2, domain: 'example.org', dns_provider_name: 'Route 53', issuing_ca_name: null, is_wildcard_allowed: false, auto_approve: false },
]
const LOCAL_DOMAINS = Array.from({ length: 4 }, (_, i) => ({
  id: i + 1, domain: `internal-${i + 1}.corp.example.com`, issuing_ca_name: 'Corporate Issuing CA', auto_approve: i % 2 === 0,
}))
const SCEP_PROFILES = [
  { id: 1, name: 'Network equipment', url_slug: 'network', ca_refid: 'r1', ca_name: 'Corporate Issuing CA', template_name: 'Network device', intune_enabled: false, enabled: true, challenge_set: true },
  { id: 2, name: 'Managed laptops', url_slug: 'mdm', ca_refid: 'r1', ca_name: 'Corporate Issuing CA', template_name: null, intune_enabled: true, enabled: false },
]
const SCEP_REQUESTS = Array.from({ length: 4 }, (_, i) => ({
  id: i + 1, subject: `CN=device-${1000 + i}.mdm.example.com,OU=MDM,O=Example`, transaction_id: hex(i, 32).toUpperCase(),
  status: ['pending', 'approved', 'rejected', 'approved'][i], created_at: at(-i), ca_refid: 'r1', profile_id: i % 2 ? 1 : null,
}))
const INTUNE = [
  { id: 1, name: 'Corporate tenant', tenant_id: '72f988bf-86f1-41af-91ab-2d7cd011db47', client_id: '0b5e1c3d-8f6a-4e2b-9d7c-1a2b3c4d5e6f', profile_count: 1, last_test_at: at(-2), last_test_result: 'ok' },
  { id: 2, name: 'Lab tenant', tenant_id: 'lab.onmicrosoft.com', client_id: '5f6e7d8c-9b0a-4c1d-8e2f-3a4b5c6d7e8f', profile_count: 0 },
]
const EST_CONFIG = {
  enabled: true, ca_id: null, ca_name: 'Corporate Issuing CA', validity_days: 365, username: 'est-client', password_set: true,
  labels: { iot: { ca_refid: 'r2', ca_name: 'IoT Devices Issuing Authority' }, routers: { ca_refid: 'r1', ca_name: 'Corporate Issuing CA' } },
}
const TSA_CONFIG = { enabled: true, ca_refid: 'r1', ca_name: 'Timestamping Authority', policy_oid: '1.3.6.1.4.1.55555.1', require_dedicated_cert: false, signer: { configured: false } }

// A listing the server pages (page, per_page) as it does, with its total
const paged = (rows: unknown[], url: URL, size: number) => {
  const page = Number(url.searchParams.get('page') || 1)
  const per = Number(url.searchParams.get('per_page') || size)
  return { data: rows.slice((page - 1) * per, page * per), meta: { total: rows.length, page, per_page: per } }
}
const FEEDS: [RegExp, (url: URL) => unknown][] = [
  [/^\/api\/v2\/acme\/accounts$/, (u) => paged(ACCOUNTS, u, 100)],
  [/^\/api\/v2\/acme\/orders$/, () => ({ data: { items: LOCAL_ORDERS, meta: { page: 1, per_page: 50, total: LOCAL_ORDERS.length } } })],
  [/^\/api\/v2\/acme\/history$/, () => ({ data: HISTORY, meta: { total: HISTORY.length, cas: [] } })],
  [/^\/api\/v2\/acme\/eab-credentials$/, (u) => paged(EAB, u, 200)],
  [/^\/api\/v2\/acme\/client\/orders$/, (u) => paged(CLIENT_ORDERS, u, 100)],
  [/^\/api\/v2\/acme\/client\/accounts$/, () => ({ data: UPSTREAM })],
  [/^\/api\/v2\/dns-providers$/, () => ({ data: PROVIDERS })],
  [/^\/api\/v2\/acme\/domains$/, () => ({ data: DOMAINS })],
  [/^\/api\/v2\/acme\/local-domains$/, () => ({ data: LOCAL_DOMAINS })],
  [/^\/api\/v2\/scep\/profiles$/, () => ({ data: SCEP_PROFILES })],
  [/^\/api\/v2\/scep\/requests$/, () => ({ data: SCEP_REQUESTS, meta: { total: SCEP_REQUESTS.length, page: 1, per_page: 25 } })],
  [/^\/api\/v2\/scep\/intune-apps$/, () => ({ data: INTUNE })],
  [/^\/api\/v2\/scep\/challenge\/\d+$/, () => ({ data: { challenge: 'a1b2c3d4e5f6' } })],
  [/^\/api\/v2\/est\/config$/, () => ({ data: EST_CONFIG })],
  [/^\/api\/v2\/tsa\/config$/, () => ({ data: TSA_CONFIG })],
]

// With `right`, the page alone reads the dock anchored at the right: the shared account's preference is never written
async function feed(page: Page, right = false) {
  const inspector = { position: 'right', height: 278, width: 460 }
  await page.route('**/api/v2/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (right && url.pathname === '/api/v2/account/preferences') {
      if (request.method() !== 'GET') return route.fulfill({ status: 200, contentType: 'application/json', body: '{"data":{}}' })
      const response = await route.fetch()
      const body = await response.json()
      body.data = { ...(body.data || {}), inspector }
      return route.fulfill({ response, json: body })
    }
    if (right && url.pathname === '/api/v2/auth/verify') {
      const response = await route.fetch()
      const body = await response.json()
      if (body?.data) body.data.preferences = { ...(body.data.preferences || {}), inspector }
      return route.fulfill({ response, json: body })
    }
    const hit = request.method() === 'GET' && FEEDS.find(([re]) => re.test(url.pathname))
    if (!hit) return route.continue()
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(hit[1](url)) })
  })
}

type List = { name: string, url: string, grows: string, sorted: string | null }
const LISTS: List[] = [
  { name: 'acme-accounts', url: '/acme', grows: 'Name', sorted: 'Created' },
  { name: 'acme-local-orders', url: '/acme?tab=localorders', grows: 'Name', sorted: 'Created' },
  { name: 'acme-local-domains', url: '/acme?tab=localdomains', grows: 'Name', sorted: 'Name' },
  { name: 'acme-eab', url: '/acme?tab=eab', grows: 'Allowed domains', sorted: 'Created' },
  { name: 'acme-client-orders', url: '/acme?tab=letsencryptorders', grows: 'Name', sorted: 'Created' },
  { name: 'acme-upstream', url: '/acme?tab=upstream', grows: 'ACME Directory URL', sorted: 'Name' },
  { name: 'acme-dns', url: '/acme?tab=dns', grows: 'Name', sorted: 'Name' },
  { name: 'acme-domains', url: '/acme?tab=domains', grows: 'Name', sorted: 'Name' },
  { name: 'acme-history', url: '/acme?tab=history', grows: 'Name', sorted: 'Issued' },
  { name: 'scep-profiles', url: '/scep-config', grows: 'Name', sorted: 'Name' },
  { name: 'scep-requests', url: '/scep-config?tab=requests', grows: 'Name', sorted: 'Requested' },
  { name: 'scep-challenges', url: '/scep-config?tab=challenges', grows: 'Subject', sorted: 'Name' },
  { name: 'scep-intune', url: '/scep-config?tab=intune', grows: 'Name', sorted: 'Name' },
  { name: 'est', url: '/est-config', grows: 'Name', sorted: 'Name' },
  { name: 'tsa', url: '/tsa-config', grows: 'Name', sorted: null },
  { name: 'crl-ocsp', url: '/crl-ocsp', grows: 'Name', sorted: 'Next update' },
]
const REGION = '#module-scroll'
// The CRL number reads « CRL number » over a fresh authority's one-digit number (the noun the phone's sort needs)
// The ACME accounts' order count reads « Commandes » in full: « Cdes » saved 11 px for a header nobody could read
const WIDE_HEADS: Record<string, RegExp> = { 'crl-ocsp': /^(CRL number|Numéro de CRL) /, 'acme-accounts': /^Commandes / }
const wide = (list: List, heads: string[]) => heads.filter((h) => !WIDE_HEADS[list.name]?.test(h))

async function open(page: Page, list: List) {
  await page.goto(list.url)
  await expect(page.locator(`${REGION} tbody tr .entity-name`).first()).toBeVisible()
}

// What the template must hold, read on the painted list
const measure = (page: Page) => page.locator(REGION).evaluate((el) => {
  const box = el.getBoundingClientRect()
  const ths = [...el.querySelectorAll('thead th')]
  const data = ths.map((th, i) => ({ th, i })).filter(({ th }) => !th.querySelector('.sr-only, input'))
  const rows = [...el.querySelectorAll('tbody tr')]
  const lost = rows.filter((tr) => tr.querySelector('[data-open]')).filter((tr) => {
    const chevron = [...tr.querySelectorAll('td:last-child button.icon-btn[data-open]')].pop()
    if (!chevron) return true
    const r = chevron.getBoundingClientRect()
    return !r.width || !r.height || r.left < box.left - 1 || r.right > box.right + 1
  }).length
  const width = (node: Node) => { const range = document.createRange(); range.selectNodeContents(node); return range.getBoundingClientRect().width }
  const fitCut: string[] = []
  const untitled: string[] = []
  const wideHeads: string[] = []
  for (const { th, i } of data) {
    const label = (th.querySelector('button') || th).textContent || ''
    const cells = rows.map((tr) => tr.children[i] as HTMLElement).filter(Boolean)
    // A fit or number column: neither the free text (text-cell) nor the name, which give way with an ellipsis
    const fixed = th.classList.contains('fit') && !cells.some((td) => td.matches('.text-cell, .description-cell') || td.querySelector('.entity-name'))
    if (fixed) {
      for (const td of cells) if (td.scrollWidth > td.clientWidth + 1) fitCut.push(`${label}: ${td.textContent}`)
      // A short header near its values: its label at most 48 px wider than the widest value
      const text = [...(th.querySelector('button') || th).childNodes].find((n) => n.nodeType === Node.TEXT_NODE)
      const head = text ? width(text) : 0
      const present = cells.filter((td) => (td.textContent || '').trim() !== '—')
      const widest = Math.max(0, ...present.map((td) => width(td)))
      if (present.length && head > widest + 48) wideHeads.push(`${label} ${Math.round(head)} > ${Math.round(widest)} + 48`)
    }
    // A cut text keeps its whole value in its title
    for (const td of cells) {
      const boxes = [td, ...td.querySelectorAll('.entity-label')] as HTMLElement[]
      for (const b of boxes) {
        if (b.scrollWidth <= b.clientWidth + 1) continue
        const title = b.getAttribute('title') || td.getAttribute('title') || ''
        if (!title || !title.includes((b.textContent || '').trim().slice(0, 20))) untitled.push(`${label}: ${b.textContent}`)
      }
    }
  }
  const cut = rows.flatMap((tr) => [...tr.querySelectorAll('td, .entity-label')]).filter((b) => (b as HTMLElement).scrollWidth > (b as HTMLElement).clientWidth + 1).length
  return {
    over: el.scrollWidth - el.clientWidth, page: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    rows: rows.length, lost, fitCut, untitled, wideHeads, cut,
    clipped: data.filter(({ th }) => th.scrollWidth > th.clientWidth + 1).map(({ th }) => th.textContent),
    grows: data.filter(({ th }) => !th.classList.contains('fit')).map(({ th }) => (th.querySelector('button') || th).textContent),
    sorted: data.filter(({ th }) => /ending$/.test(th.getAttribute('aria-sort') || '')).map(({ th }) => (th.querySelector('button') || th).textContent),
    folded: document.querySelector('.atl .table-footer .folded-note')?.getAttribute('title') || '',
    widths: Object.fromEntries(data.map(({ th }) => [(th.querySelector('button') || th).textContent, Math.round(th.getBoundingClientRect().width)])),
  }
})

async function seed(api: Api) {
  // Two real authorities with a published CRL, for the CRL / OCSP and SCEP challenge lists
  for (const ca of [await createCA(api, { commonName: 'Regional Issuing Authority for the West' }), await createCA(api)]) {
    await api.post(`/crl/${ca.id}/regenerate`)
    await expect.poll(async () => (await api.get(`/crl/${ca.id}`))?.crl_number).toBeGreaterThan(0)
  }
}

for (const [width, dock] of [[1600, false], [1406, true], [1280, false], [1000, false]] as const) {
  test.describe(`protocol lists at ${width} px${dock ? ', dock on the right' : ''}`, () => {
    test.use({ viewport: { width, height: dock ? 809 : 900 } })

    test('no sideways scroll, chevrons in view, headers whole, fit cells whole, cut text titled, one column sorted', async ({ page, api }) => {
      // Sixteen lists opened in turn: the budget list-columns-pki.spec.ts gives its nine
      test.setTimeout(180_000)
      await seed(api)
      await feed(page, dock)
      for (const list of LISTS) {
        await open(page, list)
        if (dock) {
          await page.locator(`${REGION} tbody tr .entity-name`).first().click()
          await expect(page.locator('#app.zone-app')).toHaveClass(/dock-right/)
        }
        // Settled widths, then every list measured even when one overflows
        await expect.poll(() => measure(page).then((m) => m.over), { message: list.name }).toBeLessThanOrEqual(1).catch(() => {})
        const m = await measure(page)
        console.log(`MEASURE ${width}${dock ? 'd' : ''} ${list.name} ${JSON.stringify(m)}`)
        expect.soft(m.over, list.name).toBeLessThanOrEqual(1)
        expect.soft(m.page, list.name).toBeLessThanOrEqual(0)
        expect.soft({ lost: m.lost, clipped: m.clipped, fitCut: m.fitCut, untitled: m.untitled }, list.name)
          .toEqual({ lost: 0, clipped: [], fitCut: [], untitled: [] })
        expect.soft(m.sorted, list.name).toEqual(list.sorted ? [list.sorted] : [])
        if (width === 1600) {
          expect.soft(m.grows, list.name).toEqual([list.grows])
          expect.soft(wide(list, m.wideHeads), list.name).toEqual([])
          // At 1600 px nothing folds and nothing is cut
          expect.soft({ folded: m.folded, cut: m.cut }, list.name).toEqual({ folded: '', cut: 0 })
        }
      }
    })
  })
}

test.describe('protocol lists in French at 1600 px', () => {
  test.use({ viewport: { width: 1600, height: 900 } })

  test('a short header stays near its values in the longest of the written languages', async ({ page, api }) => {
    test.setTimeout(180_000)
    await page.addInitScript(() => { try { localStorage.setItem('i18nextLng', 'fr') } catch { /* noop */ } })
    await seed(api)
    await feed(page)
    for (const list of LISTS) {
      await open(page, list)
      const m = await measure(page)
      console.log(`MEASURE 1600fr ${list.name} ${JSON.stringify({ wideHeads: m.wideHeads, clipped: m.clipped, widths: m.widths })}`)
      expect.soft({ wide: wide(list, m.wideHeads), clipped: m.clipped }, list.name).toEqual({ wide: [], clipped: [] })
    }
  })
})

test.describe('protocol lists on a phone', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('every record keeps its chevron, no fact is a dash, a date or a number follows its label, a sortable list sorts', async ({ page, api }) => {
    test.setTimeout(180_000)
    await seed(api)
    await feed(page)
    for (const list of LISTS) {
      await page.goto(list.url)
      const records = page.locator('.atl .mobile-list article.mobile-record.opens')
      await expect(records.first(), list.name).toBeVisible()
      const read = await page.locator('.atl .mobile-list').evaluate((el) => {
        const all = [...el.querySelectorAll('article.mobile-record.opens')]
        const outside = all.filter((r) => {
          const b = r.querySelector('.row-top > button.icon-btn')?.getBoundingClientRect()
          return !b || b.right > window.innerWidth
        }).length
        const facts = all.flatMap((r) => [...r.querySelectorAll('.row-meta > span')])
        // A bare date or a bare number, without its column's label
        const bare = facts.filter((f) => !f.querySelector('.fact-label')).map((f) => (f.textContent || '').trim())
          .filter((v) => /^\d+$/.test(v) || (!Number.isNaN(Date.parse(v)) && /\d{4}/.test(v)))
        return { outside, dashes: facts.filter((f) => f.textContent?.trim() === '—').length, bare }
      })
      console.log(`MEASURE 390 ${list.name} ${JSON.stringify(read)}`)
      expect.soft(read, list.name).toEqual({ outside: 0, dashes: 0, bare: [] })
      const select = page.getByRole('combobox', { name: 'Sort by' })
      if (list.sorted) await expect.soft(select, list.name).toBeVisible()
      else await expect.soft(select, list.name).toHaveCount(0)
    }
  })
})

test.describe('the sort of a protocol list', () => {
  test.use({ viewport: { width: 1600, height: 1000 } })

  test('a header sorts, the address keeps it, a reload gives it back; a view change drops it', async ({ page, api }) => {
    await seed(api)
    await feed(page)
    await page.goto('/acme?tab=upstream')
    const head = (name: string) => page.locator(`${REGION} thead th`).filter({ has: page.getByRole('button', { name, exact: true }) })
    await expect(head('Name')).toHaveAttribute('aria-sort', 'ascending')
    await head('ACME Directory URL').getByRole('button').click()
    await expect(page).toHaveURL(/tab=upstream&sort=directory&order=asc/)
    const names = () => page.locator(`${REGION} tbody tr .entity-name`).allTextContents()
    await expect.poll(names).toEqual(['Actalis', "Let's Encrypt", 'ZeroSSL'])
    await page.reload()
    await expect(head('ACME Directory URL')).toHaveAttribute('aria-sort', 'ascending')
    await expect(page.locator(`${REGION} tbody tr .entity-name`)).toHaveCount(3)
    expect(await names()).toEqual(['Actalis', "Let's Encrypt", 'ZeroSSL'])
    await page.getByRole('tab', { name: /^Accounts/ }).click()
    await expect(page).toHaveURL(/\/acme$/)
    // The header is named by its full label
    await expect(head('Creation date')).toHaveAttribute('aria-sort', 'descending')
  })
})
