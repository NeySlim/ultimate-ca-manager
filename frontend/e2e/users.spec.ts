import { test, expect, createUser, uid, strongPassword, Api } from './support/fixtures'
import { MODULES } from '../src/navigation/registry.js'

const ADMIN_ONLY = MODULES.filter(m => m.guard === 'admin')

test('an operator neither sees nor opens the administration pages', async ({ api, signIn }) => {
  expect(ADMIN_ONLY.map(m => m.id).sort()).toEqual(['logs', 'operations', 'rbac', 'settings', 'users'])
  const operator = await createUser(api, 'operator')
  const { page, api: own } = await signIn(operator.username, operator.password)

  await page.goto('/')
  await page.getByRole('button', { name: 'Modules' }).click()
  const menu = page.getByRole('navigation', { name: 'Product modules' })
  await expect(menu.locator('a[href="/templates"]')).toBeVisible()
  for (const m of ADMIN_ONLY) await expect(menu.locator(`a[href="${m.path}"]`)).toHaveCount(0)

  // The route sends the operator back to the overview
  for (const m of ADMIN_ONLY) {
    await page.goto(m.path)
    await expect(page.getByRole('heading', { level: 1, name: 'Overview' })).toBeVisible()
    await expect(page).toHaveURL(url => url.pathname === '/')
  }
  expect(await own.status('GET', '/users')).toBe(403)
  expect(await own.status('GET', '/rbac/roles')).toBe(403)
})

test('a user created on screen can sign in with its role', async ({ page, api, request }) => {
  const username = uid('user').replace(/-/g, '_')
  const password = strongPassword()
  await page.goto('/users')
  await page.getByRole('main').getByRole('button', { name: 'Create User' }).click()
  const dialog = page.getByRole('dialog', { name: 'Create User' })
  await dialog.getByLabel('Username').fill(username)
  await dialog.getByLabel('Email').fill(`${username}@example.test`)
  await dialog.getByLabel('Password').fill(password)
  await dialog.getByLabel('Role', { exact: true }).selectOption({ label: 'Operator' })
  await dialog.getByRole('button', { name: 'Create', exact: true }).click()
  await expect(dialog).toBeHidden()

  await expect(page.getByRole('main').getByText(username).first()).toBeVisible()
  const own = await Api.login(request, username, password)
  expect((await own.get('/auth/verify')).user).toMatchObject({ username, role: 'operator' })
})

test('a group created on screen is stored', async ({ page, api }) => {
  const name = uid('group')
  await page.goto('/users?tab=groups')
  await page.getByRole('main').getByRole('button', { name: 'Create Group' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('Name', { exact: false }).first().fill(name)
  // The permissions are a grid of named resources and Read, Write, Delete columns
  await dialog.getByRole('checkbox', { name: 'Write: Certificates', exact: true }).check()
  await dialog.getByRole('button', { name: /^Create/ }).click()
  await expect(dialog).toBeHidden()

  await expect(page.getByRole('main').getByRole('cell', { name }).first()).toBeVisible()
  const groups = await api.get('/groups')
  expect(JSON.stringify(groups)).toContain(name)
  expect(JSON.stringify(groups.find((g) => g.name === name)?.permissions)).toContain('write:certificates')
})

test('a custom role created on screen is stored', async ({ page, api }) => {
  const name = uid('role')
  await page.goto('/rbac')
  await page.getByRole('main').getByRole('button', { name: 'Create Role' }).click()
  const dialog = page.getByRole('dialog', { name: 'Create Custom Role' })
  await dialog.getByLabel('Role Name').fill(name)
  await dialog.getByLabel('Description').fill('end-to-end role')
  await dialog.getByRole('button', { name: 'Create', exact: true }).click()
  await expect(dialog).toBeHidden()

  await expect(page.getByRole('main').getByText(name).first()).toBeVisible()
  expect(JSON.stringify(await api.get('/rbac/roles'))).toContain(name)
})

test.describe('a phone of 360 px', () => {
  test.use({ viewport: { width: 360, height: 800 } })

  test('a user\'s profile cuts no word, mutes what is missing, folds the role\'s explanation', async ({ page, api }) => {
    const user = await createUser(api, 'operator')
    await page.goto(`/users?item=${user.id}`)
    const panel = page.locator('#inspector .detail-panel')
    await expect(panel.locator('dl.kv')).toHaveCount(2)
    await expect(panel.locator('dl.props')).toHaveCount(0)
    const row = (term: string) => panel.locator('dl.kv > .row', { has: page.locator('dt', { hasText: term }) })
    // Never signed in: a muted absence; the second factor off: a neutral state
    await expect(row('Last access').locator('dd.absent')).toHaveText('Never')
    await expect(row('Two-factor authentication').locator('dd.v .badge.muted')).toHaveText('Disabled')
    // Every word of a term or a value on one line
    const cut = await panel.evaluate((el) => {
      const out: string[] = []
      for (const cell of el.querySelectorAll('dl.kv > .row > :is(dt, dd.v, dd.absent)')) {
        const walker = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT)
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
          const text = node.textContent || ''
          for (const m of text.matchAll(/\S+/g)) {
            const range = document.createRange()
            range.setStart(node, m.index!)
            range.setEnd(node, m.index! + m[0].length)
            if (new Set([...range.getClientRects()].filter((r) => r.width > 0).map((r) => Math.round(r.top))).size > 1) out.push(m[0])
          }
        }
      }
      return out
    })
    expect(cut).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360)
    // The role alone in its value, its explanation folded, then unfolded on the whole width of the block
    await expect(row('Role').locator('dd.v')).toHaveText('Operator')
    const tip = panel.getByRole('button', { name: 'Help: Role' })
    await expect(tip).toHaveAttribute('aria-expanded', 'false')
    const help = panel.locator(`[id="${await tip.getAttribute('aria-controls')}"]`)
    await expect(help).toBeHidden()
    await tip.click()
    await expect(help).toHaveText('Issue, renew and revoke; neither accounts nor access control.')
    const block = (await row('Role').locator('xpath=..').boundingBox())!
    expect(Math.abs((await help.boundingBox())!.x - block.x)).toBeLessThanOrEqual(1)
    // Security: each factor a state, the exemption included
    await page.locator('#inspector').getByRole('tab', { name: 'Security' }).click()
    await expect(row('2FA exempt').locator('dd.v .badge.muted')).toHaveText('No')
  })
})
