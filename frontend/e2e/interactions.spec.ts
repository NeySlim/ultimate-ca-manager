import { test, expect, createCA, createUser, issueCert } from './support/fixtures'
import type { Page, Locator } from '@playwright/test'

// Interactions of the console: a row opens its object from anywhere on it, the protocol views past the room go
// into « More » beside the right dock, a list and its inspector scroll apart, one bar panel at a time and always on
// top, the account menu's card, and the Aurore theme following the system.
const EPS = 1
type Box = { x: number; y: number; width: number; height: number }
const box = async (locator: Locator): Promise<Box> => {
  const b = await locator.boundingBox()
  expect(b).not.toBeNull()
  return b as Box
}
// Nothing covers the centre of the locator: a click there reaches it
const onTop = (locator: Locator) => locator.evaluate((el) => {
  const r = el.getBoundingClientRect()
  const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)
  return !!hit && (hit === el || el.contains(hit))
})

// The page alone reads the dock anchored at the right: the shared account's preference is never written
async function dockRight(page: Page) {
  const inspector = { position: 'right', height: 278, width: 460 }
  await page.route('**/api/v2/account/preferences', async (route) => {
    if (route.request().method() !== 'GET') return route.fulfill({ status: 200, contentType: 'application/json', body: '{"data":{}}' })
    const response = await route.fetch()
    const body = await response.json()
    body.data = { ...(body.data || {}), inspector }
    return route.fulfill({ response, json: body })
  })
  await page.route('**/api/v2/auth/verify', async (route) => {
    const response = await route.fetch()
    const body = await response.json()
    if (body?.data) body.data.preferences = { ...(body.data.preferences || {}), inspector }
    return route.fulfill({ response, json: body })
  })
}

/** A cell of the row that is plain text (no control in it), clicked at its centre. */
async function clickPlainCell(row: Locator) {
  const index = await row.evaluate((tr) => [...tr.children].findIndex((td) => !td.classList.contains('check-col')
    && !td.querySelector('button, a, input, label') && (td.textContent || '').trim()))
  expect(index).toBeGreaterThanOrEqual(0)
  const cell = row.locator('td').nth(index)
  await expect(cell).toHaveCSS('cursor', 'pointer')
  await cell.click()
}

test.describe('a row opens its object from anywhere on it', () => {
  test.use({ viewport: { width: 1600, height: 1000 } })

  test('certificates, templates and users', async ({ page, api }) => {
    const cert = await issueCert(api, (await createCA(api)).id)
    await page.goto('/certificates')
    await page.getByRole('main').getByRole('searchbox').fill(cert.common_name)
    const row = page.locator('tbody tr').filter({ hasText: cert.common_name })
    await expect(row).toHaveCount(1)
    await clickPlainCell(row)
    await expect(page.locator('#inspector')).toBeVisible()
    await expect(row).toHaveClass(/opened/)

    for (const path of ['/templates', '/users']) {
      await page.goto(path)
      const first = page.locator('tbody tr').first()
      await expect(first.locator('button.entity-name')).toBeVisible()
      await clickPlainCell(first)
      await expect(page.locator('#inspector')).toBeVisible()
      await expect(first).toHaveClass(/opened/)
    }
  })
})

test.describe('the ACME views beside the right dock at 1406 px', () => {
  test.use({ viewport: { width: 1406, height: 900 } })

  test('the views past the room are in « More », the shown one stays in the row', async ({ page, api }) => {
    await dockRight(page)
    // One account to open, fed to the page alone
    await page.route('**/api/v2/acme/accounts*', (route) => route.request().method() !== 'GET' ? route.continue() : route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ data: [{ id: 1, account_id: 'e2e-account', contact: ['mailto:ops@example.com'], status: 'valid', orders_count: 0, key_type: 'EC-P256', created_at: new Date().toISOString() }], meta: { total: 1, page: 1, per_page: 100 } }),
    }))
    await page.goto('/acme')
    await page.locator('tbody tr').first().locator('button.entity-name').click()
    await expect(page.locator('#app.dock-right')).toHaveCount(1)
    await expect(page.locator('#inspector')).toBeVisible()
    const tabs = page.getByRole('tablist', { name: 'View' })
    expect(await tabs.evaluate((el) => el.scrollWidth <= el.clientWidth + 1)).toBe(true)
    const shown = await tabs.getByRole('tab').count()
    expect(shown).toBeLessThan(11)
    const frame = await box(page.locator('.page-views'))
    const more = page.getByRole('button', { name: 'More', exact: true })
    const m = await box(more)
    expect(m.x + m.width).toBeLessThanOrEqual(frame.x + frame.width + EPS)
    await more.click()
    const menu = page.getByRole('menu', { name: 'Other views' })
    // The row settles once the dock's transition ends: every view is either in it or in the menu
    await expect.poll(async () => (await tabs.getByRole('tab').count()) + (await menu.getByRole('menuitem').count())).toBe(11)
    await expect(menu.getByRole('menuitem')).not.toHaveCount(0)
    expect(await onTop(menu)).toBe(true)
    await menu.getByRole('menuitem', { name: /^Issued certificates/ }).click()
    await expect(tabs.getByRole('tab', { name: /^Issued certificates/ })).toHaveAttribute('aria-selected', 'true')
    expect(await onTop(tabs.getByRole('tab', { name: /^Issued certificates/ }))).toBe(true)
  })
})

test.describe('a list and its inspector scroll apart', () => {
  test.use({ viewport: { width: 1600, height: 640 } })

  /** Scrolls `list` to its end: the inspector stays where it was and the page itself does not scroll. */
  async function scrollApart(page: Page, list: Locator, inspector: Locator) {
    const before = await box(inspector)
    const scrolled = await list.evaluate((el) => { el.scrollTop = el.scrollHeight; return el.scrollTop })
    expect(scrolled).toBeGreaterThan(0)
    const after = await box(inspector)
    expect(Math.abs(after.y - before.y)).toBeLessThanOrEqual(EPS)
    expect(await page.evaluate(() => document.scrollingElement!.scrollTop)).toBe(0)
    const view = page.locator('#view-scroll')
    if (await view.count()) expect(await view.evaluate((el) => el.scrollTop)).toBe(0)
  }

  test('authorities: the list or the hierarchy, and the side panel', async ({ page, api }) => {
    const roots = []
    for (let i = 0; i < 14; i++) roots.push(await createCA(api))
    await page.goto(`/cas?authority=${roots[0].id}`)
    const side = page.locator('aside.ca-side')
    await expect(side).toBeVisible()
    await page.locator('[data-view-mode="list"]').click()
    await scrollApart(page, page.locator('#ca-list-scroll'), side)
    // The panel scrolls inside itself when it is taller than the view
    expect(await side.evaluate((el) => getComputedStyle(el).overflowY)).toBe('auto')
    await page.locator('[data-view-mode="tree"]').click()
    await scrollApart(page, page.locator('.ca-tree-panel'), side)
  })

  test('certificates and templates: the list and the dock', async ({ page, api }) => {
    const ca = await createCA(api)
    for (let i = 0; i < 8; i++) await issueCert(api, ca.id)
    for (const path of ['/certificates', '/templates']) {
      await page.goto(path)
      await page.locator('tbody tr').first().locator('button.entity-name').click()
      const dock = page.locator('#inspector')
      await expect(dock).toBeVisible()
      await scrollApart(page, page.locator('.page-content .table-scroll'), dock)
    }
  })
})

test.describe('the panels of the bar', () => {
  test.use({ viewport: { width: 1600, height: 1000 } })
  const PANELS = {
    language: { button: '#language-button', panel: '#language-menu' },
    theme: { button: '#theme-button', panel: '#theme-menu' },
    notifications: { button: '#notif-button', panel: '#notif-panel' },
    account: { button: '#user-button', panel: '#user-menu' },
  }
  const names = Object.keys(PANELS) as (keyof typeof PANELS)[]
  const pairs = names.flatMap((a) => names.filter((b) => b !== a).map((b) => [a, b] as const))

  test('one open at a time, the open one on top of everything', async ({ page, api }) => {
    await page.goto('/certificates')
    for (const [a, b] of pairs) {
      await page.locator(PANELS[a].button).click()
      await expect(page.locator(PANELS[a].panel)).toBeVisible()
      await page.locator(PANELS[b].button).click()
      await expect(page.locator(PANELS[b].panel)).toBeVisible()
      await expect(page.locator(PANELS[a].panel)).toBeHidden()
      await expect(page.locator(PANELS[a].button)).toHaveAttribute('aria-expanded', 'false')
      expect(await onTop(page.locator(PANELS[b].panel)), `${a} then ${b}`).toBe(true)
      await page.keyboard.press('Escape')
      await expect(page.locator(PANELS[b].panel)).toBeHidden()
    }
  })

  test('the help and the palette close the open menu; a click outside and the cross close the notifications', async ({ page, api }) => {
    await page.goto('/certificates')
    await page.locator('#theme-button').click()
    await page.getByRole('button', { name: 'Search and navigate' }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(page.locator('#theme-menu')).toBeHidden()
    await page.keyboard.press('Escape')
    await page.locator('#notif-button').click()
    await expect(page.locator('#notif-panel')).toBeVisible()
    await page.getByRole('heading', { level: 1 }).click()
    await expect(page.locator('#notif-panel')).toBeHidden()
    await page.locator('#notif-button').click()
    await page.locator('#theme-button').click()
    await page.locator('#notif-button').click()
    await expect(page.locator('#theme-menu')).toBeHidden()
    await page.locator('#notif-close').click()
    await expect(page.locator('#notif-panel')).toBeHidden()
  })
})

test.describe('the account menu', () => {
  test.use({ viewport: { width: 1600, height: 1000 } })

  test('opens on the account card: the avatar beside the name, the facts, Lock and Sign out apart', async ({ page, api }) => {
    await page.goto('/certificates')
    await page.locator('#user-button').click()
    const menu = page.locator('#user-menu')
    const avatar = menu.locator('.auth-user .avatar')
    const name = menu.locator('#user-name')
    await expect(avatar).toHaveText(await page.locator('#user-button').innerText())
    const a = await box(avatar)
    const n = await box(name)
    expect(a.x + a.width).toBeLessThan(n.x)
    expect(n.y).toBeLessThan(a.y + a.height)
    await expect(menu.locator('dl.user-facts dt').first()).toBeVisible()
    await expect(menu.getByRole('separator')).toBeVisible()
    // Lock and Sign out sit apart, after the separator
    expect(await menu.locator('[role="separator"] + #user-lock + #user-logout').count()).toBe(1)
  })
})

test('Aurore with System follows the system between dark and light', async ({ api, signIn }) => {
  const user = await createUser(api, 'viewer')
  const { page } = await signIn(user.username, user.password)
  await page.emulateMedia({ colorScheme: 'dark' })
  await page.goto('/')
  const theme = page.getByRole('button', { name: /^Theme: / })
  await theme.click()
  await page.getByRole('menuitemradio', { name: 'Aurore', exact: true }).click()
  await theme.click()
  await page.getByRole('menuitemradio', { name: /^System/ }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'aurore')
  await expect(page.locator('html')).toHaveAttribute('data-mode', 'dark')
  await page.emulateMedia({ colorScheme: 'light' })
  await expect(page.locator('html')).toHaveAttribute('data-mode', 'light')
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'aurore')
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'aurore')
  await expect(page.locator('html')).toHaveAttribute('data-mode', 'light')
})
