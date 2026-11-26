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

// A dialog's helps and notices read on 78 characters of their own font at most, in the wide dialogs too
const DIALOGS: [string, string][] = [['/templates', '#template-new'], ['/policies', '#policy-new'], ['/cas', '[data-action=create-ca]'],
  ['/ssh/cas', '#ssh-ca-new'], ['/hsm', '#hsm-new'], ['/certificates', '[data-action=issue]'], ['/ssh/certificates', '#ssh-cert-new'], ['/rbac', '#rbac-new']]
for (const width of [1280, 1920]) {
  test(`at ${width}px the helps and notices of the form dialogs stop at 78ch`, async ({ page, api: _api }) => {
    test.setTimeout(120_000)
    await page.setViewportSize({ width, height: 1200 })
    let measured = 0
    for (const [path, opener] of DIALOGS) {
      await page.goto(path)
      await page.locator(opener).first().click()
      const dialog = page.locator('dialog[open]').last()
      await expect(dialog, path).toBeVisible()
      // the folded parts hold helps too
      const folded = dialog.locator('.advanced-toggle[aria-expanded=false]')
      while (await folded.count()) await folded.first().click()
      const m = await dialog.evaluate((d) => {
        const over: string[] = []
        let count = 0, widest = 0
        for (const el of d.querySelectorAll('small, p.small, p.muted, p.group-hint, .modal-head p, .notice > span')) {
          if (getComputedStyle(el).display === 'inline' || !(el as HTMLElement).offsetParent) continue
          const probe = document.createElement('span')
          probe.style.cssText = 'position:absolute;visibility:hidden;width:78ch'
          el.appendChild(probe)
          const limit = probe.getBoundingClientRect().width
          probe.remove()
          const w = el.getBoundingClientRect().width
          count += 1
          widest = Math.max(widest, w / limit)
          if (w > limit + 1) over.push(`${el.textContent?.slice(0, 40)}: ${Math.round(w)} > ${Math.round(limit)}`)
        }
        return { over, count, widest, width: d.getBoundingClientRect().width }
      })
      expect(m.over, path).toEqual([])
      measured += m.count
    }
    expect(measured).toBeGreaterThan(30)
  })
}

// A form dialog taller than the window keeps its actions in view at its foot, whichever dialog it is
for (const [width, height] of [[1600, 900], [390, 844]]) {
  test(`at ${width}x${height} the actions of a long form dialog stay in view`, async ({ page, api: _api }) => {
    test.setTimeout(120_000)
    await page.setViewportSize({ width, height })
    let long = 0
    for (const [path, opener] of DIALOGS) {
      await page.goto(path)
      await page.locator(opener).first().click()
      const dialog = page.locator('dialog[open]').last()
      await expect(dialog, path).toBeVisible()
      const m = await dialog.evaluate((d) => {
        const actions = [...d.querySelectorAll('.modal-actions')].filter((a) => (a as HTMLElement).offsetParent).pop()
        if (!actions) return null
        const a = actions.getBoundingClientRect()
        const b = d.getBoundingClientRect()
        return { scrolls: d.scrollHeight > d.clientHeight + 1, inView: a.top >= b.top - 1 && a.bottom <= b.bottom + 1, a: [a.top, a.bottom], b: [b.top, b.bottom] }
      })
      expect(m, path).not.toBeNull()
      if (!m!.scrolls) continue
      long += 1
      expect(m!.inView, `${path} ${JSON.stringify(m)}`).toBe(true)
    }
    expect(long).toBeGreaterThan(2)
  })
}
