import { test, expect, uid } from './support/fixtures'

test('a general setting saved on screen is read back', async ({ page, api }) => {
  const host = uid('syslog')
  await page.goto('/settings')
  await page.getByLabel('Syslog hostname').fill(host)
  await page.locator('#settings-savebar').getByRole('button', { name: 'Save', exact: true }).click()
  await expect.poll(async () => JSON.stringify(await api.get('/settings/general'))).toContain(host)

  await page.reload()
  await expect(page.getByLabel('Syslog hostname')).toHaveValue(host)
})

test('a checkbox of a dialog form sits beside its words', async ({ page, api }) => {
  void api
  await page.goto('/settings?tab=sso')
  await page.locator('#set-sec-sso li').first().getByRole('button', { name: /^(Configure|Edit)$/ }).click()
  const box = page.locator('dialog[open]').getByRole('checkbox', { name: 'Enable provider' })
  await expect(box).toBeVisible()
  const [b, l] = await box.evaluate((el) => [el.getBoundingClientRect().toJSON(), el.closest('label')!.getBoundingClientRect().toJSON()])
  // One line: the box on the label's row, the words to its right
  expect(l.height).toBeLessThan(44)
  expect(b.left - l.left).toBeLessThan(2)
  expect(b.top + b.height / 2).toBeGreaterThan(l.top)
  expect(b.top + b.height / 2).toBeLessThan(l.bottom)
})
