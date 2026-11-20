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
  await dialog.getByLabel('Role', { exact: true }).click()
  await page.getByRole('option', { name: 'Operator', exact: true }).click()
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
  await dialog.getByRole('button', { name: /^Create/ }).click()
  await expect(dialog).toBeHidden()

  await expect(page.getByRole('main').getByRole('cell', { name }).first()).toBeVisible()
  expect(JSON.stringify(await api.get('/groups'))).toContain(name)
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
