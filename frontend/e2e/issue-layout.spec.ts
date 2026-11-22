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
    const hint = await box(dialog.locator('.field-hint'))
    const fields = await box(dialog.locator('.form-fields'))
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
    const cards = dialog.locator('.choice-grid .format-option')
    await expect(cards).toHaveCount(2)
    const [a, b] = [await box(cards.nth(0)), await box(cards.nth(1))]
    expect(Math.abs(a.width - b.width)).toBeLessThanOrEqual(EPS)
    expect(Math.abs(b.x - (a.x + a.width + 10))).toBeLessThanOrEqual(EPS)

    // A SAN row: 120 px type, the value, a 36 px remove button
    const row = dialog.locator('.san-row').first()
    expect(Math.abs((await box(row.locator('select'))).width - 120)).toBeLessThanOrEqual(EPS)
    expect(Math.abs((await box(row.getByRole('button'))).width - 36)).toBeLessThanOrEqual(EPS)

    // Advanced starts folded
    await expect(dialog.getByRole('button', { name: /Advanced/ })).toHaveAttribute('aria-expanded', 'false')
    await expect(dialog.locator('.advanced-panel')).toBeHidden()

    // Review: the summary across the dialog, the step marks 22 px round
    await dialog.getByLabel('Common name').fill('layout.example.com')
    await dialog.getByRole('button', { name: 'Review the request' }).click()
    const review = page.getByRole('dialog', { name: 'Review the request' })
    const summary = await box(review.locator('.review-summary'))
    expect(Math.abs(summary.width - 870)).toBeLessThanOrEqual(EPS)
    const mark = await box(review.locator('.steps .step > span').first())
    expect(Math.abs(mark.width - 22)).toBeLessThanOrEqual(EPS)
    const dt = await box(review.locator('.review-summary dt').first())
    const dd = await box(review.locator('.review-summary dd').first())
    // The term column as wide as its longest term (44 % at most), the value right after it
    expect(Math.abs(dd.x - (dt.x + dt.width))).toBeLessThanOrEqual(EPS)
    expect(dt.width).toBeLessThanOrEqual(summary.width * 0.44 + EPS)
  })
})

test.describe('desktop, errors', () => {
  test.use({ viewport: { width: 1600, height: 1000 } })

  test('a field in error takes the bad colour on its border, focused or not', async ({ page, api }) => {
    await page.goto('/certificates?action=create')
    const dialog = page.getByRole('dialog', { name: 'Issue a certificate' })
    await expect(dialog).toBeVisible()
    await dialog.getByRole('button', { name: 'Review the request' }).click()
    const cn = dialog.getByLabel('Common name')
    await expect(cn).toHaveAttribute('aria-invalid', 'true')
    // Asked until it holds: the border colour eases in
    await expect.poll(() => cn.evaluate((el) => {
      const probe = document.createElement('span')
      probe.style.color = 'var(--bad)'
      el.parentElement.appendChild(probe)
      const bad = getComputedStyle(probe).color
      probe.remove()
      return getComputedStyle(el).borderTopColor === bad
    })).toBe(true)
    // Advanced stays folded: nothing of it is in error
    await expect(dialog.getByRole('button', { name: /Advanced/ })).toHaveAttribute('aria-expanded', 'false')
  })

  test('placeholders take the muted text colour of the theme', async ({ page, api }) => {
    await page.goto('/certificates?action=create')
    const dialog = page.getByRole('dialog', { name: 'Issue a certificate' })
    await expect(dialog).toBeVisible()
    const colours = await dialog.getByLabel('Common name').evaluate((el) => {
      const probe = document.createElement('span')
      probe.style.color = 'var(--muted)'
      el.parentElement.appendChild(probe)
      const muted = getComputedStyle(probe).color
      probe.remove()
      return { muted, placeholder: getComputedStyle(el, '::placeholder').color }
    })
    expect(colours.placeholder).toBe(colours.muted)
  })
})

test.describe('phone', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('the issue dialog keeps 16 px margins, one column and no sideways scroll', async ({ page, api }) => {
    await page.goto('/certificates?action=create')
    const dialog = page.getByRole('dialog', { name: 'Issue a certificate' })
    await expect(dialog).toBeVisible()
    const d = await box(dialog)
    expect(Math.abs(d.x - 16)).toBeLessThanOrEqual(EPS)
    expect(Math.abs(d.width - 358)).toBeLessThanOrEqual(EPS)
    await expect(dialog.locator('.field-hint')).toBeHidden()
    expect(await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth + 1)).toBe(true)
    // 44 px fields and stacked key source cards
    expect(Math.abs((await box(dialog.getByLabel('Common name'))).height - 44)).toBeLessThanOrEqual(EPS)
    const cards = dialog.locator('.choice-grid .format-option')
    const [a, b] = [await box(cards.nth(0)), await box(cards.nth(1))]
    expect(b.y).toBeGreaterThan(a.y + a.height)
  })
})
