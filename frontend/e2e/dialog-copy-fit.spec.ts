import { test, expect, uid } from './support/fixtures'
import type { Locator, Page } from '@playwright/test'

// A value shown once, in a dialog on a phone: the value scrolls in its box, its copy button stays on the screen
test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })

// Every copy button of the dialog inside the dialog and the screen, and the dialog without sideways scroll
async function expectCopyButtonsOnScreen(page: Page, dialog: Locator, count: number) {
  const fit = await dialog.evaluate((d) => {
    const box = d.getBoundingClientRect()
    return {
      overflow: d.scrollWidth - d.clientWidth,
      buttons: [...d.querySelectorAll('.command-line > button')].map((b) => {
        const r = b.getBoundingClientRect()
        return { left: r.left, right: r.right, inside: r.left >= box.left - 0.5 && r.right <= box.right + 0.5 && r.right <= innerWidth + 0.5 }
      }),
    }
  })
  expect(fit.buttons).toHaveLength(count)
  expect(fit.buttons.filter((b) => !b.inside), JSON.stringify(fit.buttons)).toEqual([])
  expect(fit.overflow).toBeLessThanOrEqual(1)
  await dialog.locator('.command-line > button').last().click()
  expect(await dialog.evaluate((d) => d.scrollLeft)).toBe(0)
}

test('the SSH enrollment token and its command keep their copy buttons on a phone', async ({ page, api }) => {
  const caName = uid('fit-hosts')
  await api.post('/ssh/cas', { descr: caName, ca_type: 'host', key_type: 'ed25519', allowed_principals: [], allow_any_principal: true })
  await page.goto('/ssh/hosts?view=tokens')
  await page.locator('#ssh-token-new').click()
  const dialog = page.getByRole('dialog', { name: 'New enrollment token' })
  await dialog.getByLabel('Host CA').selectOption({ label: caName })
  await dialog.getByLabel('Host names').fill('storage-node-07.lyon.internal.corp.example.com, storage-node-07')
  await dialog.getByRole('button', { name: 'New enrollment token' }).click()
  await expect(dialog.getByTestId('ssh-token-command')).toBeVisible()
  await expectCopyButtonsOnScreen(page, dialog, 2)
})

test('the EAB key ID and HMAC key keep their copy buttons on a phone', async ({ page, api }) => {
  void api // signs the page in
  await page.goto('/acme?tab=eab')
  await page.getByRole('button', { name: 'New EAB' }).first().click()
  const form = page.getByTestId('eab-create-dialog')
  await form.getByLabel('Label').fill(uid('fit-eab'))
  await form.getByRole('button', { name: 'Generate', exact: true }).click()
  const dialog = page.getByTestId('eab-secret-dialog')
  await expect(dialog.getByText('HMAC Key', { exact: true })).toBeVisible()
  await expectCopyButtonsOnScreen(page, dialog, 2)
})

test('the DNS UPDATE key name, algorithm and secret keep their copy buttons on a phone', async ({ page, api }) => {
  void api // signs the page in
  // An upstream account with its proxy on, and the key the server would create (a 512-bit TSIG secret)
  const account = {
    id: 990001, label: 'Fit upstream', directory_url: 'https://acme.example.test/directory', email: 'ops@example.test',
    account_key_algorithm: 'ES256', is_default: false, proxy_enabled: true, proxy_slug: 'fit-proxy', status: 'valid',
    dns_update_key_count: 0, created_at: new Date().toISOString(),
  }
  const key = {
    id: 1, name: 'fit-proxy-0a1b2c3d.', algorithm: 'hmac-sha512', status: 'active', eab_credential_id: null, notes: null,
    secret: 'q'.repeat(86) + '==', created_at: new Date().toISOString(),
  }
  await page.route('**/api/v2/acme/client/accounts', (route) => route.request().method() === 'GET'
    ? route.fulfill({ json: { data: [account] } }) : route.fallback())
  await page.route(`**/api/v2/acme/client/accounts/${account.id}/dns-update-keys`, (route) => route.fulfill({
    status: route.request().method() === 'POST' ? 201 : 200, json: { data: route.request().method() === 'POST' ? key : [] },
  }))
  await page.goto(`/acme?tab=upstream&item=${account.id}&section=dnsupdate`)
  await page.getByRole('button', { name: 'New key' }).first().click()
  const form = page.getByTestId('dns-update-create-dialog')
  await form.getByRole('button', { name: 'Generate key' }).click()
  const dialog = page.getByTestId('dns-update-secret-dialog')
  await expect(dialog.getByTestId('dns-update-created-secret')).toHaveText(key.secret)
  await expectCopyButtonsOnScreen(page, dialog, 3)
})
