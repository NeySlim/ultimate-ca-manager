import { test, expect, createCA, issueCert } from './support/fixtures'
import type { Page } from '@playwright/test'

// The overview's widgets in a browser: a compliance rule opens its gaps, a chart reads from the
// keyboard with one tooltip, each chart has its table view, and the page never scrolls sideways.

// Shows the default layout in this page only: another spec may save a preset that hides a card,
// and the shared administrator's preference is never written here.
async function defaultLayout(page: Page) {
  for (const path of ['**/api/v2/auth/verify', '**/api/v2/account/preferences']) {
    await page.route(path, async (route) => {
      if (route.request().method() !== 'GET') return route.continue()
      const response = await route.fetch()
      const body = await response.json()
      const drop = (node: unknown): void => {
        if (Array.isArray(node)) { node.forEach(drop); return }
        if (node && typeof node === 'object') {
          delete (node as Record<string, unknown>).dashboard
          Object.values(node).forEach(drop)
        }
      }
      drop(body)
      await route.fulfill({ response, json: body })
    })
  }
}

test('a compliance rule opens the certificate list filtered on its gap', async ({ page, api }) => {
  const ca = await createCA(api)
  await issueCert(api, ca.id)
  await page.setViewportSize({ width: 1600, height: 1000 })
  await defaultLayout(page)
  await page.goto('/')
  const card = page.getByRole('region', { name: 'Compliance' })
  await expect(card.locator('.sk-body')).toHaveCount(0)
  // The test's RSA 2048 certificate is a gap of the 3072-bit rule
  const rule = card.locator('a.meter[data-check="rsa_below_3072"]')
  await expect(rule).toBeVisible()
  await expect(rule.locator('.track')).toHaveAttribute('role', 'img')
  const href = new URL(await rule.getAttribute('href') as string, 'https://ucm.test')
  const filter = { live: 'true', key_algo_prefix: 'RSA', key_bits_below: '3072' }
  expect(href.pathname).toBe('/certificates')
  expect(Object.fromEntries(href.searchParams)).toEqual(filter)
  await rule.click()
  await expect(page).toHaveURL(/\/certificates\?/)
  expect(Object.fromEntries(new URL(page.url()).searchParams)).toEqual(filter)
  await expect(page.getByRole('heading', { level: 1, name: 'Certificates' })).toBeVisible()
})

test('a chart reads day by day from the keyboard, its tooltip following, Escape closing it', async ({ page, api: _api }) => {
  await page.setViewportSize({ width: 1600, height: 1000 })
  await defaultLayout(page)
  await page.goto('/')
  const card = page.getByRole('region', { name: 'Automation health' })
  await expect(card.locator('.sk-body')).toHaveCount(0)
  const chart = card.locator('[data-protocol="acme"] .mirror')
  await chart.focus()
  const tip = page.getByRole('tooltip')
  await expect(tip).toBeVisible()
  await expect(chart).toHaveAttribute('aria-describedby', await tip.getAttribute('id') as string)
  const today = await tip.locator('h4').textContent()
  await page.keyboard.press('ArrowLeft')
  await expect(tip.locator('h4')).not.toHaveText(today as string)
  await expect(tip.locator('.row')).toHaveCount(2)
  // The tooltip stays inside the window
  const box = await tip.boundingBox()
  expect(box!.x).toBeGreaterThanOrEqual(0)
  expect(box!.x + box!.width).toBeLessThanOrEqual(1600)
  await page.keyboard.press('Escape')
  await expect(page.getByRole('tooltip')).toHaveCount(0)
  await expect(chart).toBeFocused()
})

test('a card shows its figures as a table from its menu, and back', async ({ page, api: _api }) => {
  await page.setViewportSize({ width: 1600, height: 1000 })
  await defaultLayout(page)
  await page.goto('/')
  const card = page.getByRole('region', { name: 'Automation health' })
  await expect(card.locator('.sk-body')).toHaveCount(0)
  await card.getByRole('button', { name: 'Options of the Automation health card' }).click()
  await card.getByRole('button', { name: 'Table view' }).click()
  const table = card.getByRole('table')
  await expect(table).toBeVisible()
  await expect(table.locator('tbody tr')).toHaveCount(30)
  await expect(card.getByRole('button', { name: 'Download as CSV' })).toBeVisible()
  await card.getByRole('button', { name: 'Options of the Automation health card' }).click()
  await card.getByRole('button', { name: 'Chart view' }).click()
  await expect(card.getByRole('table')).toHaveCount(0)
  await expect(card.locator('.mirror').first()).toBeVisible()
})

for (const [name, width, height] of [['1000 px', 1000, 900], ['a phone', 390, 844]] as const) {
  test(`the overview never scrolls sideways at ${name}`, async ({ page, api: _api }) => {
    await page.setViewportSize({ width, height })
    await defaultLayout(page)
    await page.goto('/')
    for (const region of ['Automation health', 'Compliance', 'Latest operations', 'Expiry horizon', 'Issuances by source', 'Authorities and HSM', 'Revocation coverage']) {
      await expect(page.getByRole('region', { name: region })).toBeVisible()
      await expect(page.getByRole('region', { name: region }).locator('.sk-body')).toHaveCount(0)
    }
    const overflow = await page.evaluate(() => {
      const root = document.documentElement
      const scroller = document.getElementById('view-scroll')
      return {
        page: root.scrollWidth - root.clientWidth,
        // The deepest elements that pass the window's right edge, to name the culprit
        past: [...document.querySelectorAll('body *')]
          .filter(el => el.getBoundingClientRect().right > root.clientWidth + 1 && el.getBoundingClientRect().width > 0
            && ![...el.children].some(c => c.getBoundingClientRect().right > root.clientWidth + 1))
          .slice(0, 8).map(el => `${el.tagName.toLowerCase()}.${String(el.className).split(' ').join('.')} in ${el.closest('[data-card], .metric-strip, header, nav')?.className ?? 'page'}`),
        view: scroller ? scroller.scrollWidth - scroller.clientWidth : 0,
        // No widget wider than its card
        wide: [...document.querySelectorAll('.metric-strip .metric, .dash-card .mirror, .dash-card .meter, .dash-card .tl-row, .dash-card .cal, .dash-card .flow, .dash-card .atile, .dash-card .cover')]
          .filter(el => { const card = el.closest('.dash-card, .metric-strip')!.getBoundingClientRect(); const r = el.getBoundingClientRect(); return r.right > card.right + 1 })
          .map(el => el.className),
      }
    })
    expect(overflow.page, overflow.past.join('\n')).toBeLessThanOrEqual(0)
    expect(overflow.view).toBeLessThanOrEqual(0)
    expect(overflow.wide).toEqual([])
  })
}

test('a day of the expiry horizon opens the list of exactly its certificates, and reads from the keyboard', async ({ page, api }) => {
  const ca = await createCA(api)
  const cert = await issueCert(api, ca.id, { validity_days: 20 })
  const day = new Date(cert.valid_to).toISOString().slice(0, 10)
  const week = new Date(Date.parse(`${day}T00:00:00Z`) + 7 * 86400000).toISOString().slice(0, 10)
  await page.setViewportSize({ width: 1600, height: 1000 })
  await defaultLayout(page)
  await page.goto('/')
  const card = page.getByRole('region', { name: 'Expiry horizon' })
  const cell = card.locator(`button.day[data-date="${day}"]`)
  await expect(cell).toBeVisible()

  // The keyboard: the tooltip of the day on focus, a week further with the right arrow, Escape closing it
  await cell.focus()
  await expect(page.getByRole('tooltip')).toBeVisible()
  await page.keyboard.press('ArrowRight')
  await expect(card.locator(`button.day[data-date="${week}"]`)).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('tooltip')).toHaveCount(0)

  await cell.click()
  await expect(cell).toHaveAttribute('aria-pressed', 'true')
  const side = card.getByTestId('horizon-side')
  await expect(side.locator('.side-list a').first()).toBeVisible()
  const count = Number((await side.locator('.fig').textContent())?.trim())
  expect(count).toBeGreaterThanOrEqual(1)
  const listed = page.waitForResponse(r => r.request().method() === 'GET' && /\/api\/v2\/certificates\?/.test(r.url())
    && r.url().includes(`expires_from=${day}`) && !r.url().includes('per_page=5'))
  await side.getByRole('link', { name: /in Certificates$/ }).click()
  await expect(page).toHaveURL(new RegExp(`/certificates\\?.*expires_from=${day}`))
  const body = await (await listed).json()
  expect(body.meta.total).toBe(count)
  // One chip for the interval, its x removing both bounds
  const chip = page.locator('#clear-interval-expires')
  await expect(chip).toBeVisible()
  await chip.click()
  await expect(page).not.toHaveURL(/expires_(from|to)=/)
})
