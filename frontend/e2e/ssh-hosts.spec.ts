import { generateKeyPairSync } from 'node:crypto'
import { test, expect, uid } from './support/fixtures'

// An OpenSSH ed25519 public key line from a fresh key: string "ssh-ed25519", string the 32-byte key
function ed25519PublicKey() {
  const raw = generateKeyPairSync('ed25519').publicKey.export({ format: 'der', type: 'spki' }).subarray(-32)
  const str = (b: Buffer) => { const n = Buffer.alloc(4); n.writeUInt32BE(b.length); return Buffer.concat([n, b]) }
  return `ssh-ed25519 ${Buffer.concat([str(Buffer.from('ssh-ed25519')), str(raw)]).toString('base64')}`
}

test('a token created on screen enrolls a host once, which the page lists and revokes', async ({ page, api }) => {
  const caName = uid('ssh-hosts')
  const ca = await api.post('/ssh/cas', { descr: caName, ca_type: 'host', key_type: 'ed25519', allowed_principals: [] , allow_any_principal: true })
  const hostName = `${uid('web')}.example.test`

  await page.goto('/ssh/hosts')
  await page.getByRole('button', { name: 'New enrollment token' }).first().click()
  const dialog = page.getByRole('dialog', { name: 'New enrollment token' })
  await dialog.getByLabel('Host CA').selectOption({ label: caName })
  await dialog.getByLabel('Host names').fill(hostName)
  await dialog.getByRole('button', { name: 'New enrollment token' }).click()

  const token = (await dialog.getByTestId('ssh-token-secret').textContent())!.trim()
  expect(token).toMatch(/^ucmh_[A-Za-z0-9_-]{43}$/)
  await expect(dialog.getByTestId('ssh-token-command')).toContainText(`/ssh/setup/${ca.refid}/agent | sudo UCM_ENROLL_TOKEN=${token} sh`)
  await dialog.getByRole('button', { name: 'Close', exact: true }).click()
  await expect(dialog).toBeHidden()

  // The server's side: the public enrollment route, then the same token a second time
  const enroll = () => page.request.post(`/ssh/enroll/${ca.refid}`, { data: { token, public_key: ed25519PublicKey() } })
  expect((await enroll()).status()).toBe(201)
  expect((await enroll()).status()).toBe(403)

  await page.reload()
  const row = page.getByRole('row', { name: new RegExp(hostName) })
  await expect(row).toContainText('Valid')
  await expect(row).toContainText('On')
  await row.getByRole('button', { name: `Revoke host ${hostName}` }).click()
  const confirm = page.getByRole('dialog', { name: 'Revoke host' })
  await confirm.getByRole('button', { name: 'Revoke host' }).click()
  await expect(row).toContainText('Revoked')

  await page.goto('/ssh/hosts?view=tokens')
  await expect(page.getByRole('row', { name: new RegExp(token.slice(0, 12)) })).toContainText('Used')
})
