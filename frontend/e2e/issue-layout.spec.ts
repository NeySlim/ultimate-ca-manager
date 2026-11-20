import { test, expect, createCA } from './support/fixtures'

// Real geometry of the issue dialog of the Atelier at 1600 x 1000 and on a phone: jsdom measures nothing
const EPS = 1.5
type Box = { x: number; y: number; width: number; height: number }
const box = async (locator): Promise<Box> => {
  const b = await locator.boundingBox()
  expect(b).not.toBeNull()
  return b as Box
}

test.describe('desktop', () => {
  test.use({ viewport: { width: 1600, height: 1000 } })

  test('the issue dialog lays out its two columns and its steps as the Atelier does', async ({ page, api }) => {
    const ca = await createCA(api)
    await page.goto('/certificates?action=create')
    const dialog = page.getByRole('dialog', { name: 'Issue a certificate' })
    await expect(dialog).toBeVisible()
    await dialog.getByLabel('Authority').selectOption(String(ca.id))

    // 920 px wide, centred, 20 px from the top when it fills the height
    const d = await box(dialog)
    expect(Math.abs(d.width - 920)).toBeLessThanOrEqual(EPS)
    expect(Math.abs(d.x - 340)).toBeLessThanOrEqual(EPS)
    expect(d.y).toBeGreaterThanOrEqual(20 - EPS)

    // Fields on the left, 250 px of what is imposed on the right, 26 px apart
    const hint = await box(dialog.locator('.iss-hint'))
    const fields = await box(dialog.locator('.iss-fields'))
    expect(Math.abs(hint.width - 250)).toBeLessThanOrEqual(EPS)
    expect(Math.abs(hint.x - (fields.x + fields.width + 26))).toBeLessThanOrEqual(EPS)
    expect(Math.abs(fields.x - (d.x + 25))).toBeLessThanOrEqual(EPS)

    // Template and authority side by side, 36 px high; the common name across both
    const tpl = await box(dialog.getByLabel('Template'))
    const auth = await box(dialog.getByLabel('Authority'))
    const cn = await box(dialog.getByLabel('Common name'))
    expect(Math.abs(tpl.y - auth.y)).toBeLessThanOrEqual(EPS)
    expect(Math.abs(tpl.height - 36)).toBeLessThanOrEqual(EPS)
    expect(Math.abs(auth.x - (tpl.x + tpl.width + 16))).toBeLessThanOrEqual(EPS)
    expect(Math.abs(cn.width - fields.width)).toBeLessThanOrEqual(EPS)

    // Two key source cards of equal width, 10 px apart
    const cards = dialog.locator('.iss-choice')
    await expect(cards).toHaveCount(2)
    const [a, b] = [await box(cards.nth(0)), await box(cards.nth(1))]
    expect(Math.abs(a.width - b.width)).toBeLessThanOrEqual(EPS)
    expect(Math.abs(b.x - (a.x + a.width + 10))).toBeLessThanOrEqual(EPS)

    // A SAN row: 120 px type, the value, a 36 px remove button
    const row = dialog.locator('.iss-san-row').first()
    expect(Math.abs((await box(row.locator('select'))).width - 120)).toBeLessThanOrEqual(EPS)
    expect(Math.abs((await box(row.getByRole('button'))).width - 36)).toBeLessThanOrEqual(EPS)

    // Advanced starts folded
    await expect(dialog.getByRole('button', { name: /Advanced/ })).toHaveAttribute('aria-expanded', 'false')
    await expect(dialog.locator('.iss-advanced-panel')).toBeHidden()

    // Review: the summary across the dialog, the step marks 22 px round
    await dialog.getByLabel('Common name').fill('layout.example.com')
    await dialog.getByRole('button', { name: 'Review the request' }).click()
    const review = page.getByRole('dialog', { name: 'Review the request' })
    const summary = await box(review.locator('.iss-review'))
    expect(Math.abs(summary.width - 870)).toBeLessThanOrEqual(EPS)
    const mark = await box(review.locator('.iss-step-mark').first())
    expect(Math.abs(mark.width - 22)).toBeLessThanOrEqual(EPS)
    const dt = await box(review.locator('.iss-review dt').first())
    const dd = await box(review.locator('.iss-review dd').first())
    expect(Math.abs(dd.x - (dt.x + 130 + 16))).toBeLessThanOrEqual(EPS)
  })
})

test.describe('phone', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('the issue dialog keeps 16 px margins, one column and no sideways scroll', async ({ page }) => {
    await page.goto('/certificates?action=create')
    const dialog = page.getByRole('dialog', { name: 'Issue a certificate' })
    await expect(dialog).toBeVisible()
    const d = await box(dialog)
    expect(Math.abs(d.x - 16)).toBeLessThanOrEqual(EPS)
    expect(Math.abs(d.width - 358)).toBeLessThanOrEqual(EPS)
    await expect(dialog.locator('.iss-hint')).toBeHidden()
    expect(await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth + 1)).toBe(true)
    // 44 px fields and stacked key source cards
    expect(Math.abs((await box(dialog.getByLabel('Common name'))).height - 44)).toBeLessThanOrEqual(EPS)
    const cards = dialog.locator('.iss-choice')
    const [a, b] = [await box(cards.nth(0)), await box(cards.nth(1))]
    expect(b.y).toBeGreaterThan(a.y + a.height)
  })
})
