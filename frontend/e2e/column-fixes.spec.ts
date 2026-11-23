import { test, expect, createCA, issueCert, createUser, uid } from './support/fixtures'

// The column template after its last measure (COL-FIX): the handle grabbed right of its line, the layout measured again
// after a change of language, the trust store's subject kept readable beside the dock, the scheduler's inspector,
// and an inspector laid out by its own width in a floating window.

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

async function settled(page, region: string) {
  await expect(page.locator(`${region} tbody .entity-name`).first()).toBeVisible()
  await expect(page.locator(`${region} tbody tr.sk-row`)).toHaveCount(0)
  await expect(page.locator(`${region} table.measuring`)).toHaveCount(0)
}

// The region's sideways overflow and the rows whose chevron left it
const geometry = (page, region: string) => page.locator(region).evaluate((el) => {
  const box = el.getBoundingClientRect()
  const lost = [...el.querySelectorAll('tbody tr')].filter((tr) => tr.querySelector('[data-open]')).filter((tr) => {
    const chevron = [...tr.querySelectorAll('td:last-child button.icon-btn[data-open]')].pop()
    if (!chevron) return true
    const r = chevron.getBoundingClientRect()
    return !r.width || r.left < box.left - 1 || r.right > box.right + 1
  }).length
  return { over: el.scrollWidth - el.clientWidth, lost }
})

test.describe('the handle of a column', () => {
  test.use({ viewport: { width: 1600, height: 1000 } })

  test('grabbed 2 px right of its line it widens the column on its left and sorts nothing', async ({ page, api }) => {
    const ca = await createCA(api)
    await issueCert(api, ca.id)
    await page.goto('/certificates')
    await settled(page, '#cert-scroll')
    const heads = page.locator('#cert-scroll thead th')
    const name = heads.filter({ has: page.locator(':scope > [role=separator]') }).first()
    const next = name.locator('xpath=following-sibling::th[1]')
    const sortBefore = await next.getAttribute('aria-sort')
    const url = page.url()
    const width = () => name.evaluate((el) => Math.round(el.getBoundingClientRect().width))
    const before = await width()
    const b = (await name.boundingBox())!
    const line = b.x + b.width
    // The zone is 24 px across the line: 12 in the header, 12 in the next one, which lights the line on hover
    const lead = next.locator(':scope > .col-resize-lead')
    expect(Math.round((await lead.boundingBox())!.width)).toBe(12)
    await page.mouse.move(line + 2, b.y + b.height / 2)
    await expect.poll(() => name.locator(':scope > .col-resize').evaluate((g) => getComputedStyle(g, '::before').width)).toBe('2px')
    await page.mouse.down()
    await page.mouse.move(line + 16, b.y + b.height / 2, { steps: 4 })
    await page.mouse.move(line + 30, b.y + b.height / 2, { steps: 4 })
    await page.mouse.up()
    await expect.poll(width).toBeGreaterThanOrEqual(before + 26)
    expect(await next.getAttribute('aria-sort')).toBe(sortBefore)
    expect(page.url()).toBe(url)
    // Réinitialiser les colonnes in the footer of the Certificates too
    const reset = page.locator('#cert-scroll').locator('xpath=..').locator('.table-footer [data-action=reset-columns]')
    await reset.click()
    await expect(reset).toHaveCount(0)
    expect(await name.evaluate((el) => el.style.width)).toBe('')
  })
})

test('a change of language measures the columns again: no sideways scroll, every chevron in view', async ({ api, signIn }) => {
  const ca = await createCA(api)
  for (let i = 0; i < 3; i += 1) await issueCert(api, ca.id)
  const user = await createUser(api, 'viewer')
  const { page } = await signIn(user.username, user.password)
  await page.setViewportSize({ width: 1000, height: 800 })
  await page.goto('/certificates')
  await settled(page, '#cert-scroll')
  expect(await geometry(page, '#cert-scroll')).toEqual({ over: 0, lost: 0 })
  await page.locator('#language-button').click()
  await page.getByRole('menuitemradio', { name: 'Deutsch' }).click()
  await expect(page.locator('html')).toHaveAttribute('lang', /^de/)
  await expect(page.locator('#cert-scroll table.measuring')).toHaveCount(0)
  await expect.poll(async () => (await geometry(page, '#cert-scroll')).over).toBeLessThanOrEqual(1)
  expect((await geometry(page, '#cert-scroll')).lost).toBe(0)
})

test.describe('beside the dock at 1406 px', () => {
  test.use({ viewport: { width: 1406, height: 809 } })

  test('the trust store keeps 160 px of subject: a column of priority 3 or 4 folds first', async ({ page, api }) => {
    const ca = await createCA(api, { commonName: `Regional Issuing Authority for the West ${uid('ts')}` })
    await api.post(`/truststore/add-from-ca/${ca.refid}`, { purpose: 'root_ca', description: 'Imported from system CA bundle for the bank clients' }).catch(() => null)
    await dockRight(page)
    await page.goto('/truststore')
    await settled(page, '#module-scroll')
    await page.locator('#module-scroll tbody tr td:last-child button[data-open]').first().click()
    await expect(page.locator('#inspector')).toBeVisible()
    await expect(page.locator('#module-scroll table.measuring')).toHaveCount(0)
    const subject = page.locator('#module-scroll thead th').filter({ hasText: 'Subject' })
    await expect.poll(() => subject.evaluate((el) => Math.round(el.getBoundingClientRect().width))).toBeGreaterThanOrEqual(160)
    expect((await geometry(page, '#module-scroll')).over).toBeLessThanOrEqual(1)
  })
})

test.describe('the scheduler', () => {
  test.use({ viewport: { width: 1000, height: 800 } })

  test('folds with a footer that says so, no line before its buttons, and opens a task with every column', async ({ page, api }) => {
    await page.goto('/settings?tab=scheduler')
    const region = page.locator('#scheduler-scroll')
    await expect(region.locator('tbody tr').first()).toBeVisible()
    await expect(region.locator('table.measuring')).toHaveCount(0)
    const footer = region.locator('xpath=..').locator('.table-footer .folded-note')
    await expect(footer).toBeVisible()
    // The last labelled header draws no separator before the column of buttons
    const last = await region.locator('thead th').evaluateAll((ths) => {
      const labelled = ths.filter((th) => th.querySelector(':scope > [role=separator]'))
      return labelled.at(-1)?.querySelector(':scope > .col-sep') ? 'line' : 'none'
    })
    expect(last).toBe('none')
    await region.locator('tbody tr').first().locator('td:last-child button[data-open]').click()
    const dock = page.locator('#inspector')
    await expect(dock).toBeVisible()
    await expect(dock.locator('dl.kv dt')).toHaveCount(7)
    await expect(page).toHaveURL(/item=/)
  })
})

// Which characters end the lines of an element's text, in reading order
const lineEnds = (locator) => locator.evaluate((el) => {
  const ends: string[] = []
  let top: number | null = null
  let prev = ''
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT)
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = node.textContent || ''
    for (let i = 0; i < text.length; i += 1) {
      const range = document.createRange()
      range.setStart(node, i)
      range.setEnd(node, i + 1)
      const r = range.getClientRects()[0]
      if (!r) continue
      if (top !== null && r.top > top + 2) ends.push(prev)
      top = r.top
      prev = text[i]
    }
  }
  return ends
})

test.describe('an inspector in a floating window (container queries)', () => {
  test.use({ viewport: { width: 1600, height: 1000 } })

  test('at 620 px two columns, at 480 px one, and a 40-character name breaks at its separators only', async ({ page, api }) => {
    const ca = await createCA(api)
    const suffix = '.internal.example.org'
    const label = `${uid('w')}abcdefghijklmnop`.slice(0, 40 - suffix.length).replace(/-$/, 'x')
    const cert = await issueCert(api, ca.id, { cn: `${label}${suffix}` })
    expect(cert.common_name).toHaveLength(40)
    await page.goto('/certificates')
    await page.getByRole('main').getByRole('searchbox').fill(cert.common_name)
    await page.getByRole('main').getByRole('button', { name: cert.common_name, exact: true }).click()
    await page.locator('#inspector').getByRole('button', { name: 'Detach into a window' }).click()
    const win = page.getByRole('dialog', { name: cert.common_name })
    await expect(win).toBeVisible()
    const edge = win.locator('.float-edge-e')
    for (const [target, display] of [[620, 'grid'], [480, 'flex']] as const) {
      const w = (await win.boundingBox())!.width
      const e = (await edge.boundingBox())!
      await page.mouse.move(e.x + e.width / 2, e.y + e.height / 2)
      await page.mouse.down()
      await page.mouse.move(e.x + e.width / 2 + (target - w), e.y + e.height / 2, { steps: 6 })
      await page.mouse.up()
      await expect.poll(async () => Math.round((await win.boundingBox())!.width)).toBe(target)
      const overview = win.locator('[data-testid=certificate-overview]')
      await expect.poll(() => overview.evaluate((el) => getComputedStyle(el).display)).toBe(display)
      // On two lines at most, after a separator of the name
      const san = overview.locator('dt', { hasText: 'Alternative name' }).locator('xpath=following-sibling::dd[1]')
      const ends = await lineEnds(san)
      expect(ends.length, `${target} px`).toBeLessThanOrEqual(1)
      for (const end of ends) expect(end, `${target} px`).toMatch(/^[.-]$/)
      // The serial wraps after its colons, never inside a byte
      const serial = overview.locator('dt', { hasText: 'Serial' }).locator('xpath=following-sibling::dd[1]')
      for (const end of await lineEnds(serial)) expect(end, `${target} px`).toBe(':')
    }
  })
})
