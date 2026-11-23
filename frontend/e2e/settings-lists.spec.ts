import { test, expect, uid } from './support/fixtures'

// A long webhook list is a paged table: the sections after it stay within reach, the search finds one
test('75 webhooks fit one bounded page and the search finds one of them', async ({ page, api }) => {
  test.setTimeout(120_000)
  const prefix = uid('lst')
  const ids: number[] = []
  try {
    for (let i = 1; i <= 75; i++) {
      // Disabled, on a private address that is never called: no delivery leaves the instance
      const hook = await api.post('/webhooks', { name: `${prefix}-${String(i).padStart(2, '0')}`, url: `https://10.255.${Math.floor(i / 250)}.${i}/hook`, events: ['certificate.issued'], enabled: false })
      ids.push(hook.id)
    }
    await page.goto('/settings?tab=webhooks')
    const section = page.locator('#set-sec-webhooks')
    const search = section.locator('#webhook-search')
    await search.fill(prefix)
    const rows = section.locator('table.module-table tbody tr')
    await expect(rows).toHaveCount(25)
    await expect(section.locator('.table-footer')).toContainText('1–25 of 75')
    // 25 rows, the toolbar and the footer: far from the 5 000 px the 75 lines took
    const height = await section.evaluate((el) => el.getBoundingClientRect().height)
    expect(height).toBeLessThan(1800)

    await search.fill(`${prefix}-42`)
    await expect(rows).toHaveCount(1)
    await expect(rows.first()).toContainText(`${prefix}-42`)
    await expect(rows.first()).toContainText('10.255.0.42')
  } finally {
    for (const id of ids) await api.del(`/webhooks/${id}`)
  }
})
