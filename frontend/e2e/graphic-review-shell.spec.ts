import { test, expect, createCA, issueCert, uid } from './support/fixtures'

// The graphic review's layout defects of governance and the shell, measured: a checkbox's help under its label,
// a search result's name whole beside a long hint
type Box = { x: number; y: number; width: number; height: number }
const box = async (locator): Promise<Box> => {
  const b = await locator.boundingBox()
  expect(b).not.toBeNull()
  return b as Box
}

test.describe('desktop', () => {
  test.use({ viewport: { width: 1600, height: 1000 } })

  test('a policy checkbox\'s help sits under its label, not glued after it', async ({ page, api }) => {
    await page.goto('/policies')
    await page.locator('.page-head').getByRole('button', { name: 'Create Policy' }).click()
    const dialog = page.getByRole('dialog')
    const line = dialog.locator('label.checkbox-line').filter({ hasText: 'Notify on policy violation' })
    await line.scrollIntoViewIfNeeded()
    const label = await line.locator('span').first().evaluate((el) => {
      const text = el.firstChild as Text
      const r = document.createRange()
      r.selectNodeContents(text)
      const t = r.getBoundingClientRect()
      return { bottom: t.bottom, left: t.left }
    })
    const help = await box(line.locator('small'))
    expect(help.y).toBeGreaterThanOrEqual(label.bottom - 0.5)
    expect(Math.abs(help.x - label.left)).toBeLessThanOrEqual(1)
  })

  test('a certificate found by the search keeps its name whole beside its hint', async ({ page, api }) => {
    const ca = await createCA(api)
    const name = `${uid('pal')}.example.com`
    await issueCert(api, ca.id, {
      cn: name, organization: 'An organisation with a rather long legal name', organizational_unit: 'Infrastructure and platform engineering',
      locality: 'Saint-Remy-en-Bouzemont-Saint-Genest-et-Isson', state: 'Grand Est', country: 'FR',
    })
    await page.goto('/certificates')
    await page.locator('#shell-search').click()
    await page.locator('.command-search input').fill(name.slice(0, 12))
    const result = page.locator('.command-result').filter({ hasText: name })
    await expect(result).toBeVisible()
    // On one line of 13 px type, whole: a broken name took two or three lines
    expect((await box(result.locator('.name'))).height).toBeLessThan(24)
    expect(await result.locator('.name').evaluate((el) => el.scrollWidth <= el.clientWidth + 1)).toBe(true)
  })
})
