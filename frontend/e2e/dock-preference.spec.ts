import { test, expect, createCA, issueCert, createUser } from './support/fixtures'

// The one dock of the interface: one account preference for every page, the right anchoring from
// 1200 px, on a phone a modal dialog that keeps the focus and gives it back to the row
const opener = (page) => page.locator('.atl button[data-open]:visible').first()
const app = (page) => page.locator('.atl #app')

async function openFirst(page, path: string) {
  await page.goto(path)
  await expect(page.locator('h1#main-title')).toBeVisible()
  const row = opener(page)
  await expect(row).toBeVisible()
  await row.click()
  const dock = page.locator('#inspector')
  await expect(dock).toBeVisible()
  return { row, dock }
}

test.describe('desktop', () => {
  test.use({ viewport: { width: 1600, height: 1000 } })

  // The preference is written on an account of this test's own: the shared one is read by specs running beside it
  test('the right anchoring chosen on Certificates holds on Templates, and back', async ({ api, signIn }) => {
    const cert = await issueCert(api, (await createCA(api)).id)
    const user = await createUser(api, 'admin')
    const { page, api: own } = await signIn(user.username, user.password)
    await page.goto('/certificates')
    await page.getByRole('main').getByRole('searchbox').fill(cert.common_name)
    await page.getByRole('main').getByRole('button', { name: cert.common_name, exact: true }).click()
    await page.locator('#inspector').getByRole('button', { name: 'Dock on the right' }).click()
    await expect(app(page)).toHaveClass(/dock-right/)
    await expect.poll(async () => (await own.get('/account/preferences'))?.inspector?.position).toBe('right')

    const { dock } = await openFirst(page, '/templates')
    await expect(app(page)).toHaveClass(/dock-right/)
    await dock.getByRole('button', { name: 'Dock at the bottom' }).click()
    await expect(app(page)).not.toHaveClass(/dock-right/)

    // The account holds it: after a reload another page opens at the bottom too
    await page.reload()
    await openFirst(page, '/users')
    await expect(app(page)).not.toHaveClass(/dock-right/)
    await expect.poll(async () => (await own.get('/account/preferences'))?.inspector?.position).toBe('bottom')
  })

  test('the open certificates stay open across pages by default', async ({ page, api }) => {
    const cert = await issueCert(api, (await createCA(api)).id)
    await page.goto('/certificates')
    await page.getByRole('main').getByRole('searchbox').fill(cert.common_name)
    await page.getByRole('main').getByRole('button', { name: cert.common_name, exact: true }).click()
    await expect(page.locator('#inspector')).toBeVisible()
    await page.getByRole('navigation', { name: 'Main navigation' }).locator('a[data-module="cas"]').click()
    await expect(page.locator('h1#main-title')).toBeVisible()
    await page.getByRole('navigation', { name: 'Main navigation' }).locator('a[data-module="certificates"]').click()
    await expect(page.locator('#inspector')).toBeVisible()
  })
})

for (const width of [1199, 1200]) {
  test.describe(`at ${width} px`, () => {
    test.use({ viewport: { width, height: 900 } })
    // `api` signs the page in: without it the page is the sign-in screen
    test(`offers the right anchoring only from 1200 px (${width})`, async ({ page, api }) => {
      const { dock } = await openFirst(page, '/templates')
      await expect(dock.getByRole('button', { name: 'Dock on the right' })).toHaveCount(width >= 1200 ? 1 : 0)
    })
  })
}

test.describe('at 1200 px with the dock at the right', () => {
  test.use({ viewport: { width: 1200, height: 900 } })
  // Beside the right dock the list folds its secondary columns and its toolbar: no horizontal scroll, the chevron in view.
  // The page alone reads the dock at the right: the shared account's preference is never written.
  test('the lists fit beside the dock', async ({ page, api }) => {
    await issueCert(api, (await createCA(api)).id)
    // The session restore (/auth/verify) and the preference read carry the account's preferences
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
    for (const path of ['/certificates', '/users', '/templates']) {
      await openFirst(page, path)
      await expect(app(page)).toHaveClass(/dock-right/)
      const fits = () => page.evaluate(() => {
        const region = document.querySelector('.atl .page-content .table-scroll') as HTMLElement
        const box = region.closest('.table-container')!.getBoundingClientRect()
        const chevron = region.querySelector('tbody tr td:last-child button:last-of-type')
        return region.scrollWidth - region.clientWidth <= 1 && (!chevron || chevron.getBoundingClientRect().right <= box.right + 1)
      })
      await expect.poll(fits, { message: path }).toBe(true)
      // Its toolbar folds when short of room: the search shows its whole hint, each filter its whole choice
      const readable = () => page.evaluate(() => {
        const bar = document.querySelector('.atl .page-content .toolbar') as HTMLElement
        const ctx = document.createElement('canvas').getContext('2d')!
        const fits = (el: HTMLElement, text: string, room: number) => {
          const cs = getComputedStyle(el)
          ctx.font = `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`
          return ctx.measureText(text).width <= room + 0.5
        }
        const input = bar.querySelector('.search input') as HTMLInputElement
        const selects = [...bar.querySelectorAll('select')] as HTMLSelectElement[]
        return bar.scrollWidth <= bar.clientWidth + 1 && (!input || fits(input, input.placeholder, input.clientWidth))
          && selects.every((s) => fits(s, s.options[s.selectedIndex]?.text || '', s.getBoundingClientRect().width - 38))
      })
      await expect.poll(readable, { message: `${path} toolbar` }).toBe(true)
    }
  })
})
