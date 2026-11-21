import type { APIRequestContext, Page } from '@playwright/test'
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

// The server never takes back an identifier it replaced (session fixation): a request the page
// sent with it is refused, and the page checks its current session and sends that request again.
async function stalePageRequest(page: Page, request: APIRequestContext, renew: () => Promise<unknown>) {
  await page.goto('/account')
  await expect(page.getByRole('button', { name: 'Security', exact: true })).toBeVisible()
  const before = (await page.context().cookies()).find(c => c.name === 'session')!.value
  await renew()
  const after = (await page.context().cookies()).find(c => c.name === 'session')!.value
  expect(after).not.toBe(before)

  const statuses: number[] = []
  page.on('response', r => { if (r.url().endsWith('/api/v2/account/profile')) statuses.push(r.status()) })
  // The first profile request of the next page carries the replaced identifier
  await page.route('**/api/v2/account/profile', async route => {
    const stale = await request.get(route.request().url(), { headers: { Cookie: `session=${before}` } })
    await route.fulfill({ response: stale })
  }, { times: 1 })
  await page.reload()
  await expect(page.getByRole('button', { name: 'Security', exact: true })).toBeVisible()
  await expect.poll(() => statuses).toEqual([401, 200])
  await expect(page).toHaveURL(url => url.pathname.startsWith('/account'))
  expect((await (await page.request.get('/api/v2/auth/verify')).json()).data.authenticated).toBe(true)
}

test('a request still carrying the identifier a TOTP confirmation replaced keeps the page signed in', async ({ api, signIn, request }) => {
  const user = await createUser(api, 'viewer')
  const { page, api: own } = await signIn(user.username, user.password)
  await stalePageRequest(page, request, async () => {
    const { secret } = await own.post('/account/2fa/enable')
    await own.post('/account/2fa/confirm', { code: totp(secret) })
  })
})

test('a request still carrying the identifier a password change replaced keeps the page signed in', async ({ api, signIn, request }) => {
  const user = await createUser(api, 'viewer')
  const { page, api: own } = await signIn(user.username, user.password)
  await stalePageRequest(page, request, () =>
    own.post('/account/password', { current_password: user.password, new_password: strongPassword() }))
})

test('a request still carrying the identifier closing the other sessions replaced keeps the page signed in', async ({ api, signIn, request }) => {
  const user = await createUser(api, 'viewer')
  const { page, api: own } = await signIn(user.username, user.password)
  await stalePageRequest(page, request, () => own.post('/account/sessions/revoke-all'))
})
