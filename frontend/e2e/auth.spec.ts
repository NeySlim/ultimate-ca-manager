import { test, expect, ADMIN_USER, ADMIN_PASSWORD, Api, createUser } from './support/fixtures'

test.describe('sign-in and session', () => {
  test('password sign-in opens the console and the server knows the session', async ({ page }) => {
    await page.goto('/login')
    await page.getByLabel('Username', { exact: true }).fill(ADMIN_USER)
    await page.getByLabel('Password', { exact: true }).fill(ADMIN_PASSWORD)
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()

    await expect(page.getByRole('heading', { level: 1, name: 'Overview' })).toBeVisible()
    await expect(page.getByRole('button', { name: `My Account: ${ADMIN_USER}` })).toBeVisible()
    const verify = await (await page.request.get('/api/v2/auth/verify')).json()
    expect(verify.data).toMatchObject({ authenticated: true, user: { username: ADMIN_USER } })
  })

  test('a wrong password is refused and no session opens', async ({ page, api }) => {
    const user = await createUser(api, 'viewer')
    await page.context().clearCookies()
    await page.goto('/login')
    await page.getByLabel('Username', { exact: true }).fill(user.username)
    await page.getByLabel('Password', { exact: true }).fill(`${user.password}-wrong`)
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()

    await expect(page.getByText(/invalid|incorrect/i).first()).toBeVisible()
    await expect(page).toHaveURL(/\/login/)
    const verify = await (await page.request.get('/api/v2/auth/verify')).json()
    expect(verify.data.authenticated).toBe(false)
  })

  test('sign out from the account menu ends the session', async ({ page, api }) => {
    await page.goto('/')
    await page.getByRole('button', { name: `My Account: ${ADMIN_USER}` }).click()
    await page.getByRole('button', { name: 'Sign Out' }).click()

    await expect(page.getByRole('heading', { name: 'Sign in', exact: true })).toBeVisible()
    expect(await api.status('GET', '/certificates')).toBe(401)
  })

  test('a session ended by the server sends the next action back to the sign-in page', async ({ api, signIn, request }) => {
    const user = await createUser(api, 'viewer')
    const { page } = await signIn(user.username, user.password)
    await page.goto('/')
    await expect(page.getByRole('heading', { level: 1, name: 'Overview' })).toBeVisible()
    // Another session of the account closes this one, as an expiry does on the server
    const other = await Api.login(request, user.username, user.password)
    await other.post('/account/sessions/revoke-all')

    // The next page asked for, or a request the console makes first, leads to the sign-in page;
    // in the second case the console's own redirect aborts this navigation
    await page.goto('/certificates').catch(e => { if (!String(e).includes('ERR_ABORTED')) throw e })
    await expect(page.getByRole('heading', { name: 'Sign in', exact: true })).toBeVisible()
    await expect(page).toHaveURL(url => url.pathname === '/login')
    expect((await (await page.request.get('/api/v2/auth/verify')).json()).data.authenticated).toBe(false)
  })
})

test.describe('preferences', () => {
  test('French chosen in the account menu applies, survives a reload and is stored', async ({ api, signIn }) => {
    const user = await createUser(api, 'viewer')
    const { page, api: own } = await signIn(user.username, user.password)
    await page.goto('/')
    await page.getByRole('button', { name: `My Account: ${user.username}` }).click()
    const stored = page.waitForResponse(r => r.url().endsWith('/api/v2/account/preferences') && r.request().method() === 'PUT')
    await page.getByRole('group', { name: 'Language' }).getByRole('button', { name: 'Français' }).click()
    expect((await stored).status()).toBe(200)

    await expect(page.getByRole('heading', { level: 1, name: "Vue d'ensemble" })).toBeVisible()
    await expect(page.locator('html')).toHaveAttribute('lang', 'fr')
    await page.reload()
    await expect(page.getByRole('heading', { level: 1, name: "Vue d'ensemble" })).toBeVisible()
    expect((await own.get('/auth/verify')).preferences.language).toBe('fr')
  })

  test('dark mode chosen in the theme menu applies and survives a reload', async ({ api, signIn }) => {
    const user = await createUser(api, 'viewer')
    const { page } = await signIn(user.username, user.password)
    await page.goto('/')
    await page.getByRole('button', { name: 'Theme', exact: true }).click()
    await page.getByRole('menu', { name: 'Theme' }).getByRole('menuitemradio', { name: 'Dark', exact: true }).click()

    await expect(page.locator('html')).toHaveAttribute('data-mode', 'dark')
    await page.reload()
    await expect(page.getByRole('heading', { level: 1, name: 'Overview' })).toBeVisible()
    await expect(page.locator('html')).toHaveAttribute('data-mode', 'dark')
  })
})

