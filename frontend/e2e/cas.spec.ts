import { test, expect, uid } from './support/fixtures'

async function listCAs(api) {
  const data = await api.get('/cas?per_page=500')
  return (Array.isArray(data) ? data : data.items || data.cas) as any[]
}

test('a root then an intermediate created on screen form the hierarchy', async ({ page, api }) => {
  const rootName = uid('root')
  const intName = uid('int')
  await page.goto('/cas')

  await page.getByRole('main').getByRole('button', { name: 'Create', exact: true }).click()
  let dialog = page.getByRole('dialog', { name: 'Create CA' })
  await dialog.getByLabel('Common Name (CN)').fill(rootName)
  await dialog.getByRole('button', { name: 'Create CA' }).click()
  await expect(dialog).toBeHidden()
  await expect(page.getByRole('main').getByText(rootName).first()).toBeVisible()

  await page.getByRole('main').getByRole('button', { name: 'Create', exact: true }).click()
  dialog = page.getByRole('dialog', { name: 'Create CA' })
  await dialog.getByLabel('Common Name (CN)').fill(intName)
  await dialog.getByLabel('Type', { exact: true }).click()
  await page.getByRole('option', { name: /^Intermediate CA/ }).click()
  await dialog.getByLabel('Parent CA').click()
  await page.getByRole('option', { name: new RegExp(rootName) }).click()
  await dialog.getByRole('button', { name: 'Create CA' }).click()
  await expect(dialog).toBeHidden()

  const main = page.getByRole('main')
  await expect(main.getByText(intName).first()).toBeVisible()
  const cas = await listCAs(api)
  const root = cas.find(c => c.common_name === rootName)
  const inter = cas.find(c => c.common_name === intName)
  expect(root?.is_root).toBe(true)
  expect(inter?.caref).toBe(root.refid)
  expect(inter.issuer).toBe(`CN=${rootName}`)
})
