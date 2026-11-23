import { test, expect } from './support/fixtures'
import type { Page, Locator } from '@playwright/test'

// Settings and generic dialogs as typed facts (KV-3, zone E): a technical value in a chip that copies it whole,
// no button in a value column but a chip's own, no word cut on a phone of 360 px.

const stubClipboard = (page: Page) => page.evaluate(() => {
  const copied: string[] = []
  ;(window as any).__copied = copied
  navigator.clipboard.writeText = (text: string) => { copied.push(text); return Promise.resolve() }
})
const copied = (page: Page) => page.evaluate(() => (window as any).__copied)
const row = (scope: Locator, term: string) => scope.locator('dl.kv > .row', { has: scope.page().locator('dt', { hasText: new RegExp(`^${term}$`) }) })
const loneButtons = (scope: Locator) => scope.locator('dl.kv dd.v button').evaluateAll((buttons) => buttons.filter((b) => !b.closest('.code-value')).length)

// Every word of a term or a value on one line, a technical value in its chip excepted
const cutWords = (scope: Locator) => scope.evaluate((root) => {
  const out: string[] = []
  for (const cell of root.querySelectorAll('dl.kv > .row > :is(dt, dd.v, dd.absent)')) {
    if (!(cell as HTMLElement).offsetParent) continue
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

// The latest journal entry that recorded an address, opened from its row
async function openEventWithIp(page: Page, api: any) {
  const data = await api.get('/audit/logs?page=1&per_page=50')
  const logs = Array.isArray(data) ? data : (data.logs || data.items || [])
  const log = logs.find((l: any) => l.ip_address)
  expect(log, 'an entry with an IP address').toBeTruthy()
  await page.goto('/audit')
  await page.locator(`button[data-open="${log.id}"]`).first().click()
  const dialog = page.locator('dialog[open]')
  await expect(dialog.locator('dl.kv')).toBeVisible()
  return { dialog, log }
}

test('the database URI copies whole from its chip, its health a state, no button beside a value', async ({ page, api }) => {
  const status = await api.get('/database/status')
  await page.goto('/settings?tab=database')
  const main = page.getByRole('main')
  const uri = row(main, 'Connection URI')
  await expect(uri.locator('dd.v .code-value.url')).toBeVisible()
  await stubClipboard(page)
  await uri.getByRole('button', { name: 'Copy Connection URI' }).press('Enter')
  await expect.poll(() => copied(page)).toEqual([status.uri_redacted])
  await expect(row(main, 'Health').locator('dd.v .badge')).toBeVisible()
  expect(await loneButtons(page.getByRole('main'))).toBe(0)
})

test('the event dialog copies the IP address from its chip and keeps buttons out of its values', async ({ page, api }) => {
  const { dialog, log } = await openEventWithIp(page, api)
  await expect(row(dialog, 'Result').locator('dd.v .badge')).toBeVisible()
  await stubClipboard(page)
  await row(dialog, 'IP Address').getByRole('button', { name: 'Copy IP Address' }).press('Enter')
  await expect.poll(() => copied(page)).toEqual([log.ip_address])
  expect(await loneButtons(dialog)).toBe(0)
})

test.describe('a phone of 360 px', () => {
  test.use({ viewport: { width: 360, height: 800 } })

  test('the settings and the event dialog cut no word and scroll not sideways', async ({ page, api }) => {
    await page.goto('/settings?tab=security')
    const main = page.getByRole('main')
    await expect(main.locator('dl.kv').first()).toBeVisible()
    expect(await cutWords(main)).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360)
    const { dialog } = await openEventWithIp(page, api)
    expect(await cutWords(dialog)).toEqual([])
    // The client's signature, a sentence, goes under its term
    const client = row(dialog, 'Client')
    if (await client.count()) {
      const [dt, dd] = await Promise.all([client.locator('dt').boundingBox(), client.locator('dd.v').boundingBox()])
      expect(dd!.y).toBeGreaterThan(dt!.y + dt!.height - 1)
    }
  })
})
