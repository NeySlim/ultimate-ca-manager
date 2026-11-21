import { test, expect, uid, createCA, issueCert } from './support/fixtures'

async function listCAs(api) {
  const data = await api.get('/cas?per_page=500')
  return (Array.isArray(data) ? data : data.items || data.cas) as any[]
}

test('a root then an intermediate created on screen form the hierarchy', async ({ page, api }) => {
  const rootName = uid('root')
  const intName = uid('int')
  await page.goto('/cas')

  await page.getByRole('button', { name: 'Create CA', exact: true }).click()
  let dialog = page.getByRole('dialog', { name: 'Create a certificate authority' })
  await dialog.getByLabel('Common Name (CN)').fill(rootName)
  await dialog.getByRole('button', { name: 'Create CA' }).click()
  await expect(dialog).toBeHidden()
  // The new authority is the one the side panel shows
  await expect(page.getByRole('complementary', { name: rootName })).toBeVisible()

  await page.getByRole('button', { name: 'Create CA', exact: true }).click()
  dialog = page.getByRole('dialog', { name: 'Create a certificate authority' })
  await dialog.getByLabel('Common Name (CN)').fill(intName)
  await dialog.getByLabel('Type', { exact: true }).selectOption('intermediate')
  const parent = dialog.getByLabel('Parent CA')
  await parent.selectOption({ label: (await parent.locator('option', { hasText: rootName }).first().textContent()) || rootName })
  await dialog.getByRole('button', { name: 'Create CA' }).click()
  await expect(dialog).toBeHidden()

  // The new root is a node of the tree, open on the intermediate it has just signed
  const tree = page.getByRole('tree', { name: 'Trust hierarchy' })
  const rootItem = tree.getByRole('treeitem', { name: rootName, exact: true })
  await expect(rootItem).toHaveAttribute('aria-expanded', 'true')
  await expect(rootItem.getByRole('treeitem', { name: intName, exact: true })).toBeVisible()
  await expect(rootItem).toContainText('1 sub-authority')
  const cas = await listCAs(api)
  const root = cas.find(c => c.common_name === rootName)
  const inter = cas.find(c => c.common_name === intName)
  expect(root?.is_root).toBe(true)
  expect(inter?.caref).toBe(root.refid)
  expect(inter.issuer).toBe(`CN=${rootName}`)
})

test('the hierarchy is a tree driven by the keyboard, the filters and the search', async ({ page, api }) => {
  const root = await createCA(api)
  const mid = await createCA(api, { parentCAId: root.id })
  const leaf = await createCA(api, { parentCAId: mid.id })
  await issueCert(api, mid.id)
  await page.goto(`/cas?authority=${root.id}`)

  const tree = page.getByRole('tree', { name: 'Trust hierarchy' })
  const item = (name: string) => tree.getByRole('treeitem', { name, exact: true })
  // Roots open on their first level; the level below stays folded
  await expect(item(root.common_name)).toHaveAttribute('aria-expanded', 'true')
  await expect(item(mid.common_name)).toHaveAttribute('aria-expanded', 'false')
  await expect(item(mid.common_name)).toContainText('1 certificate')
  await expect(item(mid.common_name)).toContainText('1 sub-authority')
  await expect(item(leaf.common_name)).toHaveCount(0)

  // Right unfolds then enters the branch, Enter shows the authority in the side panel
  await item(mid.common_name).focus()
  await page.keyboard.press('ArrowRight')
  await expect(item(mid.common_name)).toHaveAttribute('aria-expanded', 'true')
  await page.keyboard.press('ArrowRight')
  await expect(item(leaf.common_name)).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('complementary', { name: leaf.common_name })).toBeVisible()
  await expect(page).toHaveURL(new RegExp(`[?&]authority=${leaf.id}`))
  await expect(item(leaf.common_name)).toHaveAttribute('aria-selected', 'true')
  // Its issuer is a link that selects it
  await page.getByRole('complementary', { name: leaf.common_name }).getByRole('button', { name: mid.common_name, exact: true }).click()
  await expect(page.getByRole('complementary', { name: mid.common_name })).toBeVisible()

  // The filter is part of the address and filters the tree
  const filters = page.getByRole('group', { name: 'Filter the authorities' })
  await filters.getByRole('button', { name: /^Intermediates/ }).click()
  await expect(page).toHaveURL(/[?&]view=intermediates/)
  await expect(item(leaf.common_name)).toBeVisible()
  await filters.getByRole('button', { name: /^All/ }).click()
  await expect(page).not.toHaveURL(/view=/)

  // The search keeps the branch that leads to what it found
  await page.getByRole('searchbox', { name: 'Search the authorities' }).fill(leaf.common_name)
  await expect(tree.getByRole('treeitem')).toHaveCount(3)

  // The list view: one action on the row, next to the chevron that shows it
  await page.getByRole('group', { name: 'Display' }).getByRole('button', { name: 'List' }).click()
  const row = page.getByRole('row', { name: new RegExp(leaf.common_name) })
  await expect(row.getByRole('button', { name: /Download certificate/ })).toBeVisible()
  await expect(row.getByRole('button')).toHaveCount(3)
})

test('an authority shows its CRL, its revoked count and its actions beside the tree', async ({ page, api }) => {
  const root = await createCA(api)
  await page.goto(`/cas?authority=${root.id}`)
  const side = page.getByRole('complementary', { name: root.common_name })
  await expect(side.getByRole('heading', { name: 'Revocation' })).toBeVisible()
  await expect(side.getByText('Of which revoked')).toBeVisible()
  // A root that holds its key issues
  await expect(side.getByRole('button', { name: 'Issue with this CA' })).toBeEnabled()
  await side.getByRole('button', { name: 'Other actions' }).click()
  const menu = page.getByRole('dialog', { name: 'Authority actions' })
  await expect(menu.getByRole('button', { name: /Export/ })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(menu).toHaveCount(0)
  await side.getByRole('button', { name: 'View certificates' }).click()
  await expect(page).toHaveURL(new RegExp(`/certificates\\?ca_id=${root.id}`))
})
