import { test, expect, createCA, issueCert, strongPassword } from './support/fixtures'

// The governance and administration lists on the column template, measured where jsdom
// cannot: no list scrolls sideways at any desktop width, dock closed or at the right; no header is clipped, no fitted
// cell cut, no free text cut without its whole text in a title; one column sorted from the first view; the
// checkbox is 40 px; the tables of the settings keep the 36 px row; on a phone, the sort from the toolbar.

const LISTS = [
  { name: 'users', url: '/users', region: '#module-scroll', sorted: 'Name' },
  { name: 'groups', url: '/users?tab=groups', region: '#module-scroll', sorted: 'Name' },
  { name: 'roles', url: '/rbac', region: '#module-scroll', sorted: 'Name' },
  { name: 'policies', url: '/policies', region: '#module-scroll', sorted: 'Priority' },
  { name: 'hsm', url: '/hsm', region: '#module-scroll', sorted: 'Name', empty: true },
  { name: 'scans', url: '/discovery', region: '#module-scroll', sorted: 'Name', empty: true },
  { name: 'discovered', url: '/discovery?tab=discovered', region: '#module-scroll', sorted: 'Expires', empty: true },
  { name: 'runs', url: '/discovery?tab=history', region: '#module-scroll', sorted: 'Started', empty: true },
  { name: 'audit', url: '/audit', region: '#audit-scroll', sorted: 'Time', journal: true },
  { name: 'logs', url: '/logs', region: '#logs-scroll', sorted: 'Time', journal: true, empty: true },
  { name: 'operations', url: '/operations?tab=bulk', region: '#ops-scroll', sorted: 'Common Name' },
  { name: 'scheduler', url: '/settings?tab=scheduler', region: '#scheduler-scroll', sorted: 'Task' },
  { name: 'backups', url: '/settings?tab=backup', region: '#backup-scroll', sorted: 'Created', empty: true },
]

// Fixed names, created once per base and reused by every test: a seed per test grew the shared lists without end
const SEED = {
  ca: 'Regional Issuing Authority for the West (list fixture)',
  cert: 'a-long-service-name-of-the-list-fixture.internal.example.com',
  // A journal entry whose resource is as long as a name may be: 64 characters
  longCert: 'svc-list-fixture.the-longest-internal-subdomain.example.com'.padEnd(64, 'x').slice(0, 64),
  user: 'operator_list_fixture',
  group: 'group-list-fixture',
  // A journal entry whose resource is as long as a group name may be: 100 characters
  longGroup: 'group-list-fixture-operators-of-the-issuing-authorities-of-the-western-region-on-call'.padEnd(100, 'x').slice(0, 100),
  policy: 'policy-list-fixture',
}

const items = (data) => (Array.isArray(data) ? data : data?.items || data?.certificates || data?.users || []) as any[]

// Found, else created; a create refused because another worker made it meanwhile finds it again
async function ensure(find: () => Promise<any>, create: () => Promise<any>) {
  const found = await find()
  if (found) return found
  try {
    return await create()
  } catch (e) {
    const again = await find()
    if (again) return again
    throw e
  }
}

async function seed(api, { journal = false } = {}) {
  const q = encodeURIComponent
  const ca = await ensure(async () => items(await api.get(`/cas?search=${q(SEED.ca)}`)).find((c) => c.common_name === SEED.ca),
    () => createCA(api, { commonName: SEED.ca }))
  const cert = (cn) => ensure(async () => items(await api.get(`/certificates?search=${q(cn)}&per_page=100`)).find((c) => c.common_name === cn),
    () => issueCert(api, ca.id, { cn }))
  await cert(SEED.cert)
  const longCert = await cert(SEED.longCert)
  await ensure(async () => items(await api.get(`/users?search=${q(SEED.user)}`)).find((u) => u.username === SEED.user),
    () => api.post('/users', { username: SEED.user, password: strongPassword(), email: `${SEED.user}@example.test`, role: 'operator' }))
  const group = (name, extra = {}) => ensure(async () => items(await api.get(`/groups?search=${q(name)}`)).find((g) => g.name === name),
    () => api.post('/groups', { name, ...extra }))
  await group(SEED.group, { description: 'The operators of the issuing authorities of the western region, on call' })
  const longGroup = await group(SEED.longGroup)
  await ensure(async () => items(await api.get('/policies')).find((p) => p.name === SEED.policy),
    () => api.post('/policies', { name: SEED.policy, operations: ['issuance'], priority: 20, ca_id: ca.id, requires_approval: false }))
  if (journal) {
    // Fresh journal entries naming the long resources, without a new object
    await api.patch(`/certificates/${longCert.id}`, { descr: SEED.longCert })
    await api.put(`/groups/${longGroup.id}`, { description: 'The long-named group of the list fixture' })
  }
}

async function open(page, list) {
  await page.goto(list.url)
  await expect(page.locator(`${list.region} thead th`).first()).toBeVisible()
  // The skeleton rows gone: the list is read
  await expect(page.locator(`${list.region} tbody tr.sk-row`)).toHaveCount(0)
  if (!list.empty) await expect(page.locator(`${list.region} tbody tr td:not([colspan])`).first()).toBeVisible()
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

// Overflow, clipped headers, cut fitted cells, free text cut without its title, the sorted headers, the checkbox width
const geometry = (page, region, journal) => page.locator(region).evaluate((el, isJournal) => {
  const heads = [...el.querySelectorAll('thead th')] as HTMLElement[]
  const clippedHeads = heads.filter((th) => th.scrollWidth > th.clientWidth + 1).map((th) => th.textContent)
  const fitCut: string[] = []
  const noTitle: string[] = []
  const rows = [...el.querySelectorAll('tbody tr')].filter((tr) => !tr.querySelector('td[colspan]'))
  heads.forEach((th, i) => {
    if (th.querySelector('input, .sr-only')) return
    for (const tr of rows) {
      const td = tr.children[i] as HTMLElement
      if (!td) continue
      const free = td.classList.contains('text-cell') || td.classList.contains('entity-cell') || td.classList.contains('description-cell')
      if (th.classList.contains('fit') && !free && td.scrollWidth > td.clientWidth + 1) fitCut.push(`${th.textContent}: ${td.textContent}`)
      if (isJournal) continue
      for (const box of [td, ...td.querySelectorAll('*')] as HTMLElement[]) {
        const cs = getComputedStyle(box)
        if (cs.overflowX === 'visible' || box.scrollWidth <= box.clientWidth + 1 || box.matches('svg, svg *, button.icon-btn, input')) continue
        const tip = box.title || td.title || box.closest('[title]')?.getAttribute('title') || ''
        if (!tip.includes((box.textContent || '').trim().slice(0, 20))) noTitle.push(`${th.textContent}: ${box.textContent}`)
      }
    }
  })
  const sorted = heads.filter((th) => /ending/.test(th.getAttribute('aria-sort') || '')).map((th) => th.textContent)
  const check = el.querySelector('thead th.check-col') as HTMLElement | null
  return {
    over: el.scrollWidth - el.clientWidth, page: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    clippedHeads, fitCut, noTitle, sorted, check: check ? Math.round(check.getBoundingClientRect().width) : null,
  }
}, journal)

for (const width of [1000, 1280, 1600]) {
  test.describe(`at ${width} px, dock closed`, () => {
    test.use({ viewport: { width, height: 900 } })

    // One test per list: a page visit costs seconds on two cores, a loop over every list overran the timeout
    for (const list of LISTS) {
      test(`${list.name}: no scroll sideways, no header clipped, no text cut without its title, one column sorted`, async ({ page, api }) => {
        await seed(api, { journal: list.journal })
        await open(page, list)
        await expect.poll(() => geometry(page, list.region, list.journal).then((g) => g.over), { message: list.name }).toBeLessThanOrEqual(1)
        const g = await geometry(page, list.region, list.journal)
        expect(g, list.name).toMatchObject({ clippedHeads: [], fitCut: [], noTitle: [], sorted: [list.sorted] })
        expect(g.page, list.name).toBeLessThanOrEqual(0)
        if (g.check !== null) expect(g.check, list.name).toBe(40)
      })
    }
  })
}

test.describe('at 1406 px, the dock at the right', () => {
  test.use({ viewport: { width: 1406, height: 809 } })

  test('a list beside its dock folds before it scrolls, and cuts no text without its title', async ({ page, api }) => {
    await seed(api)
    await dockRight(page)
    for (const list of LISTS.filter((l) => ['users', 'groups', 'roles', 'policies'].includes(l.name))) {
      await open(page, list)
      await page.locator(`${list.region} tbody tr`).first().locator('button.entity-name').click()
      await expect(page.locator('.atl #app')).toHaveClass(/dock-right/)
      await expect.poll(() => geometry(page, list.region, false).then((g) => g.over), { message: list.name }).toBeLessThanOrEqual(1)
      const g = await geometry(page, list.region, false)
      expect(g, list.name).toMatchObject({ clippedHeads: [], fitCut: [], noTitle: [], sorted: [list.sorted] })
      // The chevron of every row stays in the region
      const lost = await page.locator(list.region).evaluate((el) => {
        const box = el.getBoundingClientRect()
        return [...el.querySelectorAll('tbody tr')].filter((tr) => {
          const c = tr.querySelector('td:last-child button.icon-btn[data-open]')
          if (!c) return false
          const r = c.getBoundingClientRect()
          return !r.width || r.right > box.right + 1
        }).length
      })
      expect(lost, list.name).toBe(0)
    }
  })
})

test.describe('the columns at 1600 px', () => {
  test.use({ viewport: { width: 1600, height: 1000 } })

  const ABSORBERS = {
    users: ['Email'], groups: ['Description'], roles: ['Description'], policies: ['Name'], hsm: ['Name'], scans: ['Range'],
    discovered: ['Issuer'], runs: ['Name'], operations: ['Common Name'], scheduler: ['Last result'], backups: ['Name'],
  }
  for (const list of LISTS.filter((l) => !l.journal)) {
    test(`${list.name}: the absorbing column is free text or the name`, async ({ page, api }) => {
      await seed(api)
      await open(page, list)
      const absorber = await page.locator(`${list.region} thead th`).evaluateAll((ths) => ths
        .filter((th) => !th.classList.contains('fit') && !th.querySelector('input, .sr-only')).map((th) => th.textContent))
      expect(absorber).toEqual(ABSORBERS[list.name])
    })
  }

  test('counts read at the right', async ({ page, api }) => {
    await seed(api)
    await open(page, LISTS[2])
    const users = page.locator('#module-scroll thead th').filter({ hasText: 'Users' })
    expect(await users.evaluate((th) => [getComputedStyle(th).textAlign, getComputedStyle(th).fontVariantNumeric])).toEqual(['right', 'tabular-nums'])
  })

  test('the settings rows are 36 px', async ({ page, api }) => {
    await seed(api)
    await open(page, LISTS.find((l) => l.name === 'scheduler'))
    const heights = await page.locator('#scheduler-scroll tbody tr').evaluateAll((trs) => trs.map((tr) => Math.round(tr.getBoundingClientRect().height)))
    expect(new Set(heights)).toEqual(new Set([36]))
  })

  test('the sort of a list is kept by a reload; a settings list keeps its own beside the others', async ({ page, api }) => {
    await seed(api)
    await open(page, LISTS[2])
    await page.locator('#module-scroll thead th button[data-sort=users]').click()
    await expect(page).toHaveURL(/\/rbac\?sort=users&order=asc$/)
    await page.reload()
    await expect(page.locator('#module-scroll thead th[aria-sort=ascending]')).toHaveText('Users')
    await open(page, LISTS.find((l) => l.name === 'scheduler'))
    await page.locator('#scheduler-scroll thead th button[data-sort=runs]').click()
    await expect(page).toHaveURL(/tasks-sort=runs&tasks-order=asc/)
    await page.reload()
    await expect(page.locator('#scheduler-scroll thead th[aria-sort=ascending]')).toHaveText('Runs')
  })
})

test.describe('on a phone', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('a list sorts from its toolbar, its records name their dates and counts', async ({ page, api }) => {
    await seed(api)
    await page.goto('/rbac')
    const select = page.locator('.mobile-sort select')
    await expect(select).toHaveValue('name')
    const firstNames = () => page.locator('.mobile-record:not(.sk-record) .entity-name').allTextContents()
    await expect.poll(() => firstNames().then((n) => n.length)).toBeGreaterThan(1)
    const before = await firstNames()
    await page.locator('.mobile-sort button[data-action=reverse-sort]').click()
    await expect.poll(firstNames).toEqual([...before].reverse())
    // A count names its column before its value
    await expect(page.locator('.mobile-record .row-meta .fact-label').first()).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0)
  })
})
