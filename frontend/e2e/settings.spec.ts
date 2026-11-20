import { test, expect, uid } from './support/fixtures'

test('a general setting saved on screen is read back', async ({ page, api }) => {
  const host = uid('syslog')
  await page.goto('/settings')
  await page.getByLabel('Syslog hostname').fill(host)
  await page.getByTestId('sf-savebar').getByRole('button', { name: 'Save', exact: true }).click()
  await expect.poll(async () => JSON.stringify(await api.get('/settings/general'))).toContain(host)

  await page.reload()
  await expect(page.getByLabel('Syslog hostname')).toHaveValue(host)
})
