import { readFileSync } from 'node:fs'
import { test, expect, createCA, uid, BUSY_MESSAGE } from './support/fixtures'

const en = JSON.parse(readFileSync(new URL('../src/i18n/locales/en.json', import.meta.url), 'utf8'))
const SIGN = /\/api\/v2\/csrs\/\d+\/sign$/

test('a CSR imported on screen is signed by a CA', async ({ page, api }) => {
  const ca = await createCA(api)
  // A request made elsewhere: generated, exported, then removed from UCM
  const cn = `${uid('csr')}.example.com`
  const made = await api.post('/csrs', { cn, key_type: 'RSA 2048' })
  const pem = (await api.call('GET', `/csrs/${made.id}/export`)).body as string
  expect(pem).toContain('BEGIN CERTIFICATE REQUEST')
  await api.del(`/csrs/${made.id}`)

  await page.goto('/csrs')
  await page.getByRole('main').getByRole('button', { name: 'Import', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Smart Import' })
  await dialog.getByRole('textbox').fill(pem)
  await dialog.getByRole('button', { name: 'Analyze' }).click()
  await dialog.getByRole('button', { name: /^Import 1 object/ }).click()
  await dialog.getByRole('button', { name: 'Done' }).click()

  // The row opens from its name (CSR-<id>); the subject is a cell of that row, the request opens in the dock
  await page.getByRole('main').getByRole('row').filter({ hasText: cn }).locator('.entity-name').click()
  const panel = page.locator('#inspector')
  await expect(panel.getByText(cn).first()).toBeVisible()
  await panel.getByRole('button', { name: 'Sign', exact: true }).click()
  const sign = page.getByRole('dialog', { name: 'Sign CSR' })
  // A native select, as the mockup's: the option is picked by its value
  const picker = sign.getByLabel('Certificate Authority')
  const value = await picker.locator('option', { hasText: ca.common_name }).first().getAttribute('value')
  await picker.selectOption(value!)
  // The first press meets the server's busy answer, as when another write holds SQLite; any later
  // one may meet it for real. The page says the server is busy, keeps the dialog, the operator signs again
  await page.route(SIGN, (route) => route.fulfill({
    status: 503, contentType: 'application/problem+json', headers: { 'Retry-After': '1' },
    body: JSON.stringify({ type: 'about:blank', title: 'Service Unavailable', status: 503, detail: BUSY_MESSAGE, message: BUSY_MESSAGE, error: true, code: 503 }),
  }), { times: 1 })
  for (let attempt = 1; ; attempt += 1) {
    const answer = page.waitForResponse((r) => r.request().method() === 'POST' && SIGN.test(r.url()))
    await sign.getByRole('button', { name: 'Sign CSR' }).click()
    const r = await answer
    if (r.status() !== 503 || attempt === 5) break
    await expect(page.getByText(en.messages.errors.serverBusy).first()).toBeVisible()
    await expect(sign).toBeVisible()
    await page.waitForTimeout(1000 * Math.min(Number(r.headers()['retry-after']) || 1, 2))
  }
  await expect(sign).toBeHidden()

  await expect.poll(async () => {
    const data = await api.get(`/certificates?search=${encodeURIComponent(cn)}`)
    const list = (Array.isArray(data) ? data : data.items || []) as any[]
    return list.find(c => c.common_name === cn)?.issuer
  }).toBe(`CN=${ca.common_name}`)
})

test('a request\'s details grey what it lacks and name its signature by its hash', async ({ page, api }) => {
  const cn = `${uid('csr')}.example.com`
  await api.post('/csrs', { cn, key_type: 'RSA 2048' })
  await page.goto('/csrs')
  await page.getByRole('main').getByRole('searchbox').fill(cn)
  await page.getByRole('main').getByRole('row').filter({ hasText: cn }).locator('.entity-name').click()
  const panel = page.locator('#inspector')
  await panel.getByRole('tab', { name: 'Details' }).click()
  const row = (label: string) => panel.locator('dl.kv > .row', { has: page.locator('dt', { hasText: new RegExp(`^${label}$`) }) })
  await expect(row('Organization').locator('dd.absent')).toHaveText('—')
  await expect(row('Signature').locator('dd.v')).toHaveText('SHA-256')
  await expect(panel.locator('dl.props')).toHaveCount(0)
})
