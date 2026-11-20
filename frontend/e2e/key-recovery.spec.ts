import { test, expect, createCA, issueCert, createUser, uid } from './support/fixtures'
import { readFileSync } from 'node:fs'

test('a key requested, approved by another administrator, then recovered', async ({ page, api, signIn }) => {
  const cert = await issueCert(api, (await createCA(api)).id)
  const reason = uid('lost laptop')

  // Request from the certificate's inspector
  await page.goto('/certificates')
  await page.getByRole('main').getByRole('searchbox').fill(cert.common_name)
  await page.getByRole('main').getByRole('button', { name: cert.common_name, exact: true }).click()
  const panel = page.getByRole('tabpanel', { name: cert.common_name })
  // Every action but Export and Renew is in the Certificate actions dialog of the heading's « ⋯ »
  await panel.getByRole('button', { name: `Other actions for ${cert.common_name}` }).click()
  await page.getByRole('dialog', { name: 'Certificate actions' }).getByRole('button', { name: 'Recover key' }).click()
  const ask = page.getByRole('dialog')
  await ask.getByLabel('Reason').fill(reason)
  await ask.getByRole('button', { name: 'Submit request' }).click()
  await expect(ask).toBeHidden()

  // Dual control: a second administrator approves
  const approver = await createUser(api, 'admin')
  const second = await signIn(approver.username, approver.password)
  await second.page.goto('/key-recovery')
  // The queue row of the request: its approval asks for a note, optional
  await second.page.getByRole('button', { name: `Approve the recovery of ${cert.common_name}` }).click()
  await second.page.getByRole('dialog').getByRole('button', { name: 'Approve', exact: true }).click()
  await expect.poll(async () => {
    const data = await api.get('/key-recovery')
    return data.requests.find(r => r.reason === reason)?.status
  }).toBe('approved')

  // The requester downloads the key
  await page.goto('/key-recovery')
  await page.getByRole('button', { name: `Recover the key of ${cert.common_name}` }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('PKCS#12 password').fill('Recover-pass-123')
  const download = page.waitForEvent('download')
  await dialog.getByRole('button', { name: 'Download .p12' }).click()
  expect(readFileSync(await (await download).path()).length).toBeGreaterThan(500)
  const data = await api.get('/key-recovery')
  expect(data.requests.find(r => r.reason === reason)).toMatchObject({ status: 'recovered', recovered_by: 'admin' })
})
