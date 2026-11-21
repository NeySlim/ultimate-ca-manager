import { test, expect, uid } from './support/fixtures'

// The configuration of a protocol page is a view of its page switch, saved by the form's save bar
const save = (page) => page.locator('#settings-save').click()

test('SCEP: a configuration saved on screen is read back', async ({ page, api }) => {
  await page.goto('/scep-config?tab=config')
  const field = page.getByRole('textbox', { name: /Challenge Password Validity/ })
  const value = String(48 + Math.floor(Math.random() * 100))
  await field.fill(value)
  await save(page)
  await expect.poll(async () => String((await api.get('/scep/config')).challenge_validity ?? JSON.stringify(await api.get('/scep/config')))).toContain(value)

  await page.reload()
  await expect(page.getByRole('textbox', { name: /Challenge Password Validity/ })).toHaveValue(value)
})

test('EST: a configuration saved on screen is read back', async ({ page, api }) => {
  await page.goto('/est-config')
  await page.getByLabel('View', { exact: true }).selectOption('config')
  const enable = page.getByRole('checkbox', { name: /Enable EST Server/ })
  if (!(await enable.isChecked())) await enable.click()
  const user = uid('est').replace(/-/g, '')
  await page.getByLabel('Username').fill(user)
  await save(page)
  await expect.poll(async () => JSON.stringify(await api.get('/est/config'))).toContain(user)

  await page.reload()
  await expect(page.getByLabel('Username')).toHaveValue(user)
})

test('ACME: a local server setting saved on screen is read back', async ({ page, api }) => {
  await page.goto('/acme')
  await page.getByLabel('View', { exact: true }).selectOption('config')
  const issuer = `${uid('caa')}.example.com`
  await page.getByLabel('CAA issuer identifiers').fill(issuer)
  await save(page)
  await expect.poll(async () => JSON.stringify(await api.get('/acme/settings'))).toContain(issuer)

  await page.reload()
  await expect(page.getByLabel('CAA issuer identifiers')).toHaveValue(issuer)
})
