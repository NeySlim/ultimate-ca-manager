import { test, expect, createUser, strongPassword, totp, Api, ApiError } from './support/fixtures'

test('a password changed on screen is the one that signs in', async ({ api, signIn, request }) => {
  const user = await createUser(api, 'viewer')
  const { page } = await signIn(user.username, user.password)
  const next = strongPassword()
  await page.goto('/account')
  await page.getByRole('button', { name: 'Security', exact: true }).click()
  await page.getByRole('button', { name: 'Change Password' }).click()
  const dialog = page.getByRole('dialog', { name: 'Change Password' })
  await dialog.getByLabel('Current Password').fill(user.password)
  await dialog.getByLabel('New Password', { exact: false }).first().fill(next)
  await dialog.getByLabel('Confirm New Password').fill(next)
  await dialog.getByRole('button', { name: 'Change Password' }).click()
  await expect(dialog).toBeHidden()

  await Api.login(request, user.username, next)
  await expect(Api.login(request, user.username, user.password)).rejects.toBeInstanceOf(ApiError)
})

test('TOTP enrolled on screen is asked at the next sign-in', async ({ api, signIn, request }) => {
  const user = await createUser(api, 'viewer')
  const { page } = await signIn(user.username, user.password)
  await page.goto('/account')
  await page.getByRole('button', { name: 'Security', exact: true }).click()
  const enrolment = page.waitForResponse(r => r.url().endsWith('/api/v2/account/2fa/enable'))
  await page.getByRole('button', { name: 'Enable 2FA' }).click()
  const { data } = await (await enrolment).json()
  const dialog = page.getByRole('dialog')
  await dialog.getByPlaceholder(/\d{6}|code/i).fill(totp(data.secret))
  const confirmation = page.waitForResponse(r => r.url().endsWith('/api/v2/account/2fa/confirm'))
  await dialog.getByRole('button', { name: 'Verify & Enable' }).click()
  const confirmed = await confirmation
  expect(confirmed.status()).toBe(200)
  const codes: string[] = (await confirmed.json()).data.backup_codes
  expect(codes.length).toBeGreaterThan(0)

  const first = await request.post('/api/v2/auth/login', { data: { username: user.username, password: user.password } })
  expect((await first.json()).data).toMatchObject({ requires_2fa: true })
  expect((await request.post('/api/v2/auth/login/2fa', { data: { code: codes[0] } })).status()).toBe(200)
})

test('a request still carrying the session identifier a TOTP confirmation replaced is served', async ({ api, signIn, request }) => {
  test.fail(true, 'product defect: the confirmation renews the session identifier and drops the old one at once, so a request the page sent meanwhile gets 401 and signs the user out')
  const user = await createUser(api, 'viewer')
  const { page, api: own } = await signIn(user.username, user.password)
  const { secret } = await own.post('/account/2fa/enable')
  const before = (await page.context().cookies()).find(c => c.name === 'session')!.value
  await own.post('/account/2fa/confirm', { code: totp(secret) })
  // What a request sent by the page before the answer arrived carries
  const meanwhile = await request.get('/api/v2/account/profile', { headers: { Cookie: `session=${before}` } })
  expect(meanwhile.status()).toBe(200)
})
