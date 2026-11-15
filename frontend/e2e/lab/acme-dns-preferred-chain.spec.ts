/**
 * Lab: ACME DNS-01 through a DNS provider, with preferred_chain, against Let's Encrypt staging.
 * Needs a UCM with that DNS provider and the staging CA configured, outside the CI:
 *   UCM_LAB=1 UCM_E2E_BASE_URL=https://ucm.example.test:8443 UCM_E2E_ADMIN_PASSWORD='…' \
 *   UCM_LAB_DOMAIN_BASE=lab.example.test npx playwright test e2e/lab/acme-dns-preferred-chain.spec.ts
 */
import { test, expect } from '../support/fixtures'

const LAB_DOMAIN_BASE = process.env.UCM_LAB_DOMAIN_BASE || 'lab.ucm.example.com'
const PREFERRED_CHAIN = 'ISRG Root X1'
const CA_LABEL = /Let's Encrypt Staging/i
const DNS_PROVIDER = new RegExp(process.env.UCM_LAB_DNS_PROVIDER || 'register-gandi', 'i')

test('a staging certificate is issued over DNS-01 with the preferred chain', async ({ page, api }) => {
  test.setTimeout(6 * 60 * 1000)
  const domain = `test-pw-${Date.now()}.${LAB_DOMAIN_BASE}`
  await page.goto('/acme')

  const stagingCard = page.getByRole('main').locator('div').filter({ hasText: CA_LABEL }).first()
  await expect(stagingCard).toBeVisible()
  if (!(await stagingCard.getByText(PREFERRED_CHAIN).isVisible())) {
    await stagingCard.getByRole('button', { name: 'Edit' }).click()
    await page.getByLabel(/preferred chain/i).fill(PREFERRED_CHAIN)
    await page.getByRole('button', { name: 'Save', exact: true }).click()
    await expect(stagingCard.getByText(PREFERRED_CHAIN)).toBeVisible()
  }

  await page.getByRole('button', { name: 'Request Certificate' }).first().click()
  const modal = page.getByRole('dialog')
  await modal.getByRole('textbox').first().fill(domain)
  await modal.getByLabel(/DNS Provider/i).click()
  await page.getByRole('option', { name: DNS_PROVIDER }).click()
  await modal.getByLabel(/Certificate Authority/i).click()
  await page.getByRole('option', { name: CA_LABEL }).click()
  await modal.getByRole('button', { name: 'Request Certificate', exact: true }).click()
  await expect(modal).toBeHidden({ timeout: 30_000 })

  // The order is finalised by the provider's DNS propagation: minutes, not seconds
  await expect.poll(async () => {
    const data = await api.get('/acme/client/orders')
    const orders = (Array.isArray(data) ? data : data.items || data.orders || []) as any[]
    return orders.find(o => JSON.stringify(o).includes(domain))?.status
  }, { timeout: 5 * 60 * 1000, intervals: [3000, 5000, 10000] }).toMatch(/valid|issued/)
})
