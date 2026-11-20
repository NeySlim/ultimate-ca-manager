import { test, expect } from './support/fixtures'

// Base components at the Atelier geometry: 32 px buttons with a 4 px radius, 36 px fields,
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
  const frame = page.locator('#sf-title-security')
  await expect(frame).toBeVisible()

  const field = page.locator('.sf-body .ui-control:visible').first()
  near((await box(field)).height, 36)
  expect(await field.evaluate((el) => getComputedStyle(el).borderTopLeftRadius)).toBe('4px')

  const check = page.locator('.sf-body .ui-check-line input[type="checkbox"]:visible').first()
  const c = await box(check)
  near(c.width, 16)
  near(c.height, 16)

  const button = page.locator('main .ui-btn:visible').first()
  const b = await box(button)
  near(b.height, 32)
  expect(await button.evaluate((el) => getComputedStyle(el).borderTopLeftRadius)).toBe('4px')
  expect(await button.evaluate((el) => getComputedStyle(el).fontSize)).toBe('12px')
  expect(await page.evaluate(() => getComputedStyle(document.body).fontSize)).toBe('13px')
})

test('the export dialog is the 760 px dialog with translated actions', async ({ page, api }) => {
  await page.goto('/certificates')
  const row = page.locator('tbody tr').first()
  await expect(row).toBeVisible()
  await row.getByRole('button', { name: /Export/ }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible()
  near((await box(dialog)).width, 760)
  await expect(dialog.getByRole('button', { name: 'Close' })).toBeVisible()
})

test('the theme menu is 220 px and lists the five choices of the mockup', async ({ page, api }) => {
  await page.goto('/certificates')
  await page.getByRole('button', { name: 'Theme', exact: true }).click()
  const menu = page.getByRole('menu', { name: 'Theme' })
  await expect(menu).toBeVisible()
  near((await box(menu)).width, 220)
  for (const name of ['System', 'Dark', 'Light', 'Aurore dark', 'Aurore light']) {
    await expect(menu.getByRole('menuitemradio', { name: new RegExp(`^${name}`) })).toBeVisible()
  }
  const item = await box(menu.getByRole('menuitemradio', { name: 'Dark', exact: true }))
  near(item.height, 36)
})
