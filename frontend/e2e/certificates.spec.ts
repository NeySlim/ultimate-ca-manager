import { test, expect, createCA, issueCert, uid, derHasSerial, pemBody } from './support/fixtures'
import { readFileSync } from 'node:fs'

async function findCerts(api, cn: string) {
  const data = await api.get(`/certificates?search=${encodeURIComponent(cn)}&per_page=100`)
  return ((Array.isArray(data) ? data : data.items || data.certificates) as any[]).filter(c => c.common_name === cn)
}

async function openInInspector(page, cn: string) {
  await page.goto('/certificates')
  // The name is the button that opens the row; the row's other controls carry the name too
  await page.getByRole('main').getByRole('button', { name: cn, exact: true }).click()
  const panel = page.getByRole('tabpanel', { name: cn })
  await expect(panel.getByRole('heading', { name: cn })).toBeVisible()
  return panel
}

test('a certificate issued on screen is signed by the chosen CA', async ({ page, api }) => {
  const ca = await createCA(api)
  const cn = `${uid('web')}.example.com`
  await page.goto('/certificates')
  await page.getByRole('button', { name: 'Issue', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Issue Certificate' })
  await dialog.getByLabel('Certificate Authority').click()
  await page.getByRole('option', { name: new RegExp(ca.common_name) }).click()
  await dialog.getByLabel('Common Name').fill(cn)
  await dialog.getByRole('button', { name: 'Issue Certificate' }).click()
  await expect(dialog).toBeHidden()

  await expect(page.getByRole('main').getByRole('button', { name: cn, exact: true })).toBeVisible()
  const [cert] = await findCerts(api, cn)
  expect(cert).toMatchObject({ issuer: `CN=${ca.common_name}`, revoked: false })
})

test('the inspector shows the certificate the row names', async ({ page, api }) => {
  const cert = await issueCert(api, (await createCA(api)).id)
  const panel = await openInInspector(page, cert.common_name)
  await expect(panel.getByText(cert.serial_number, { exact: false }).first()).toBeVisible()
  await expect(panel).toContainText(new RegExp(`DNS:\\s*${cert.common_name.replace(/\./g, '\\.')}`))
})

test('renewing from the inspector issues a new certificate for the same name', async ({ page, api }) => {
  const cert = await issueCert(api, (await createCA(api)).id)
  const panel = await openInInspector(page, cert.common_name)
  await panel.getByRole('button', { name: 'Renew', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Renew Certificate' })
  await dialog.getByRole('button', { name: 'Renew', exact: true }).click()
  await expect(dialog).toBeHidden()

  // A new serial for the same name, the old one superseded or kept beside it
  await expect.poll(async () => (await findCerts(api, cert.common_name))
    .some(c => c.serial_number !== cert.serial_number && !c.revoked)).toBe(true)
})

test('a certificate revoked from the inspector is listed by the next CRL', async ({ page, api }) => {
  const ca = await createCA(api)
  const cert = await issueCert(api, ca.id)
  const panel = await openInInspector(page, cert.common_name)
  await panel.getByRole('button', { name: 'Revoke', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Revoke certificate' })
  await dialog.getByRole('button', { name: 'Revoke', exact: true }).click()
  await expect(dialog).toBeHidden()

  await expect.poll(async () => (await api.get(`/certificates/${cert.id}`)).revoked).toBe(true)
  await api.post(`/crl/${ca.id}/regenerate`)
  const crl = await api.get(`/crl/${ca.id}`)
  expect(crl.revoked_count).toBe(1)
  expect(derHasSerial(pemBody(crl.crl_pem), BigInt(cert.serial_number).toString(16))).toBe(true)
})

test('the PEM exported from the inspector is the certificate', async ({ page, api }) => {
  const cert = await issueCert(api, (await createCA(api)).id)
  const panel = await openInInspector(page, cert.common_name)
  await panel.getByRole('button', { name: 'Export', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Export' })
  const download = page.waitForEvent('download')
  await dialog.getByRole('button', { name: 'Download' }).click()
  const file = readFileSync(await (await download).path(), 'utf8')
  expect(file).toContain('-----BEGIN CERTIFICATE-----')
  expect(pemBody(file.split('-----END CERTIFICATE-----')[0])).toEqual(pemBody(cert.pem))
})
