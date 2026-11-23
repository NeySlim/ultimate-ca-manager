import { test, expect } from './support/fixtures'
import type { Page } from '@playwright/test'

// The graphic review's layout defects of the PKI and protocol pages, measured on a phone: the head's other actions
// reachable from a menu, the EAB setting kept in view, the ACME proxy card no wider than its neighbours
const UPSTREAM = [
  { id: 1, label: "Let's Encrypt", directory_url: 'https://acme-v02.api.letsencrypt.org/directory', email: 'pki-operations@example-corporation.com',
    is_default: true, is_registered: true, proxy_enabled: true, proxy_slug: 'letsencrypt' },
]
const CLIENT_SETTINGS = {
  proxy_acme_account_id: 1, proxy_account_url: 'https://acme-v02.api.letsencrypt.org/acme/acct/290352504290352504290352504', proxy_verify_ssl: true,
}

async function feedProxy(page: Page) {
  await page.route('**/api/v2/acme/client/**', async (route) => {
    const url = new URL(route.request().url())
    if (route.request().method() !== 'GET') return route.continue()
    if (url.pathname === '/api/v2/acme/client/accounts') return route.fulfill({ json: { data: UPSTREAM } })
    if (url.pathname === '/api/v2/acme/client/settings') {
      const response = await route.fetch()
      const body = await response.json()
      body.data = { ...(body.data || {}), ...CLIENT_SETTINGS }
      return route.fulfill({ response, json: body })
    }
    return route.continue()
  })
}

test.describe('phone', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  for (const [path, name] of [['/certificates', 'Import'], ['/ssh/cas', 'Import'], ['/ssh/certificates', 'Import']]) {
    test(`${path}: the head's other actions are in a menu, not lost`, async ({ page, api }) => {
      await page.goto(path)
      const head = page.locator('.page-head')
      await expect(head.locator('.btn.primary')).toBeVisible()
      const more = head.locator('[data-action="page-actions"]')
      await expect(more).toBeVisible()
      await more.click()
      await expect(page.getByRole('dialog').getByRole('button', { name, exact: true })).toBeVisible()
    })
  }

  test('ACME EAB: the « require EAB » box stays on the page', async ({ page, api }) => {
    await page.goto('/acme?tab=eab')
    const box = page.locator('label.eab-required')
    await expect(box).toBeVisible()
    const b = await box.boundingBox()
    expect(b!.width).toBeGreaterThan(40)
    expect(b!.x + b!.width).toBeLessThanOrEqual(390)
  })

  test('ACME client: the proxy card is no wider than the page, its URLs and lists whole', async ({ page, api }) => {
    await feedProxy(page)
    await page.goto('/acme?tab=letsencrypt')
    const card = page.locator('#set-sec-proxy')
    await card.scrollIntoViewIfNeeded()
    await expect(card.locator('.acme-proxy')).toBeVisible()
    const widths = await page.locator('.settings-section').evaluateAll((els) => els.map((el) => Math.round(el.getBoundingClientRect().width)))
    const proxy = await card.evaluate((el) => Math.round(el.getBoundingClientRect().width))
    expect(proxy).toBeLessThanOrEqual(Math.min(...widths))
    // Nothing inside runs past the card's padding box
    const overflow = await card.evaluate((el) => {
      const right = el.getBoundingClientRect().right
      return [...el.querySelectorAll('select, .code-value, .notice, pre, .btn')].filter((n) => n.getBoundingClientRect().right > right + 0.5).length
    })
    expect(overflow).toBe(0)
  })
})
