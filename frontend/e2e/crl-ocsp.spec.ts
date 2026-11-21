import { test, expect, createCA } from './support/fixtures'

// A CA opens its detail from its name in the list (the mockup's module list and dock)
const openCa = async (page, ca) => {
  await page.goto('/crl-ocsp')
  await page.getByRole('searchbox').fill(ca.common_name)
  await page.getByRole('main').getByRole('button', { name: new RegExp(`^${ca.common_name}$`) }).first().click()
  return page.getByRole('complementary').filter({ hasText: ca.common_name })
}

test('a CRL generated on screen is published for the CA', async ({ page, api }) => {
  const ca = await createCA(api)
  expect(await api.get(`/crl/${ca.id}`)).toBeFalsy()
  const panel = await openCa(page, ca)
  await panel.getByRole('button', { name: 'Regenerate CRL' }).click()

  await expect.poll(async () => (await api.get(`/crl/${ca.id}`))?.crl_number).toBe(1)
  await expect(panel.getByText(/No CRL/)).toHaveCount(0)
})

test('OCSP switched on for a CA on screen is stored', async ({ page, api }) => {
  const ca = await createCA(api)
  expect(ca.ocsp_enabled).toBe(false)
  const panel = await openCa(page, ca)
  await panel.getByRole('tab', { name: 'OCSP' }).click()
  await panel.getByRole('checkbox', { name: 'Answer OCSP for this authority' }).click()
  await expect.poll(async () => (await api.get(`/cas/${ca.id}`)).ocsp_enabled).toBe(true)
})
