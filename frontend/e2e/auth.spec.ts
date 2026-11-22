import { test, expect, ADMIN_USER, ADMIN_PASSWORD, Api, createUser } from './support/fixtures'

test.describe('sign-in and session', () => {
  test('password sign-in opens the console and the server knows the session', async ({ page }) => {
    await page.goto('/login')
    await page.getByLabel('Username', { exact: true }).fill(ADMIN_USER)
    await page.getByLabel('Password', { exact: true }).fill(ADMIN_PASSWORD)
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()

    await expect(page.getByRole('heading', { level: 1, name: 'Overview' })).toBeVisible()
    await expect(page.getByRole('button', { name: new RegExp(`^Account: ${ADMIN_USER}, `) })).toBeVisible()
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
    await page.getByRole('button', { name: new RegExp(`^Account: ${ADMIN_USER}, `) }).click()
    await page.getByRole('button', { name: 'Sign out' }).click()

    await expect(page.getByRole('heading', { name: 'Sign in', exact: true })).toBeVisible()
    expect(await api.status('GET', '/certificates')).toBe(401)
  })

  test('Lock in the account menu locks the session, says so, and the password unlocks back to the page', async ({ api, signIn }) => {
    const user = await createUser(api, 'viewer')
    const { page } = await signIn(user.username, user.password)
    await page.goto('/certificates')
    // After a reload the card still knows the session from the server
    await page.reload()
    const account = page.getByRole('button', { name: /^Account: / })
    await account.click()
    const card = page.locator('#user-menu .user-facts')
    await expect(card).toContainText('Sign-in')
    await expect(card).toContainText('password')
    await expect(card).toContainText('Two-factor')
    await expect(card).toContainText('Off')
    await expect(card).toContainText(/Locks after \d+ min of inactivity/)
    await expect(card).toContainText(/Ends /)

    await page.getByRole('button', { name: 'Lock', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Session locked' })).toBeVisible()
    await expect(page.getByText('You locked the session.', { exact: false })).toBeVisible()
    await expect(page.getByText('expired after inactivity', { exact: false })).toHaveCount(0)
    expect((await (await page.request.get('/api/v2/auth/verify')).json()).data.authenticated).toBe(false)

    await page.getByLabel('Password', { exact: true }).fill(user.password)
    await page.getByRole('button', { name: 'Unlock' }).click()
    await expect(page).toHaveURL(url => url.pathname === '/certificates')
    expect((await (await page.request.get('/api/v2/auth/verify')).json()).data.authenticated).toBe(true)
  })

  test('Alt+Shift+L locks every tab of the session', async ({ api, signIn }) => {
    const user = await createUser(api, 'viewer')
    const { page } = await signIn(user.username, user.password)
    await page.goto('/certificates')
    await expect(page.getByRole('button', { name: /^Account: / })).toBeVisible()
    const other = await page.context().newPage()
    await other.goto('/')
    await expect(other.getByRole('button', { name: /^Account: / })).toBeVisible()

    await page.bringToFront()
    await page.locator('body').press('Alt+Shift+L')
    await expect(page.getByRole('heading', { name: 'Session locked' })).toBeVisible()
    await expect(other.getByRole('heading', { name: 'Session locked' })).toBeVisible()
    await expect(other.getByText('You locked the session.', { exact: false })).toBeVisible()
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
  test('French chosen on My account applies, survives a reload and is stored', async ({ api, signIn }) => {
    const user = await createUser(api, 'viewer')
    const { page, api: own } = await signIn(user.username, user.password)
    // The account menu leads to My account, which carries the language
    await page.goto('/')
    await page.getByRole('button', { name: new RegExp(`^Account: ${user.username}, `) }).click()
    await page.getByRole('button', { name: 'My Account' }).click()
    const stored = page.waitForResponse(r => r.url().endsWith('/api/v2/account/preferences') && r.request().method() === 'PUT')
    await page.getByRole('combobox', { name: 'Language' }).selectOption('fr')
    expect((await stored).status()).toBe(200)
    await page.goto('/')

    await expect(page.getByRole('heading', { level: 1, name: 'Vue d’ensemble' })).toBeVisible()
    await expect(page.locator('html')).toHaveAttribute('lang', 'fr')
    await page.reload()
    await expect(page.getByRole('heading', { level: 1, name: 'Vue d’ensemble' })).toBeVisible()
    expect((await own.get('/auth/verify')).preferences.language).toBe('fr')
  })

  test('an account set to a retired theme opens in Atelier, its mode kept and its preference untouched', async ({ api, signIn }) => {
    const user = await createUser(api, 'viewer')
    const { page, api: own } = await signIn(user.username, user.password)
    const prefs = (await own.get('/account/preferences')) || {}
    await own.put('/account/preferences', { ...prefs, theme_family: 'purple', theme_mode: 'light' })
    await page.goto('/')
    await expect(page.getByRole('heading', { level: 1, name: 'Overview' })).toBeVisible()
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'atelier')
    await expect(page.locator('html')).toHaveAttribute('data-mode', 'light')
    await page.getByRole('button', { name: /^Theme: / }).click()
    await expect(page.getByRole('menu', { name: 'Theme' }).getByRole('menuitemradio', { name: 'Light', exact: true }))
      .toHaveAttribute('aria-checked', 'true')
    expect((await own.get('/account/preferences')).theme_family).toBe('purple')
  })

  test('dark mode chosen in the theme menu applies and survives a reload', async ({ api, signIn }) => {
    const user = await createUser(api, 'viewer')
    const { page } = await signIn(user.username, user.password)
    await page.goto('/')
    await page.getByRole('button', { name: /^Theme: / }).click()
    await page.getByRole('menu', { name: 'Theme' }).getByRole('menuitemradio', { name: 'Dark', exact: true }).click()

    await expect(page.locator('html')).toHaveAttribute('data-mode', 'dark')
    await page.reload()
    await expect(page.getByRole('heading', { level: 1, name: 'Overview' })).toBeVisible()
    await expect(page.locator('html')).toHaveAttribute('data-mode', 'dark')
  })
})

