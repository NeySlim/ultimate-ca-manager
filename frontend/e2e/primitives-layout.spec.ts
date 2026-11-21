import { test, expect, createCA, issueCert } from './support/fixtures'

// Base components at the Atelier geometry: 32 px buttons with a 4 px radius (6 px in Aurore), 36 px fields,
// 16 px check boxes, the 760 px dialog and the 220 px theme menu
const EPS = 1
type Box = { x: number; y: number; width: number; height: number }
const box = async (locator): Promise<Box> => {
  const b = await locator.boundingBox()
  expect(b).not.toBeNull()
  return b as Box
}
const near = (value: number, target: number) => expect(Math.abs(value - target)).toBeLessThanOrEqual(EPS)

test.use({ viewport: { width: 1600, height: 1000 } })

test('settings fields, buttons and check lines follow the mockup', async ({ page, api }) => {
  await page.goto('/settings?tab=security')
  const frame = page.locator('#set-title-security')
  await expect(frame).toBeVisible()
  const radius = (await page.evaluate(() => document.documentElement.dataset.theme || '')).startsWith('aurore') ? '6px' : '4px'

  const field = page.locator('#set-sec-security .field input:not([type="checkbox"]):visible').first()
  near((await box(field)).height, 36)
  expect(await field.evaluate((el) => getComputedStyle(el).borderTopLeftRadius)).toBe(radius)

  const check = page.locator('#set-sec-security .checkbox-line input[type="checkbox"]:visible').first()
  const c = await box(check)
  near(c.width, 16)
  near(c.height, 16)

  const button = page.locator('#set-sec-security .btn:visible').first()
  const b = await box(button)
  near(b.height, 32)
  expect(await button.evaluate((el) => getComputedStyle(el).borderTopLeftRadius)).toBe(radius)
  expect(await button.evaluate((el) => getComputedStyle(el).fontSize)).toBe('12px')
  expect(await page.evaluate(() => getComputedStyle(document.body).fontSize)).toBe('13px')
})

test('the export dialog is the 760 px dialog with translated actions', async ({ page, api }) => {
  // Its own certificate, searched: the list may be empty, or changed by tests running beside
  const cert = await issueCert(api, (await createCA(api)).id)
  await page.goto('/certificates')
  await page.getByRole('main').getByRole('searchbox').fill(cert.common_name)
  const row = page.locator('tbody tr').filter({ hasText: cert.common_name })
  await expect(row).toBeVisible()
  await row.getByRole('button', { name: /Export/ }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible()
  near((await box(dialog)).width, 760)
  await expect(dialog.getByRole('button', { name: 'Close' })).toBeVisible()
})

test('the theme menu is 220 px and lists the five choices of the mockup', async ({ page, api }) => {
  await page.goto('/certificates')
  await page.getByRole('button', { name: /^Theme: / }).click()
  const menu = page.getByRole('menu', { name: 'Theme' })
  await expect(menu).toBeVisible()
  // The System line's two lines of text take the height of the mockup's font, once it is loaded
  await page.evaluate(() => document.fonts.ready.then(() => undefined))
  near((await box(menu)).width, 220)
  for (const name of ['System', 'Dark', 'Light', 'Aurore dark', 'Aurore light']) {
    await expect(menu.getByRole('menuitemradio', { name: new RegExp(`^${name}`) })).toBeVisible()
  }
  const item = await box(menu.getByRole('menuitemradio', { name: 'Dark', exact: true }))
  near(item.height, 36)
  // Those five only, as the mockup: no other family below them, the mockup's 202 px
  await expect(menu.getByRole('menuitemradio')).toHaveCount(5)
  await expect(menu.getByRole('group')).toHaveCount(0)
  near((await box(menu)).height, 202)
})
