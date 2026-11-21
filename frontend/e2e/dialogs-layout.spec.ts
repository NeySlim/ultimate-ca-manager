import { test, expect, uid } from './support/fixtures'

// The product's dialogs drawn as the mockup's modal(): a native dialog, its widths, focus in and back
type Box = { x: number; y: number; width: number; height: number }
const box = async (locator): Promise<Box> => {
  const b = await locator.boundingBox()
  expect(b).not.toBeNull()
  return b as Box
}

test.describe('desktop', () => {
  test.use({ viewport: { width: 1600, height: 1000 } })

  test('a form dialog is the wide modal, its first field focused, the opener focused again on Escape', async ({ page, api }) => {
    await page.goto('/csrs')
    const open = page.locator('#csr-generate')
    await open.focus()
    await open.click()
    const dialog = page.getByRole('dialog', { name: 'Generate CSR' })
    await expect(dialog).toBeVisible()
    expect(await dialog.evaluate((el) => el.tagName)).toBe('DIALOG')
    expect(Math.round((await box(dialog)).width)).toBe(920)
    const cn = dialog.getByLabel(/^Common Name/)
    await expect(cn).toBeFocused()
    expect(Math.round((await box(cn)).height)).toBe(36)
    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
    await expect(open).toBeFocused()
  })

  test('a confirmation is the narrow modal, the warning notice first and Cancel focused', async ({ page, api }) => {
    const cn = `${uid('ask')}.example.com`
    await api.post('/csrs', { cn, key_type: 'RSA 2048' })
    await page.goto('/csrs')
    await page.getByRole('main').getByRole('row').filter({ hasText: cn }).locator('.entity-name').click()
    const panel = page.locator('#inspector')
    await expect(panel.getByText(cn).first()).toBeVisible()
    await panel.getByRole('button', { name: /^Other actions for/ }).click()
    await page.getByRole('dialog').getByRole('button', { name: 'Delete', exact: true }).click()
    const ask = page.getByRole('dialog', { name: 'Delete CSR' })
    await expect(ask).toBeVisible()
    expect(Math.round((await box(ask)).width)).toBe(520)
    await expect(ask.locator('.notice.warn')).toBeVisible()
    await expect(ask.getByRole('button', { name: 'Cancel' })).toBeFocused()
    await ask.getByRole('button', { name: 'Cancel' }).click()
    await expect(ask).toBeHidden()
  })
})
