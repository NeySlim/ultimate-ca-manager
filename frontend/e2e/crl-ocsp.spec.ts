import { test, expect, createCA } from './support/fixtures'

test('a CRL generated on screen is published for the CA', async ({ page, api }) => {
  const ca = await createCA(api)
  expect(await api.get(`/crl/${ca.id}`)).toBeFalsy()
  await page.goto('/crl-ocsp')
  await page.getByRole('main').getByRole('cell', { name: new RegExp(ca.common_name) }).click()
  const panel = page.getByRole('complementary').filter({ hasText: ca.common_name })
  await panel.getByRole('button', { name: 'Regenerate CRL' }).click()

  await expect.poll(async () => (await api.get(`/crl/${ca.id}`))?.crl_number).toBe(1)
  await expect(panel.getByText(/No CRL/)).toHaveCount(0)
})

test('OCSP switched on for a CA on screen is stored', async ({ page, api }) => {
  const ca = await createCA(api)
  expect(ca.ocsp_enabled).toBe(false)
  await page.goto('/crl-ocsp')
  const row = page.getByRole('main').getByRole('row', { name: new RegExp(ca.common_name) })
  // Columns: auto-regeneration (CDP), delta CRL, OCSP, AIA
  await row.getByRole('checkbox').nth(2).click()
  await expect.poll(async () => (await api.get(`/cas/${ca.id}`)).ocsp_enabled).toBe(true)
})
