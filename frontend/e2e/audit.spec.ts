import { test, expect, createCA } from './support/fixtures'

test('an action of the test appears in the audit log', async ({ page, api }) => {
  const ca = await createCA(api)
  await page.goto('/audit')
  await page.getByRole('main').getByRole('textbox').first().fill(ca.common_name)
  const row = page.getByRole('main').getByRole('row', { name: new RegExp(ca.common_name) }).first()
  await expect(row).toBeVisible()
  await expect(row).toContainText('admin')

  const logs = await api.get(`/audit/logs?search=${encodeURIComponent(ca.common_name)}`)
  const list = (Array.isArray(logs) ? logs : logs.items || logs.logs) as any[]
  expect(list.some(l => l.resource_name === ca.common_name && l.username === 'admin')).toBe(true)
})
