import { test, expect, uid } from './support/fixtures'

test('a template created on screen is stored with its settings', async ({ page, api }) => {
  const name = uid('tpl')
  await page.goto('/templates')
  await page.getByRole('main').getByRole('button', { name: 'New', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Create Template' })
  await dialog.getByLabel('Template Name').fill(name)
  await dialog.getByLabel('Default Validity (days)').fill('200')
  await dialog.getByLabel('Organization (O)').fill('E2E Org')
  await dialog.getByRole('button', { name: 'Create', exact: true }).click()
  await expect(dialog).toBeHidden()

  await expect(page.getByRole('main').getByText(name).first()).toBeVisible()
  const data = await api.get('/templates?per_page=500')
  const list = (Array.isArray(data) ? data : data.items || data.templates) as any[]
  const tpl = list.find(t => t.name === name)
  expect(tpl).toBeTruthy()
  expect(tpl.validity_days ?? tpl.default_validity_days).toBe(200)
  expect(JSON.stringify(tpl)).toContain('E2E Org')
})
