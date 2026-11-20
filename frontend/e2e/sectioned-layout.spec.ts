import { test, expect } from './support/fixtures'

// Real geometry of the sectioned pages at 1600 px, as the Atelier form with a table of
// contents draws it: 200 px contents, 24 px gap, frames to the right gutter
const EPS = 1
const W = 1600
const H = 1000
const GUTTER = 24
const TOC = 200
type Box = { x: number; y: number; width: number; height: number }
const box = async (locator): Promise<Box> => {
  const b = await locator.boundingBox()
  expect(b).not.toBeNull()
  return b as Box
}

test.use({ viewport: { width: W, height: H } })

const PAGES = [
  { path: '/settings', toc: 'Settings sections', first: 'General' },
  { path: '/account', toc: 'Account sections', first: 'Profile' },
  { path: '/tools', toc: 'Tools', first: 'SSL Checker' },
  { path: '/operations', toc: 'Operations', first: 'Import' },
]

for (const { path, toc, first } of PAGES) {
  test(`${path} puts its contents left of full-width frames`, async ({ page, api }) => {
    await page.goto(path)
    const nav = page.getByRole('navigation', { name: toc, exact: true })
    const frame = page.getByRole('region', { name: first, exact: true })
    await expect(frame).toBeVisible()
    const n = await box(nav)
    const f = await box(frame)
    expect(Math.abs(n.x - GUTTER)).toBeLessThanOrEqual(EPS)
    expect(Math.abs(n.width - TOC)).toBeLessThanOrEqual(EPS)
    expect(Math.abs(f.x - (GUTTER + TOC + GUTTER))).toBeLessThanOrEqual(EPS)
    expect(Math.abs(f.x + f.width - (W - GUTTER))).toBeLessThanOrEqual(EPS)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  })
}

test('the settings save bar stays above the status bar and counts a change', async ({ page, api }) => {
  await page.goto('/settings')
  const bar = page.getByTestId('sf-savebar')
  await expect(bar).toBeVisible()
  const b = await box(bar)
  const status = await box(page.getByRole('contentinfo'))
  // 24 px above the status bar, the content scrolls in that band (the mockup's scroll-view padding)
  expect(Math.abs(status.y - (b.y + b.height) - 24)).toBeLessThanOrEqual(EPS)
  await expect(bar.getByRole('button', { name: 'Save', exact: true })).toBeDisabled()

  await page.getByLabel('Syslog hostname').fill(`e2e-${Date.now()}`)
  await expect(bar.getByRole('button', { name: 'Save', exact: true })).toBeEnabled()
  await bar.getByRole('button', { name: 'Undo changes' }).click()
  await expect(bar.getByRole('button', { name: 'Save', exact: true })).toBeDisabled()
})

test('a link to ?tab= lands the settings page on that frame', async ({ page, api }) => {
  await page.goto('/settings?tab=email')
  const title = page.locator('#sf-title-email')
  await expect(title).toBeFocused()
  const t = await box(title)
  expect(t.y).toBeGreaterThanOrEqual(0)
  expect(t.y).toBeLessThan(H / 2)
})

test('every settings section is in view in the table of contents, no title cut', async ({ page, api }) => {
  await page.goto('/settings')
  const nav = page.getByRole('navigation', { name: 'Settings sections', exact: true })
  await expect(nav).toBeVisible()
  const status = await box(page.getByRole('contentinfo'))
  const links = nav.getByRole('link')
  expect(await links.count()).toBe(19)
  for (const item of [...await links.all(), ...await nav.locator('.sf-toc-group-title').all()]) {
    const r = await box(item)
    expect(r.y + r.height).toBeLessThanOrEqual(status.y - 24 + EPS)
  }
  expect(await nav.evaluate((el) => el.scrollHeight <= el.clientHeight)).toBe(true)
})
