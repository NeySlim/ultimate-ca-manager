import { test, expect, createCA, issueCert, uid, seedOnce } from './support/fixtures'
import { ADMIN_PASSWORD } from './support/api'

// The PKI lists measured where jsdom cannot: certificates, authorities, CSRs (pending and
// signed), templates, trust store, user certificates, SSH CAs and SSH certificates, at 1000, 1280 and 1600 px dock
// closed and at 1406 px beside the dock at the right: no sideways scroll, every chevron in view, no header clipped,
// no fixed cell cut, free text cut only by an ellipsis with its whole text in a title, one sorted header, a sign on
// every sortable header, the absorbing column of the specification at 1600 px, the urgent date kept beside the dock;
// on a phone, records with their chevron, no empty fact, a lone date or number after its label, the sort select.
// Each measure is logged as one JSON line (« COLP1 … ») before it is asserted.

type List = { name: string, url: string, region: string, absorber: string, keep?: string[] }
const LISTS: List[] = [
  { name: 'certificates', url: '/certificates', region: '#cert-scroll', absorber: 'Description', keep: ['Expiry'] },
  { name: 'authorities', url: '/cas', region: '#ca-list-scroll', absorber: 'Name', keep: ['Expiry'] },
  { name: 'csrs', url: '/csrs', region: '#module-scroll', absorber: 'Subject', keep: ['Subject', 'Submitted'] },
  { name: 'csrs-signed', url: '/csrs?tab=history', region: '#module-scroll', absorber: 'Subject', keep: ['Subject', 'Submitted'] },
  { name: 'templates', url: '/templates', region: '#module-scroll', absorber: 'Name' },
  { name: 'truststore', url: '/truststore', region: '#module-scroll', absorber: 'Subject', keep: ['Expiry'] },
  { name: 'user-certificates', url: '/user-certificates', region: '#module-scroll', absorber: 'Description', keep: ['Expiry'] },
  { name: 'ssh-cas', url: '/ssh/cas', region: '#module-scroll', absorber: 'Name' },
  { name: 'ssh-certificates', url: '/ssh/certificates', region: '#module-scroll', absorber: 'Principals', keep: ['Expiry'] },
]

// One of each, with the long texts the review saw cut: a long issuer, a long subject, a long usage;
// made once for every test of the file, which only read them
const seed = (api) => seedOnce('list-columns-pki', () => make(api))

async function make(api) {
  const ca = await createCA(api, { commonName: `Regional Issuing Authority for the West ${uid('ca')}` })
  await issueCert(api, ca.id, { cn: `${uid('a-long-service-name')}.internal.example.com` })
  const pending = await api.post('/csrs', { cn: `${uid('csr-long-subject-name')}.internal.example.com`, key_type: 'RSA 2048' })
  const signed = await api.post('/csrs', { cn: `${uid('csr-signed')}.internal.example.com`, key_type: 'RSA 2048' })
  await api.post(`/csrs/${signed.id}/sign`, { ca_id: ca.id, validity_days: 30 })
  await api.post(`/truststore/add-from-ca/${ca.refid}`, { purpose: 'root_ca', description: 'Imported from system CA bundle for the bank clients' }).catch(() => null)
  // An mTLS certificate signs in alone: its route asks the account's password again
  await api.post('/mtls/certificates', { ca_id: ca.id, validity_days: 30, name: uid('user-cert'), password: ADMIN_PASSWORD })
  const ssh = await api.post('/ssh/cas', { descr: uid('ssh-users'), ca_type: 'user', key_type: 'ed25519', allowed_principals: ['alice', 'bob', 'carol', 'deploy'] })
  await api.post('/ssh/certificates/generate', { ca_id: ssh.id, cert_type: 'user', principals: ['alice', 'bob', 'carol', 'deploy'], key_type: 'ed25519', validity_seconds: 86400 })
  return { pending }
}

// The page reads the dock at the right; the shared account's preference is never written
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

async function open(page, list: List) {
  if (list.name === 'authorities') await page.addInitScript(() => localStorage.setItem('ucm-ca-view-mode', 'list'))
  await page.goto(list.url)
  // The rows read, not the skeleton drawn while they are on their way
  await expect(page.locator(`${list.region} tbody .entity-name`).first().or(page.locator(`${list.region} tbody .empty`))).toBeVisible()
  await expect(page.locator(`${list.region} tbody tr.sk-row`)).toHaveCount(0)
  await expect(page.locator(`${list.region} table.measuring`)).toHaveCount(0)
}

// Everything the rules measure on one list, as painted
const measure = (page, region: string) => page.locator(region).evaluate((el) => {
  const box = el.getBoundingClientRect()
  const heads = [...el.querySelectorAll('thead th')] as HTMLElement[]
  const data = heads.filter((th) => !th.querySelector('input, .sr-only'))
  const rows = [...el.querySelectorAll('tbody tr')].filter((tr) => tr.children.length === heads.length) as HTMLElement[]
  const lost = rows.filter((tr) => tr.querySelector('[data-open]')).filter((tr) => {
    const chevron = [...tr.querySelectorAll('td:last-child button.icon-btn[data-open]')].pop()
    if (!chevron) return true
    const r = chevron.getBoundingClientRect()
    return !r.width || !r.height || r.left < box.left - 1 || r.right > box.right + 1
  }).length
  const fitCut: string[] = []
  const noTitle: string[] = []
  const cut: Record<string, number> = {}
  heads.forEach((th, i) => {
    if (th.querySelector('input, .sr-only')) return
    for (const tr of rows) {
      const td = tr.children[i] as HTMLElement
      const free = td.classList.contains('text-cell') || td.classList.contains('description-cell') || td.classList.contains('entity-cell')
      if (!free && td.scrollWidth > td.clientWidth + 1) fitCut.push(td.textContent || '')
      for (const clip of [td, ...td.querySelectorAll('.entity-label')] as HTMLElement[]) {
        if (!free || clip.scrollWidth <= clip.clientWidth + 1) continue
        const text = (clip.textContent || '').trim()
        cut[th.textContent || ''] = (cut[th.textContent || ''] || 0) + 1
        if (getComputedStyle(clip).textOverflow !== 'ellipsis' || !((clip.title || td.title).includes(text))) noTitle.push(text)
      }
    }
  })
  return {
    over: Math.round(el.scrollWidth - el.clientWidth),
    page: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    heads: data.map((th) => th.textContent),
    widths: data.map((th) => Math.round(th.getBoundingClientRect().width)),
    absorbing: data.filter((th) => !th.classList.contains('fit')).map((th) => th.textContent),
    sorted: data.filter((th) => /^(a|de)scending$/.test(th.getAttribute('aria-sort') || '')).map((th) => th.textContent),
    unsigned: data.filter((th) => th.querySelector(':scope > button[data-sort]') && !th.querySelector(':scope > button svg')).map((th) => th.textContent),
    clippedHeads: data.filter((th) => th.scrollWidth > th.clientWidth + 1).map((th) => th.textContent),
    rows: rows.length, lost, fitCut, noTitle, cut,
  }
})

// Soft: every list is measured and logged, then the test fails on what any of them missed
const soft = expect.configure({ soft: true })

function check(m, list: List, where: string) {
  const at = `${list.name} ${where}`
  soft(m.over, at).toBeLessThanOrEqual(1)
  soft(m.page, at).toBeLessThanOrEqual(0)
  soft(m, at).toMatchObject({ lost: 0, clippedHeads: [], fitCut: [], noTitle: [], unsigned: [] })
  soft(m.sorted, at).toHaveLength(1)
}

for (const width of [1000, 1280, 1600]) {
  test.describe(`at ${width} px, dock closed`, () => {
    test.use({ viewport: { width, height: 900 } })

    // One test per list: a loop over every list overran the timeout on two cores
    for (const list of LISTS) {
      test(`${list.name}: fits, keeps its chevrons, cuts nothing without a title, shows one sort`, async ({ page, api }) => {
        await seed(api)
        await open(page, list)
        await soft.poll(() => measure(page, list.region).then((m) => m.over), { message: list.name, timeout: 3000 }).toBeLessThanOrEqual(1)
        const m = await measure(page, list.region)
        console.log(`COLP1 ${JSON.stringify({ width, dock: 'closed', list: list.name, ...m })}`)
        check(m, list, `${width}`)
        if (width === 1600) soft(m.absorbing, list.name).toEqual([list.absorber])
      })
    }
  })
}

test.describe('at 1406 px beside the dock at the right', () => {
  test.use({ viewport: { width: 1406, height: 809 } })

  for (const list of LISTS) {
    test(`${list.name}: fits beside the dock and keeps its urgent date, a long text folding first`, async ({ page, api }) => {
      await seed(api)
      await dockRight(page)
      await open(page, list)
      // A list the instance could not fill (user certificates need an mTLS enrolment) is said, not measured beside a dock
      if (!await page.locator(`${list.region} tbody .entity-name`).count()) { console.log(`COLP1 empty ${list.name}`); return }
      await page.locator(`${list.region} tbody .entity-name`).first().click()
      // The authorities open in their own panel beside the list, the other lists in the dock
      if (list.name === 'authorities') await expect(page).toHaveURL(/authority=/)
      else await expect(page.locator('.atl #app')).toHaveClass(/dock-right/)
      await soft.poll(() => measure(page, list.region).then((m) => m.over), { message: list.name, timeout: 3000 }).toBeLessThanOrEqual(1)
      const m = await measure(page, list.region)
      console.log(`COLP1 ${JSON.stringify({ width: 1406, dock: 'right', list: list.name, ...m })}`)
      check(m, list, '1406 dock right')
      for (const head of list.keep || []) soft(m.heads, `${list.name} keeps ${head}`).toContain(head)
    })
  }
})

test.describe('phone', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  for (const list of LISTS) {
    test(`${list.name}: draws records, chevron in view, no empty fact, a lone date or number named, the sort select`, async ({ page, api }) => {
      await seed(api)
      if (list.name === 'authorities') await page.addInitScript(() => localStorage.setItem('ucm-ca-view-mode', 'list'))
      await page.goto(list.url)
      const records = page.locator('.atl article.mobile-record:not(.sk-record)')
      await expect(records.first().or(page.locator('.atl .mobile-list .empty'))).toBeVisible()
      await expect(page.locator('.atl article.sk-record')).toHaveCount(0)
      if (!await records.count()) { console.log(`COLP1 empty ${list.name}`); return }
      // The sort select is drawn with the records of a sortable list
      await soft(page.locator('.atl .mobile-sort select'), list.name).toBeVisible()
      const m = await page.evaluate(() => {
        // A lone number, or a date as the interface writes it (« Jan 1, 2040 », « 1 janv. 2040 », « 2040-01-01 »)
        const plain = (s: string) => /^[\d\s.,]+$/.test(s) || /^(\p{L}{3,}\.? \d{1,2}, \d{4}|\d{1,2} \p{L}{3,}\.? \d{4}|\d{4}-\d{2}-\d{2})/u.test(s)
        const out = { records: 0, lost: 0, empty: [] as string[], unnamed: [] as string[], spill: [] as string[], sort: !!document.querySelector('.atl .mobile-sort select') }
        for (const r of document.querySelectorAll('.atl article.mobile-record')) {
          out.records += 1
          const chevron = r.querySelector('.row-top > .icon-btn')
          if (chevron) {
            const b = chevron.getBoundingClientRect()
            if (!b.width || b.right > window.innerWidth || b.left < 0) out.lost += 1
          }
          // A long labelled fact (an issuer) folds inside its record, its whole value on the card
          const edge = r.getBoundingClientRect().right
          for (const fact of r.querySelectorAll('.row-meta > span')) {
            if (fact.getBoundingClientRect().right > edge + 1) out.spill.push((fact.textContent || '').trim().slice(0, 60))
          }
          for (const fact of r.querySelectorAll('.row-meta > span, .row-status > .remaining')) {
            const text = (fact.textContent || '').trim()
            if (!text || text === '—') out.empty.push(text)
            else if (!fact.querySelector('.fact-label') && plain(text)) out.unnamed.push(text)
          }
        }
        return out
      })
      console.log(`COLP1 ${JSON.stringify({ width: 390, list: list.name, ...m })}`)
      soft(m, list.name).toMatchObject({ lost: 0, empty: [], unnamed: [], spill: [], sort: true })
      soft(m.records, list.name).toBeGreaterThan(0)
    })
  }
})
