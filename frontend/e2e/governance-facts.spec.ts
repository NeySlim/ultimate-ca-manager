import { test, expect, createCA, issueCert, uid } from './support/fixtures'

// The words of a block's terms and values that wrap inside themselves (a technical value in its chip excepted)
const cutWords = (scope) => scope.evaluate((root: Element) => {
  const out: string[] = []
  for (const cell of root.querySelectorAll('dl.kv > .row > :is(dt, dd.v, dd.absent)')) {
    const walker = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT)
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if ((node.parentElement as Element).closest('.code-value')) continue
      for (const m of (node.textContent || '').matchAll(/\S+/g)) {
        const range = document.createRange()
        range.setStart(node, m.index!)
        range.setEnd(node, m.index! + m[0].length)
        const tops = new Set([...range.getClientRects()].filter((r) => r.width > 0).map((r) => Math.round(r.top)))
        if (tops.size > 1) out.push(m[0])
      }
    }
  }
  return out
})

const catchCopies = (page) => page.evaluate(() => {
  const copied: string[] = []
  ;(window as any).__copied = copied
  navigator.clipboard.writeText = (text: string) => { copied.push(text); return Promise.resolve() }
})

test.describe('a phone of 360 px', () => {
  test.use({ viewport: { width: 360, height: 800 } })

  test('a trust anchor reads in typed rows: names long, digests in octets copied whole, no word cut', async ({ page, api }) => {
    const cert = await issueCert(api, (await createCA(api)).id)
    const entry = await api.post('/truststore', { name: uid('anchor'), certificate_pem: cert.pem, purpose: 'custom' })
    expect(entry.fingerprint_sha256).toMatch(/^[0-9a-f]{64}$/i)
    await page.goto(`/truststore?item=${entry.id}&section=details`)
    const dock = page.locator('#inspector')
    await expect(dock.locator('dl.kv').first()).toBeVisible()
    await expect(dock.locator('dl.props')).toHaveCount(0)
    await expect(dock.locator('.row', { has: page.locator('dt', { hasText: /^Issuer$/ }) })).toHaveClass(/\blong\b/)
    // The digest in four lines of eight octets, as a certificate's, and copied so
    await catchCopies(page)
    const digest = dock.locator('.row', { has: page.locator('dt', { hasText: /^SHA-256$/ }) })
    await expect(digest.locator('.val.hex > .line')).toHaveCount(4)
    await digest.getByRole('button', { name: 'Copy SHA-256' }).press('Enter')
    const octets = entry.fingerprint_sha256.toUpperCase().match(/../g).join(':')
    await expect.poll(() => page.evaluate(() => (window as any).__copied)).toEqual([octets])
    expect(await cutWords(dock)).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360)
  })
})

test('a journal entry keeps its values clear of buttons, its address copyable in its value', async ({ page, api }) => {
  const name = uid('root')
  await createCA(api, { commonName: name })
  // This request's own entry, which carries its client's address: a scheduler's entry (a CRL) may be newer and has none
  await page.goto(`/audit?search=${encodeURIComponent(name)}&action_prefix=ca_created`)
  const rows = page.getByRole('main').locator('.audit-table tbody tr:not(.sk-row)')
  await expect(rows).toHaveCount(1)
  await page.getByRole('main').locator('.audit-table .resource').first().click()
  const dialog = page.locator('dialog[open]')
  await expect(dialog.locator('dl.kv')).toBeVisible()
  await expect(dialog.locator('dl.props')).toHaveCount(0)
  // The mockup's 22 px above and below the block of the entry, from the stylesheet
  expect(await dialog.locator('.event-detail > dl.kv').evaluate((dl) => [dl.getAttribute('style'), getComputedStyle(dl).marginTop, getComputedStyle(dl).marginBottom]))
    .toEqual([null, '22px', '22px'])
  // The result a pill, the client a sentence on its own row, no button in a value but a value's own copy
  await expect(dialog.locator('.row', { has: page.locator('dt', { hasText: /^Result$/ }) }).locator('dd.v .badge')).toBeVisible()
  expect(await dialog.locator('dl.kv dd.v button').evaluateAll((list) => list.every((b) => b.closest('.code-value')))).toBe(true)
  const ip = dialog.locator('.row', { has: page.locator('dt', { hasText: /^IP Address$/ }) })
  await catchCopies(page)
  const shown = (await ip.locator('.code-value .val').innerText()).trim()
  await ip.getByRole('button', { name: 'Copy IP Address' }).press('Enter')
  await expect.poll(() => page.evaluate(() => (window as any).__copied)).toEqual([shown])
})
