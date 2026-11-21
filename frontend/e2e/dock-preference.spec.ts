import { test, expect, createCA, issueCert } from './support/fixtures'

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

  test('the right anchoring chosen on Certificates holds on Templates, and back', async ({ page, api }) => {
    const cert = await issueCert(api, (await createCA(api)).id)
    try {
      await page.goto('/certificates')
      await page.getByRole('main').getByRole('searchbox').fill(cert.common_name)
      await page.getByRole('main').getByRole('button', { name: cert.common_name, exact: true }).click()
      await page.locator('#inspector').getByRole('button', { name: 'Dock on the right' }).click()
      await expect(app(page)).toHaveClass(/dock-right/)

      const { dock } = await openFirst(page, '/templates')
      await expect(app(page)).toHaveClass(/dock-right/)
      await dock.getByRole('button', { name: 'Dock at the bottom' }).click()
      await expect(app(page)).not.toHaveClass(/dock-right/)

      // The account holds it: after a reload another page opens at the bottom too
      await page.reload()
      await openFirst(page, '/users')
      await expect(app(page)).not.toHaveClass(/dock-right/)
    } finally {
      // The account is shared by the other specs: its dock goes back to the bottom
      const prefs = (await api.get('/account/preferences')) || {}
      await api.put('/account/preferences', { ...prefs, inspector: { position: 'bottom', height: 278, width: 460 } })
    }
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

test.describe('phone', () => {
  test.use({ viewport: { width: 390, height: 844 } })
  const PAGES = ['/templates', '/users', '/truststore', '/certificates']

  for (const path of PAGES) {
    test(`${path}: the dock keeps the focus, the page is inert, Escape and Close give the focus back`, async ({ page, api }) => {
      // Each page gets a row of its own: a fresh trust store is empty, issuing a certificate does not fill it
      if (path === '/truststore' || path === '/certificates') {
        const cert = await issueCert(api, (await createCA(api)).id)
        if (path === '/truststore') await api.post('/truststore', { name: cert.common_name, certificate_pem: cert.pem, purpose: 'custom' })
      }
      const { dock } = await openFirst(page, path)
      await expect(dock).toHaveAttribute('role', 'dialog')
      for (const part of ['.masthead', '.statusbar', '.page-content']) {
        await expect(page.locator(part).first()).toHaveAttribute('inert', '')
      }
      for (let i = 0; i < 40; i += 1) {
        await page.keyboard.press('Tab')
        expect(await dock.evaluate((el) => el.contains(document.activeElement))).toBe(true)
      }
      await page.keyboard.press('Escape')
      await expect(dock).toBeHidden()
      expect(await page.evaluate(() => document.activeElement?.matches('button[data-open]'))).toBe(true)
      await expect(page.locator('.page-content')).not.toHaveAttribute('inert', '')

      await page.locator('.atl button[data-open]:focus').click()
      await expect(dock).toBeVisible()
      await dock.getByRole('button', { name: 'Close inspector' }).click()
      await expect(dock).toBeHidden()
      expect(await page.evaluate(() => document.activeElement?.matches('button[data-open]'))).toBe(true)
    })
  }
})
