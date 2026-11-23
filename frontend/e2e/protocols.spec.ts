import { test, expect, uid, createCA } from './support/fixtures'

// The configuration of a protocol page is one of its view tabs, saved by the form's save bar
const save = (page) => page.locator('#settings-save').click()

test('SCEP: a configuration saved on screen is read back', async ({ page, api }) => {
  await page.goto('/scep-config?tab=config')
  const field = page.getByRole('textbox', { name: /Challenge Password Validity/ })
  const value = String(48 + Math.floor(Math.random() * 100))
  await field.fill(value)
  await save(page)
  await expect.poll(async () => String((await api.get('/scep/config')).challenge_validity ?? JSON.stringify(await api.get('/scep/config')))).toContain(value)

  await page.reload()
  await expect(page.getByRole('textbox', { name: /Challenge Password Validity/ })).toHaveValue(value)
})

test('EST: a configuration saved on screen is read back', async ({ page, api }) => {
  await page.goto('/est-config')
  await page.getByRole('tablist', { name: 'View' }).getByRole('tab', { name: 'Configuration' }).click()
  const enable = page.getByRole('checkbox', { name: /Enable EST Server/ })
  if (!(await enable.isChecked())) await enable.click()
  const user = uid('est').replace(/-/g, '')
  await page.getByLabel('Username').fill(user)
  await save(page)
  await expect.poll(async () => JSON.stringify(await api.get('/est/config'))).toContain(user)

  await page.reload()
  await expect(page.getByLabel('Username')).toHaveValue(user)
})

test('ACME: a local server setting saved on screen is read back', async ({ page, api }) => {
  await page.goto('/acme')
  await page.getByRole('tablist', { name: 'View' }).getByRole('tab', { name: 'Server settings' }).click()
  const issuer = `${uid('caa')}.example.com`
  await page.getByLabel('CAA issuer identifiers').fill(issuer)
  await save(page)
  await expect.poll(async () => JSON.stringify(await api.get('/acme/settings'))).toContain(issuer)

  await page.reload()
  await expect(page.getByLabel('CAA issuer identifiers')).toHaveValue(issuer)
})

test.describe('a phone of 360 px', () => {
  test.use({ viewport: { width: 360, height: 800 } })

  const openDefaultEndpoint = async (page, api) => {
    const ca = await createCA(api)
    await api.patch('/est/config', { enabled: true, ca_id: ca.id })
    await page.goto('/est-config')
    await page.getByRole('button', { name: 'Default endpoint' }).first().click()
    const dock = page.locator('#inspector')
    await expect(dock.locator('dl.kv .row.long .code-value.url')).toHaveCount(5)
    return dock
  }

  test('EST: each endpoint URL in its chip, copied whole, no word cut', async ({ page, api }) => {
    const dock = await openDefaultEndpoint(page, api)
    // The terms and plain values break no word; a technical value wraps in its chip
    const cut = await dock.evaluate((aside) => {
      const out: string[] = []
      for (const cell of aside.querySelectorAll('dl.kv > .row > :is(dt, dd.v, dd.absent)')) {
        const walker = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT)
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
          if ((node.parentElement as Element).closest('.code-value')) continue
          for (const m of (node.textContent || '').matchAll(/\S+/g)) {
            const range = document.createRange()
            range.setStart(node, m.index!)
            range.setEnd(node, m.index! + m[0].length)
            if (new Set([...range.getClientRects()].filter((r) => r.width > 0).map((r) => Math.round(r.top))).size > 1) out.push(m[0])
          }
        }
      }
      return out
    })
    expect(cut).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360)
    await page.evaluate(() => {
      const copied: string[] = []
      ;(window as any).__copied = copied
      navigator.clipboard.writeText = (text: string) => { copied.push(text); return Promise.resolve() }
    })
    const enroll = dock.locator('.row', { has: page.locator('dt', { hasText: /^Simple Enroll$/ }) })
    await expect(enroll.locator('.val')).toHaveAttribute('title', /\/\.well-known\/est\/simpleenroll$/)
    await enroll.getByRole('button', { name: 'Copy Simple Enroll' }).press('Enter')
    await expect.poll(() => page.evaluate(() => (window as any).__copied)).toEqual([await enroll.locator('.val').getAttribute('title')])
  })

  test('EST: a URL cut in its middle stays on one line', async ({ page, api }) => {
    const dock = await openDefaultEndpoint(page, api)
    const lines = await dock.locator('dl.kv .code-value.url .val').evaluateAll((vals) => vals.map((val) =>
      Math.round(val.getBoundingClientRect().height / parseFloat(getComputedStyle(val).lineHeight))))
    expect(lines).toEqual([1, 1, 1, 1, 1])
  })
})
