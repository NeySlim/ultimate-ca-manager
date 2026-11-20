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

// Actions other than Export and Renew sit in the Certificate actions dialog of the heading's « ⋯ »
async function moreAction(page, panel, cn: string, name: string) {
  await panel.getByRole('button', { name: `Other actions for ${cn}` }).click()
  await page.getByRole('dialog', { name: 'Certificate actions' }).getByRole('button', { name, exact: true }).click()
}

// The inspector writes a serial number as octets in hexadecimal; the API gives it in decimal
const serialHex = (serial: string) => {
  let hex = BigInt(serial).toString(16).toUpperCase()
  if (hex.length % 2) hex = `0${hex}`
  return hex.match(/../g)!.join(':')
}

test('a certificate issued on screen is signed by the chosen CA', async ({ page, api }) => {
  const ca = await createCA(api)
  const cn = `${uid('web')}.example.com`
  await page.goto('/certificates')
  await page.getByRole('button', { name: 'Issue', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Issue a certificate' })
  await dialog.getByLabel('Authority').selectOption(String(ca.id))
  await dialog.getByLabel('Common name').fill(cn)
  // Two steps: Configure, then Review, where alone the certificate is issued
  await dialog.getByRole('button', { name: 'Review the request' }).click()
  const review = page.getByRole('dialog', { name: 'Review the request' })
  await expect(review.getByRole('heading', { name: cn })).toBeVisible()
  await review.getByRole('button', { name: 'Issue the certificate' }).click()
  // The result screen of the Atelier, then the certificate on demand
  const result = page.getByRole('dialog', { name: 'Issuance complete' })
  await expect(result.getByRole('heading', { name: 'Certificate issued' })).toBeVisible()
  await result.getByRole('button', { name: 'View the certificate' }).click()
  await expect(result).toBeHidden()

  await expect(page.getByRole('main').getByRole('button', { name: cn, exact: true })).toBeVisible()
  const [cert] = await findCerts(api, cn)
  expect(cert).toMatchObject({ issuer: `CN=${ca.common_name}`, revoked: false })
})

test('the inspector shows the certificate the row names', async ({ page, api }) => {
  const cert = await issueCert(api, (await createCA(api)).id)
  const panel = await openInInspector(page, cert.common_name)
  await expect(panel.getByText(serialHex(cert.serial_number), { exact: false }).first()).toBeVisible()
  await panel.getByRole('tab', { name: 'Extensions', exact: true }).click()
  await expect(panel).toContainText(new RegExp(`DNS:\\s*${cert.common_name.replace(/\./g, '\\.')}`))
})

test('renewing from the inspector issues a new certificate for the same name', async ({ page, api }) => {
  const cert = await issueCert(api, (await createCA(api)).id)
  const panel = await openInInspector(page, cert.common_name)
  await panel.getByRole('button', { name: 'Renew', exact: true }).click()
  // The issue form in renewal mode: the duration only, then the Review step
  const dialog = page.getByRole('dialog', { name: 'Renew the certificate' })
  await dialog.getByRole('button', { name: 'Review the request' }).click()
  const review = page.getByRole('dialog', { name: 'Review the request' })
  await review.getByRole('button', { name: 'Renew the certificate' }).click()
  const result = page.getByRole('dialog', { name: 'Renewal complete' })
  await result.getByRole('button', { name: 'Close', exact: true }).click()
  await expect(result).toBeHidden()

  // A new serial for the same name, the old one superseded or kept beside it
  await expect.poll(async () => (await findCerts(api, cert.common_name))
    .some(c => c.serial_number !== cert.serial_number && !c.revoked)).toBe(true)
})

test('a certificate revoked from the inspector is listed by the next CRL', async ({ page, api }) => {
  const ca = await createCA(api)
  const cert = await issueCert(api, ca.id)
  const panel = await openInInspector(page, cert.common_name)
  await moreAction(page, panel, cert.common_name, 'Revoke the certificate…')
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
