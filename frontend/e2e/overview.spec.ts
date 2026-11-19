import { test, expect, createCA, issueCert, type Api } from './support/fixtures'
import type { Page } from '@playwright/test'

const CARDS = [
  'To handle', 'Automation health', 'Hierarchy', 'Expiry horizon', 'Certificate activity', 'Status distribution',
  'Compliance', 'Latest operations',
]

test('the overview cards load their data', async ({ page, api }) => {
  const ca = await createCA(api)
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1, name: 'Overview' })).toBeVisible()
  for (const name of CARDS) {
    const card = page.getByRole('region', { name })
    await expect(card.getByRole('heading', { name })).toBeVisible()
    await expect(card.getByRole('status')).toHaveCount(0)
  }
  // The activity card reports what the test just did
  await expect(page.getByRole('region', { name: 'Latest operations' }).getByText(ca.common_name).first()).toBeVisible()
})

test('a queue entry opens the object it names', async ({ page, api }) => {
  // A CA that expires within a year is an item to handle
  const ca = await createCA(api, { validityDays: 100 })
  await page.goto('/')
  const queue = page.getByRole('region', { name: 'To handle' })
  await expect(queue.getByRole('heading', { name: 'To handle' })).toBeVisible()
  await expect(queue.getByRole('status')).toHaveCount(0)
  // A CA still far from expiry is only to watch: those rows are folded apart from the interventions,
  // where the same CA may also stand for its missing CRL
  await queue.getByRole('button', { name: 'Show the rows to watch' }).click()
  const entry = queue.locator('#overview-queue-watch').getByRole('link', { name: ca.common_name, exact: true })
  await expect(entry).toBeVisible()
  await entry.click()

  await expect(page).toHaveURL(url => url.pathname === '/cas' || url.pathname === `/cas/${ca.id}`)
  // The link names the CA's own page, not another one's
  await expect(page.getByRole('tabpanel', { name: ca.common_name }).getByRole('heading', { name: ca.common_name })).toBeVisible()
})

const DEFAULT_ORDER = ['queue', 'health', 'hierarchy', 'horizon', 'trend', 'states', 'compliance', 'activity']
const shownOrder = (page: Page) => page.locator('.ov-slot').evaluateAll(slots => slots.map(s => s.getAttribute('data-card')))

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

test('cards of unequal heights pack by column and keep the saved order', async ({ page, api }) => {
  await page.setViewportSize({ width: 1600, height: 1000 })
  await withDefaultLayout(api, async () => {
    await page.goto('/')
    await expect(page.locator('.ov-slot')).toHaveCount(DEFAULT_ORDER.length)
    for (const name of CARDS) await expect(page.getByRole('region', { name }).getByRole('status')).toHaveCount(0)
    // Heights the data of a real instance gives: a tall hierarchy between two shorter cards
    await page.addStyleTag({ content: `
      #card-health { min-height: 300px } #card-hierarchy { min-height: 900px } #card-horizon { min-height: 480px }
      #card-states { height: 260px; overflow: hidden }` })
    type Box = { id: string; x: number; y: number; right: number; bottom: number; slot: number }
    const measure = () => page.evaluate(() => {
      const grid = document.querySelector('.ov-grid')!
      const boxes = [...grid.querySelectorAll('.ov-slot')].map(slot => {
        const r = slot.firstElementChild!.getBoundingClientRect()
        return { id: slot.getAttribute('data-card')!, x: r.left, y: r.top, right: r.right, bottom: r.bottom,
          slot: slot.getBoundingClientRect().height }
      })
      const g = grid.getBoundingClientRect()
      return { boxes, top: g.top, left: g.left, right: g.right, gap: parseFloat(getComputedStyle(grid).columnGap) }
    })
    const overlap = (a: Box, b: Box) => a.x < b.right - 1 && b.x < a.right - 1
    await expect.poll(async () => {
      const { boxes } = await measure()
      const by = Object.fromEntries(boxes.map(b => [b.id, b]))
      return by.states.y < by.hierarchy.bottom
    }, { message: 'a later card fills the room left under a short one' }).toBe(true)

    const { boxes, top, left, right, gap } = await measure()
    const by = Object.fromEntries(boxes.map(b => [b.id, b]))
    expect(gap).toBe(20)
    expect(new Set([by.health.x, by.hierarchy.x, by.horizon.x]).size).toBe(3)
    for (const box of boxes) {
      // No hole above a card: the nearest card over it in its columns, or the top of the grid, is one gap away
      const above = boxes.filter(o => o !== box && overlap(o, box) && o.bottom <= box.y + 1)
      const floor = above.length ? Math.max(...above.map(o => o.bottom)) + gap : top
      expect(box.y - floor, `empty room above ${box.id}`).toBeLessThanOrEqual(1)
      expect(box.y - floor, `${box.id} overlaps the card above`).toBeGreaterThanOrEqual(-1)
      // No card stretched to a neighbour: its slot is as high as itself
      expect(Math.abs(box.slot - (box.bottom - box.y)), `${box.id} is stretched`).toBeLessThanOrEqual(1)
      for (const other of boxes) {
        if (other === box || !overlap(other, box)) continue
        expect(other.bottom <= box.y + 1 || box.bottom <= other.y + 1, `${box.id} and ${other.id} overlap`).toBe(true)
      }
    }
    expect(Math.round(by.states.bottom - by.states.y)).toBe(260)
    // The wide cards keep their width: the queue the whole grid, the two others two columns of three
    const column = by.health.right - by.health.x
    expect(Math.abs((by.queue.right - by.queue.x) - (right - left))).toBeLessThanOrEqual(1)
    for (const id of ['trend', 'compliance']) expect(Math.abs((by[id].right - by[id].x) - (2 * column + gap)), id).toBeLessThanOrEqual(1)
    // Reading and tab order are the saved order, wherever a card landed
    expect(boxes.map(b => b.id)).toEqual(DEFAULT_ORDER)
    const grips = await page.locator('.ov-grip').evaluateAll(els => els.map(e => e.closest('.ov-slot')!.getAttribute('data-card')))
    expect(grips).toEqual(DEFAULT_ORDER)
  })
})

test('the compliance figures keep their own height beside the algorithms', async ({ page, api }) => {
  const ca = await createCA(api)
  await issueCert(api, ca.id)
  await page.setViewportSize({ width: 1600, height: 1000 })
  await page.goto('/')
  const card = page.getByRole('region', { name: 'Compliance' })
  await expect(card.getByRole('status')).toHaveCount(0)
  await expect(card.getByText('Key algorithms')).toBeVisible()
  const heights = await card.locator('.ov-tiles > *').evaluateAll(tiles => tiles.map(t => t.getBoundingClientRect().height))
  expect(heights).toHaveLength(5)
  expect(Math.max(...heights)).toBeLessThan(90)
  expect(Math.max(...heights) - Math.min(...heights)).toBeLessThanOrEqual(1)
})

test('a card moves with the mouse, then with the keyboard, and the order survives a reload', async ({ page, api }) => {
  await withDefaultLayout(api, async () => {
    await page.goto('/')
    await expect(page.locator('.ov-slot')).toHaveCount(DEFAULT_ORDER.length)
    expect(await shownOrder(page)).toEqual(DEFAULT_ORDER)
    // Loaded cards: nothing moves under the pointer any more
    for (const name of CARDS) await expect(page.getByRole('region', { name }).getByRole('status')).toHaveCount(0)
    const grip = (name: string) => page.getByRole('button', { name: `Move the card ${name}: drag it, or use the arrow keys` })
    const saved = () => page.waitForResponse(r => r.url().endsWith('/account/preferences') && r.request().method() === 'PUT' && r.ok())

    // Mouse: the expiry horizon dropped on the automation health card takes its place
    let put = saved()
    // Stepped moves: the browser starts a drag only once the pressed pointer has travelled
    await grip('Expiry horizon').hover()
    await page.mouse.down()
    const from = (await grip('Expiry horizon').boundingBox())!
    // The heading of the target card: on the row of the grip, hence inside the window whatever the card's height
    const to = (await page.getByRole('heading', { name: 'Automation health' }).boundingBox())!
    await page.mouse.move(from.x + 30, from.y + 30, { steps: 5 })
    await page.mouse.move(to.x + to.width / 2, to.y + to.height / 2, { steps: 15 })
    await expect(page.locator('.ov-slot.is-target')).toHaveAttribute('data-card', 'health')
    await page.mouse.up()
    const afterMouse = ['queue', 'horizon', 'health', 'hierarchy', 'trend', 'states', 'compliance', 'activity']
    await expect.poll(() => shownOrder(page)).toEqual(afterMouse)
    await put
    await expect(page.locator('.ov-slot.is-dragged, .ov-slot.is-target')).toHaveCount(0)

    // Keyboard: one arrow key on the grip moves the card one place and keeps the focus on it
    put = saved()
    await grip('Automation health').focus()
    await page.keyboard.press('ArrowRight')
    const afterKey = ['queue', 'horizon', 'hierarchy', 'health', 'trend', 'states', 'compliance', 'activity']
    await expect.poll(() => shownOrder(page)).toEqual(afterKey)
    await expect(grip('Automation health')).toBeFocused()
    await expect(page.getByTestId('overview-said')).toHaveText('Automation health is now card 4 of 8.')
    await put

    await page.reload()
    await expect(page.locator('.ov-slot')).toHaveCount(DEFAULT_ORDER.length)
    await expect.poll(() => shownOrder(page)).toEqual(afterKey)
    expect((await api.get('/account/preferences')).dashboard.order).toEqual(afterKey)
  })
})
