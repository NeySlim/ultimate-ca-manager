import { test, expect, uid, createCA, issueCert } from './support/fixtures'

async function listCAs(api) {
  const data = await api.get('/cas?per_page=500')
  return (Array.isArray(data) ? data : data.items || data.cas) as any[]
}

test('a root then an intermediate created on screen form the hierarchy', async ({ page, api }) => {
  const rootName = uid('root')
  const intName = uid('int')
  await page.goto('/cas')

  await page.getByRole('button', { name: 'Create', exact: true }).click()
  let dialog = page.getByRole('dialog', { name: 'Create CA' })
  await dialog.getByLabel('Common Name (CN)').fill(rootName)
  await dialog.getByRole('button', { name: 'Create CA' }).click()
  await expect(dialog).toBeHidden()
  await expect(page.getByRole('main').getByText(rootName).first()).toBeVisible()

  await page.getByRole('button', { name: 'Create', exact: true }).click()
  dialog = page.getByRole('dialog', { name: 'Create CA' })
  await dialog.getByLabel('Common Name (CN)').fill(intName)
  await dialog.getByLabel('Type', { exact: true }).click()
  await page.getByRole('option', { name: /^Intermediate CA/ }).click()
  await dialog.getByLabel('Parent CA').click()
  await page.getByRole('option', { name: new RegExp(rootName) }).click()
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

test('the hierarchy is a tree driven by the keyboard, the tabs and the search', async ({ page, api }) => {
  const root = await createCA(api)
  const mid = await createCA(api, { parentCAId: root.id })
  const leaf = await createCA(api, { parentCAId: mid.id })
  await issueCert(api, mid.id)
  await page.goto('/cas')

  const tree = page.getByRole('tree', { name: 'Trust hierarchy' })
  const item = (name: string) => tree.getByRole('treeitem', { name, exact: true })
  // Roots open on their first level; the level below stays folded
  await expect(item(root.common_name)).toHaveAttribute('aria-expanded', 'true')
  await expect(item(mid.common_name)).toHaveAttribute('aria-expanded', 'false')
  await expect(item(mid.common_name)).toContainText('1 certificate')
  await expect(item(mid.common_name)).toContainText('1 sub-authority')
  await expect(item(leaf.common_name)).toHaveCount(0)

  // Right unfolds then enters the branch, Enter opens the detail in the dock
  await item(mid.common_name).focus()
  await page.keyboard.press('ArrowRight')
  await expect(item(mid.common_name)).toHaveAttribute('aria-expanded', 'true')
  await page.keyboard.press('ArrowRight')
  await expect(item(leaf.common_name)).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('tabpanel', { name: leaf.common_name }).getByRole('heading', { name: leaf.common_name })).toBeVisible()
  await expect(item(leaf.common_name)).toHaveAttribute('aria-selected', 'true')

  // The tab is part of the address and filters the tree
  await page.getByRole('tab', { name: /^Intermediates/ }).click()
  await expect(page).toHaveURL(/[?&]view=intermediates/)
  await expect(item(leaf.common_name)).toBeVisible()
  await page.getByRole('tab', { name: /^All/ }).click()
  await expect(page).not.toHaveURL(/view=/)

  // The search keeps the branch that leads to what it found
  await page.getByRole('searchbox', { name: /^Name, common name/ }).fill(leaf.common_name)
  await expect(tree.getByRole('treeitem')).toHaveCount(3)

  // The list view: one action on the row, next to the chevron that opens it
  await page.getByRole('button', { name: 'List view' }).click()
  const row = page.getByRole('row', { name: new RegExp(leaf.common_name) })
  await expect(row.getByRole('button', { name: /Download certificate/ })).toBeVisible()
  await expect(row.getByRole('button')).toHaveCount(3)
})
