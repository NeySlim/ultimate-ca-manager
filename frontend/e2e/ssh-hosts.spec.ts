import { createHash, generateKeyPairSync, sign } from 'node:crypto'
import { test, expect, uid } from './support/fixtures'

const str = (b: Buffer) => { const n = Buffer.alloc(4); n.writeUInt32BE(b.length); return Buffer.concat([n, b]) }

// A fresh ed25519 host key: its OpenSSH public line, and the token signed with it as
// `ssh-keygen -Y sign -n ucm-ssh-host-enrollment` signs it (PROTOCOL.sshsig)
function hostKeyAndProof(token: string) {
  const { publicKey, privateKey } = generateKeyPairSync('ed25519')
  const raw = publicKey.export({ format: 'der', type: 'spki' }).subarray(-32)
  const blob = Buffer.concat([str(Buffer.from('ssh-ed25519')), str(raw)])
  const ns = Buffer.from('ucm-ssh-host-enrollment'), alg = Buffer.from('sha512'), magic = Buffer.from('SSHSIG')
  const digest = createHash('sha512').update(token).digest()
  const signed = Buffer.concat([magic, str(ns), str(Buffer.alloc(0)), str(alg), str(digest)])
  const sig = Buffer.concat([str(Buffer.from('ssh-ed25519')), str(sign(null, signed, privateKey))])
  const version = Buffer.alloc(4); version.writeUInt32BE(1)
  const body = Buffer.concat([magic, version, str(blob), str(ns), str(Buffer.alloc(0)), str(alg), str(sig)])
  const armored = `-----BEGIN SSH SIGNATURE-----\n${body.toString('base64').match(/.{1,70}/g)!.join('\n')}\n-----END SSH SIGNATURE-----\n`
  return { public_key: `ssh-ed25519 ${blob.toString('base64')}`, signature: armored }
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
  await expect(dialog.getByTestId('ssh-token-command')).toContainText(`/ssh/setup/${ca.refid}/agent | UCM_ENROLL_TOKEN=${token} sudo --preserve-env=UCM_ENROLL_TOKEN sh`)
  await dialog.getByRole('button', { name: 'Close', exact: true }).click()
  await expect(dialog).toBeHidden()

  // The server's side: the public enrollment route, then the same token a second time
  const enroll = () => page.request.post(`/ssh/enroll/${ca.refid}`, { data: { token, ...hostKeyAndProof(token) } })
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
