import { test, expect, createCA, issueCert } from './support/fixtures'

test('a managed CA added on screen enters the trust store', async ({ page, api }) => {
  const ca = await createCA(api)
  await page.goto('/truststore')
  await page.getByRole('main').getByRole('button', { name: 'Add', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Add from Managed CAs' })
  await dialog.getByRole('checkbox', { name: new RegExp(ca.common_name) }).check()
  await dialog.getByRole('button', { name: 'Add 1 selected' }).click()
  await expect(dialog).toBeHidden()

  // The list pages by 25: the search brings the new row onto the first page
  await page.getByRole('main').getByRole('searchbox').fill(ca.common_name)
  await expect(page.getByRole('main').getByText(ca.common_name).first()).toBeVisible()
  const data = await api.get('/truststore?per_page=500')
  const list = (Array.isArray(data) ? data : data.items || data.certificates) as any[]
  expect(JSON.stringify(list)).toContain(ca.common_name)
})

test('the certificate decoder reads a pasted certificate', async ({ page, api }) => {
  const cert = await issueCert(api, (await createCA(api)).id)
  await page.goto('/tools')
  await page.getByRole('navigation', { name: 'Tools', exact: true }).getByRole('link', { name: 'Certificate Decoder' }).click()
  await page.getByLabel('Certificate (PEM or DER)').fill(cert.pem)
  await page.getByRole('button', { name: 'Decode Certificate' }).click()
  const main = page.getByRole('main')
  await expect(main.getByText(cert.common_name).first()).toBeVisible()
  await expect(main.getByText(cert.issuer_name).first()).toBeVisible()
})

test('an anchor\'s details are typed rows: its digest in pairs copied whole, its issuer on the whole width', async ({ page, api }) => {
  const ca = await createCA(api)
  const anchor = await api.post(`/truststore/add-from-ca/${ca.refid}`, { purpose: 'root_ca' })
  expect(anchor.fingerprint_sha256).toMatch(/^[0-9a-f]{64}$/)
  await page.goto(`/truststore?item=${anchor.id}&section=details`)
  const dock = page.locator('#inspector')
  await expect(dock.getByRole('tab', { name: 'Details' })).toHaveAttribute('aria-selected', 'true')
  await page.evaluate(() => {
    const copied: string[] = []
    ;(window as any).__copied = copied
    navigator.clipboard.writeText = (text: string) => { copied.push(text); return Promise.resolve() }
  })
  await expect(dock.locator('dl.props')).toHaveCount(0)
  const row = (label: RegExp) => dock.locator('.row', { has: page.locator('dt', { hasText: label }) })
  // The stored digest in the pairs of a certificate's fingerprint: four lines of eight bytes, copied whole
  await expect(row(/^SHA-256$/).locator('.val.hex > .line')).toHaveCount(4)
  await row(/^SHA-256$/).getByRole('button', { name: 'Copy SHA-256' }).press('Enter')
  await expect.poll(() => page.evaluate(() => (window as any).__copied)).toEqual([anchor.fingerprint_sha256.toUpperCase().match(/../g).join(':')])
  // The issuer's DN goes under its term, on the whole width of its block
  const issuer = row(/^Issuer$/)
  const term = (await issuer.locator('dt').boundingBox())!
  const value = (await issuer.locator('dd.v').boundingBox())!
  expect(value.y).toBeGreaterThan(term.y + term.height - 1)
  expect(Math.abs(value.x - term.x)).toBeLessThanOrEqual(1)
})
