import { test, expect, createCA, issueCert, type Api } from './support/fixtures'
import type { Page } from '@playwright/test'
import { PALETTES, usePalette, expectPalette, boxes } from './support/themes'
import { freezeApi, type Frozen } from './support/frozen'

const CARDS = [
  'To handle', 'Automation health', 'Hierarchy', 'Expiry horizon', 'Compliance', 'Latest operations', 'Certificate activity',
]

test('the overview cards load their data', async ({ page, api }) => {
  const ca = await createCA(api)
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1, name: 'Overview' })).toBeVisible()
  for (const name of CARDS) {
    const card = page.getByRole('region', { name })
    await expect(card.getByRole('heading', { name })).toBeVisible()
    await expect(card.locator('.sk-body')).toHaveCount(0)
  }
  // The activity card reports what the test just did
  await expect(page.getByRole('region', { name: 'Latest operations' }).getByText(ca.common_name).first()).toBeVisible()
})

test('a queue entry opens the object it names', async ({ page, api }) => {
  // A CA that expires within a year is an item to handle
  const ca = await createCA(api, { validityDays: 100 })
  await page.goto('/')
  const queue = page.getByRole('region', { name: 'To handle' })
  await expect(queue.getByRole('heading', { name: /^To handle/ })).toBeVisible()
  await expect(queue.locator('.sk-body')).toHaveCount(0)
  // A CA still far from expiry is only to watch: those rows are folded apart from the interventions,
  // where the same CA may also stand for its missing CRL
  await queue.locator('#queue-watch-toggle').click()
  const entry = queue.locator(`#queue-watch [data-ca-link="${ca.id}"]`)
  await expect(entry).toBeVisible()
  await entry.click()

  // The CA opens in the Authorities page, in the panel beside its hierarchy: its own, not another one's
  await expect(page).toHaveURL(new RegExp(`/cas\\?(.*&)?authority=${ca.id}(&|$)`))
  await expect(page.getByRole('complementary', { name: ca.common_name })).toBeVisible()
})

const DEFAULT_ORDER = ['queue', 'health', 'hierarchy', 'horizon', 'compliance', 'activity', 'trend']
const shownOrder = (page: Page) => page.locator('.dash-cards > .dash-card').evaluateAll(cards => cards.map(c => c.getAttribute('data-card')))

/** Runs `body` on the default layout, then puts the administrator's own preference back. */
async function withDefaultLayout(api: Api, body: () => Promise<void>) {
  const before = (await api.get('/account/preferences')) || {}
  await api.put('/account/preferences', { ...before, dashboard: { order: DEFAULT_ORDER, hidden: [], queueShowAll: false } })
  try {
    await body()
  } finally {
    const { dashboard: _moved, ...rest } = (await api.get('/account/preferences')) || {}
    await api.put('/account/preferences', 'dashboard' in before ? { ...rest, dashboard: before.dashboard } : rest)
  }
  expect(((await api.get('/account/preferences')) || {}).dashboard).toEqual(before.dashboard)
}

test('the cards follow the mockup widths: the queue on its own line, then pairs of unequal width', async ({ page, api }) => {
  await page.setViewportSize({ width: 1600, height: 1000 })
  await withDefaultLayout(api, async () => {
    await page.goto('/')
    await expect(page.locator('.dash-cards > .dash-card')).toHaveCount(DEFAULT_ORDER.length)
    for (const name of CARDS) await expect(page.getByRole('region', { name }).locator('.sk-body')).toHaveCount(0)
    const boxes = await page.evaluate(() => {
      const grid = document.querySelector('.atl .dash-cards')!.getBoundingClientRect()
      return {
        width: grid.width,
        cards: Object.fromEntries([...document.querySelectorAll('.atl .dash-cards > .dash-card')].map(c => {
          const r = c.getBoundingClientRect()
          return [c.getAttribute('data-card'), { x: r.left - grid.left, y: r.top, w: r.width }]
        })),
      }
    })
    const { cards, width } = boxes
    expect(Math.abs(cards.queue.w - width)).toBeLessThanOrEqual(1)
    // Health beside hierarchy, the narrower first; reading order is the saved order
    expect(cards.health.y).toBe(cards.hierarchy.y)
    expect(cards.health.w).toBeLessThan(cards.hierarchy.w)
    expect(cards.trend.w).toBeGreaterThan(width - 1)
    expect(await shownOrder(page)).toEqual(DEFAULT_ORDER)
  })
})

test('the compliance figures keep their own height beside the algorithms', async ({ page, api }) => {
  const ca = await createCA(api)
  await issueCert(api, ca.id)
  await page.setViewportSize({ width: 1600, height: 1000 })
  await page.goto('/')
  const card = page.getByRole('region', { name: 'Compliance' })
  await expect(card.locator('.sk-body')).toHaveCount(0)
  await expect(card.getByText('Key algorithms')).toBeVisible()
  const heights = await card.locator('.tiles > .tile:not(.algo)').evaluateAll(tiles => tiles.map(t => t.getBoundingClientRect().height))
  expect(heights).toHaveLength(5)
  expect(Math.max(...heights) - Math.min(...heights)).toBeLessThanOrEqual(1)
})

test('a card moves in the Cards dialog, keeps the focus, and the order survives a reload', async ({ page, api }) => {
  await withDefaultLayout(api, async () => {
    await page.goto('/')
    await expect(page.locator('.dash-cards > .dash-card')).toHaveCount(DEFAULT_ORDER.length)
    expect(await shownOrder(page)).toEqual(DEFAULT_ORDER)
    const saved = () => page.waitForResponse(r => r.url().endsWith('/account/preferences') && r.request().method() === 'PUT' && r.ok())

    await page.getByRole('button', { name: 'Cards: show, hide, reorder' }).click()
    const dialog = page.getByRole('dialog', { name: 'Overview cards' })
    await expect(dialog).toBeVisible()
    const put = saved()
    await dialog.getByRole('button', { name: 'Move Automation health down' }).click()
    const after = ['queue', 'hierarchy', 'health', 'horizon', 'compliance', 'activity', 'trend']
    await expect.poll(() => shownOrder(page)).toEqual(after)
    await expect(dialog.getByRole('button', { name: 'Move Automation health down' })).toBeFocused()
    await put
    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
    await expect(page.locator('#dash-cards-button')).toBeFocused()

    await page.reload()
    await expect(page.locator('.dash-cards > .dash-card')).toHaveCount(DEFAULT_ORDER.length)
    await expect.poll(() => shownOrder(page)).toEqual(after)
    expect((await api.get('/account/preferences')).dashboard.order).toEqual(after)
  })
})

test('a head preset shows its cards and reads as pressed', async ({ page, api }) => {
  await withDefaultLayout(api, async () => {
    await page.goto('/')
    const manager = page.locator('#head-preset-manager')
    await expect(manager).toHaveAttribute('aria-pressed', 'false')
    // The preset is saved: wait for it, or the save lands after the restore below
    const put = page.waitForResponse(r => r.url().endsWith('/account/preferences') && r.request().method() === 'PUT' && r.ok())
    await manager.click()
    await put
    await expect.poll(() => shownOrder(page)).toEqual(['compliance', 'horizon', 'hierarchy', 'activity'])
    await expect(manager).toHaveAttribute('aria-pressed', 'true')
  })
})

// Aurore set apart from Atelier by its accents only (e2e/theme-geometry.spec.ts): the overview's boxes do not move
const OVERVIEW_BOXES = ['.masthead', '.metric', '.dash-card', '.panel-heading', '.tile', '.badge', '.chip', '.counter', '.queue-row', '.health-row']

test('a change of theme moves nothing on the overview', async ({ page, api }) => {
  await page.setViewportSize({ width: 1600, height: 1000 })
  await withDefaultLayout(api, async () => {
    const measured: Record<string, Record<string, number[][]>> = {}
    // The scheduler writes beside this project too: every palette reads the first one's answers
    const kept: Frozen = new Map()
    for (const [family, mode] of PALETTES) {
      await page.unrouteAll({ behavior: 'ignoreErrors' })
      await freezeApi(page, kept)
      await usePalette(page, family, mode)
      await page.goto('/')
      await expectPalette(page, family, mode)
      await expect(page.locator('.dash-cards > .dash-card')).toHaveCount(DEFAULT_ORDER.length)
      for (const name of CARDS) await expect(page.getByRole('region', { name }).locator('.sk-body')).toHaveCount(0)
      measured[`${family}-${mode}`] = await boxes(page, OVERVIEW_BOXES)
    }
    const reference = measured['atelier-dark']
    for (const s of ['.metric', '.dash-card', '.tile', '.badge', '.counter']) expect(reference[s].length, s).toBeGreaterThan(0)
    for (const [key, got] of Object.entries(measured)) expect(got, key).toEqual(reference)
  })
})
