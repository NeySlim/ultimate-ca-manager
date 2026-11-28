import { test, expect, createCA, createUser } from './support/fixtures'

// The lists beyond Certificats: one density for every list (M:1108) and the sort and page footer of
// the module lists, measured where jsdom cannot: row heights, the footer's place and the phone width
// Polled: a row measured while the list re-renders reads 0
const rowHeights = (page) => page.locator('.atl tbody tr').evaluateAll((rows) => rows.map((r) => Math.round(r.getBoundingClientRect().height)))

test.describe('desktop', () => {
  test.use({ viewport: { width: 1600, height: 1000 } })

  test('the density chosen on Certificates gives every list its rows, after a reload too', async ({ page, api }) => {
    // Signed in, with a CA for the CRL / OCSP list to have rows
    await createCA(api)
    await page.goto('/users')
    await expect(page.locator('.atl tbody tr').first()).toBeVisible()
    await expect.poll(async () => [...new Set(await rowHeights(page))]).toEqual([36])
    await page.goto('/certificates')
    const toggle = page.getByRole('button', { name: 'Comfortable density' })
    await toggle.click()
    await expect(toggle).toHaveAttribute('aria-pressed', 'true')
    await expect(page.locator('.atl #app')).toHaveClass(/comfortable/)
    await page.goto('/users')
    await expect(page.locator('.atl tbody tr').first()).toBeVisible()
    await expect.poll(async () => [...new Set(await rowHeights(page))]).toEqual([44])
    await page.reload()
    await expect(page.locator('.atl tbody tr').first()).toBeVisible()
    await expect.poll(async () => [...new Set(await rowHeights(page))]).toEqual([44])
    await page.goto('/certificates')
    await page.getByRole('button', { name: 'Comfortable density' }).click()
    await page.goto('/crl-ocsp')
    await expect(page.locator('.atl tbody tr').first()).toBeVisible()
    await expect.poll(async () => [...new Set(await rowHeights(page))]).toEqual([36])
  })

  test('a long CRL / OCSP list sorts from its headers and pages under the table', async ({ page, api }) => {
    for (let i = 0; i < 11; i += 1) await createCA(api)
    await page.goto('/crl-ocsp')
    const zone = page.locator('.atl')
    await expect(zone.locator('tbody tr').first()).toBeVisible()
    // Pages of 10 to show the controls with the CAs of any run: the footer closes the table frame
    const footer = zone.locator('footer.table-footer')
    await footer.getByRole('combobox', { name: 'Rows per page' }).selectOption('10')
    await expect(zone.locator('tbody tr')).toHaveCount(10)
    const frame = await zone.locator('.table-container').boundingBox()
    const foot = await footer.boundingBox()
    expect(frame && foot).toBeTruthy()
    // The mockup's 38 px footer under its 1 px rule, as on Users
    expect(Math.round(foot!.height)).toBe(39)
    expect(Math.abs(foot!.y + foot!.height - (frame!.y + frame!.height))).toBeLessThanOrEqual(1)
    await footer.getByRole('button', { name: 'Next page' }).click()
    await expect(footer).toContainText('2 /')
    const header = zone.getByRole('columnheader', { name: 'CRL', exact: true })
    await header.getByRole('button').click()
    await expect(header).toHaveAttribute('aria-sort', 'ascending')
    await expect(footer).toContainText('1 /')
    await header.getByRole('button').click()
    await expect(header).toHaveAttribute('aria-sort', 'descending')
  })

  test('the Authorities list view pages under its table', async ({ page, api }) => {
    for (let i = 0; i < 11; i += 1) await createCA(api)
    await page.goto('/cas')
    await page.getByRole('button', { name: 'List', exact: true }).click()
    const footer = page.locator('.atl footer.table-footer')
    await expect(footer).toBeVisible()
    await footer.getByRole('combobox', { name: 'Rows per page' }).selectOption('10')
    await expect(page.locator('.atl tbody tr')).toHaveCount(10)
    await expect(footer.getByRole('button', { name: 'Next page' })).toBeEnabled()
  })
})

test.describe('phone', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('a paged module list keeps its footer within the screen', async ({ page, api }) => {
    for (let i = 0; i < 11; i += 1) await createUser(api, 'viewer')
    await page.goto('/users')
    const footer = page.locator('.atl footer.table-footer')
    await expect(footer).toBeVisible()
    const foot = await footer.boundingBox()
    expect(foot!.x).toBeGreaterThanOrEqual(0)
    expect(foot!.x + foot!.width).toBeLessThanOrEqual(390)
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  })

  // `api` signs the page in
  test('a toolbar of a search field and one icon button keeps them on one line', async ({ page, api }) => {
    for (const path of ['/acme', '/crl-ocsp']) {
      await page.goto(path)
      const toolbar = page.locator('.atl .page-content .toolbar').first()
      await expect(toolbar.locator('.search')).toBeVisible()
      const field = (await toolbar.locator('.search').boundingBox())!
      const button = (await toolbar.locator('> .icon-btn').boundingBox())!
      expect(button.y, path).toBeLessThan(field.y + field.height)
      expect(button.x + button.width, path).toBeLessThanOrEqual(390)
    }
  })
})

// Wide windows: a list's search field stops at 540 px, its filters follow it, its tools sit at the right edge
const SEARCH_MAX = 540
const LISTS = ['/certificates', '/csrs', '/cas', '/templates', '/users', '/rbac', '/truststore', '/policies', '/hsm', '/acme',
  '/crl-ocsp', '/ssh/cas', '/ssh/certificates', '/user-certificates', '/audit', '/logs', '/acme?tab=history']
for (const width of [1280, 1600, 1920, 2560]) {
  test(`at ${width}px the search of a list stops at 540 px, filters after it, tools at the right`, async ({ page, api: _api }) => {
    test.setTimeout(120_000)
    await page.setViewportSize({ width, height: 1000 })
    let tooled = 0
    for (const path of LISTS) {
      await page.goto(path)
      const toolbar = page.locator('.atl .page-content .toolbar:has(> .search)').first()
      await expect(toolbar.locator('> .search'), path).toBeVisible()
      const m = await toolbar.evaluate((el) => {
        const r = (e: Element) => { const b = e.getBoundingClientRect(); return { x: b.x, right: b.right, width: b.width } }
        const kids = [...el.children].filter((k) => k.getBoundingClientRect().width > 0)
        const search = el.querySelector(':scope > .search')!
        const after = kids[kids.indexOf(search) + 1]
        const tools = kids.filter((k) => k.matches('.tools-divider, .btn, .icon-btn'))
        const c = getComputedStyle(el)
        return {
          left: r(el).x + parseFloat(c.paddingLeft), right: r(el).right - parseFloat(c.paddingRight),
          search: r(search), after: after ? { ...r(after), tool: after.matches('.tools-divider, .btn, .icon-btn') } : null,
          firstTool: tools.length ? r(tools[0]) : null, last: r(kids[kids.length - 1]), lastIsTool: tools.includes(kids[kids.length - 1]),
        }
      })
      expect(Math.abs(m.search.x - m.left), `${path}: field at the left`).toBeLessThanOrEqual(1)
      expect(Math.abs(m.search.width - SEARCH_MAX), `${path}: field of ${m.search.width} px`).toBeLessThanOrEqual(1)
      // what follows the field that is not a tool (a filter, a switch of view) starts a gap after it, two past an empty status
      if (m.after && !m.after.tool) {
        expect(m.after.x - m.search.right, `${path}: filters after the field`).toBeGreaterThanOrEqual(8 - 1)
        expect(m.after.x - m.search.right, `${path}: filters after the field`).toBeLessThanOrEqual(16 + 1)
      }
      if (m.lastIsTool) {
        tooled += 1
        expect(Math.abs(m.last.right - m.right), `${path}: tools at the right edge`).toBeLessThanOrEqual(1)
        expect(m.firstTool!.x, `${path}: room between the filters and the tools`).toBeGreaterThan(m.search.right + 100)
      }
    }
    expect(tooled).toBeGreaterThanOrEqual(5)
  })
}

// Guard against regression only: at 820 px the search held 398 px on the base too, so this proves nothing of the cap
test('at 820px the search of a list keeps the room its toolbar leaves, under 540 px', async ({ page, api: _api }) => {
  await page.setViewportSize({ width: 820, height: 1000 })
  await page.goto('/certificates')
  const toolbar = page.locator('.atl .page-content .toolbar:has(> .search)').first()
  const field = (await toolbar.locator('> .search').boundingBox())!
  expect(field.width).toBeGreaterThan(170)
  expect(field.width).toBeLessThanOrEqual(SEARCH_MAX + 1)
  const over = await toolbar.evaluate((el) => el.scrollWidth - el.clientWidth)
  expect(over).toBeLessThanOrEqual(0)
})
