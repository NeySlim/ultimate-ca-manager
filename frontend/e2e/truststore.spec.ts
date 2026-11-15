import { test, expect, createCA, issueCert } from './support/fixtures'

test('a managed CA added on screen enters the trust store', async ({ page, api }) => {
  const ca = await createCA(api)
  await page.goto('/truststore')
  await page.getByRole('main').getByRole('button', { name: 'Add', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Add from Managed CAs' })
  await dialog.getByRole('checkbox', { name: new RegExp(ca.common_name) }).check()
  await dialog.getByRole('button', { name: 'Add 1 selected' }).click()
  await expect(dialog).toBeHidden()

  await expect(page.getByRole('main').getByText(ca.common_name).first()).toBeVisible()
  const data = await api.get('/truststore?per_page=500')
  const list = (Array.isArray(data) ? data : data.items || data.certificates) as any[]
  expect(JSON.stringify(list)).toContain(ca.common_name)
})

test('the certificate decoder reads a pasted certificate', async ({ page, api }) => {
  const cert = await issueCert(api, (await createCA(api)).id)
  await page.goto('/tools')
  await page.getByRole('button', { name: 'Certificate Decoder' }).click()
  await page.getByLabel('Certificate (PEM or DER)').fill(cert.pem)
  await page.getByRole('button', { name: 'Decode Certificate' }).click()
  const main = page.getByRole('main')
  await expect(main.getByText(cert.common_name).first()).toBeVisible()
  await expect(main.getByText(cert.issuer_name).first()).toBeVisible()
})
