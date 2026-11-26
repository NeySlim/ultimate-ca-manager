import { test, expect, createCA } from './support/fixtures'
import type { Locator, Page } from '@playwright/test'

// On a phone the document scrolls under the 62 px sticky masthead: what a tap scrolls into view starts below it
test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })

// Measured once the (smooth) scroll has come to rest: ten frames without a move
const clearOfMasthead = (title: Locator) => title.evaluate(async (el) => {
  let last = -1
  for (let still = 0; still < 10;) {
    await new Promise((r) => requestAnimationFrame(r))
    still = window.scrollY === last ? still + 1 : 0
    last = window.scrollY
  }
  const t = el.getBoundingClientRect()
  const m = document.querySelector('.atl .masthead')!.getBoundingClientRect()
  const at = document.elementFromPoint(t.left + 4, t.top + t.height / 2)
  return { scrolled: window.scrollY > 0, below: t.top >= m.bottom - 1, drawn: el.contains(at), top: Math.round(t.top), masthead: Math.round(m.bottom) }
})

test('a CA tapped in the tree brings its panel title below the masthead', async ({ page, api }) => {
  const root = await createCA(api)
  const subs = []
  for (let i = 0; i < 3; i += 1) subs.push(await createCA(api, { parentCAId: root.id }))
  await page.goto(`/cas?authority=${root.id}`)
  const main = page.getByRole('main')
  await expect(main.locator('aside.ca-side')).toBeVisible()
  await main.locator(`[data-ca="${subs[2].id}"]`).first().click()
  const title = main.locator('aside.ca-side h2').first()
  await expect(title).toHaveText(subs[2].common_name)
  expect(await clearOfMasthead(title)).toMatchObject({ scrolled: true, below: true, drawn: true })
})

/**
 * The queue card hidden in this page only: the account's layout is read with the card hidden and
 * the layout the page saves never reaches the server, so the shared administrator keeps its own.
 */
async function hiddenQueue(page: Page) {
  await page.route('**/api/v2/auth/verify', async (route) => {
    const response = await route.fetch()
    const body = await response.json()
    if (body?.data) body.data.preferences = { ...(body.data.preferences || {}), dashboard: { hidden: ['queue'] } }
    await route.fulfill({ response, json: body })
  })
  await page.route('**/api/v2/account/preferences', async (route) => {
    if (route.request().method() !== 'GET') return route.fulfill({ json: { data: route.request().postDataJSON() } })
    const response = await route.fetch()
    const body = await response.json()
    body.data = { ...(body.data || {}), dashboard: { hidden: ['queue'] } }
    await route.fulfill({ response, json: body })
  })
}

// The queue answers later than a frame: a request made while its card loads waits for it
const slowQueue = (page: Page) => page.route('**/api/v2/dashboard/queue**', async (route) => {
  await new Promise((r) => setTimeout(r, 400))
  await route.continue()
})

test('the To handle figure brings the queue title below the masthead', async ({ page, api }) => {
  await createCA(api, { validityDays: 100 })
  await slowQueue(page)
  await page.goto('/')
  const figure = page.locator('a.metric.stat[data-metric="queue"][href="#card-queue"]')
  await expect(figure).toBeVisible()
  await figure.click()
  const title = page.locator('#card-queue-title')
  await expect(title).toBeFocused()
  expect(await clearOfMasthead(title)).toMatchObject({ scrolled: true, below: true, drawn: true })
})

test('a hidden queue shown again by the To handle figure brings its title below the masthead', async ({ page, api }) => {
  const before = ((await api.get('/account/preferences')) || {}).dashboard
  await createCA(api, { validityDays: 100 })
  await hiddenQueue(page)
  await slowQueue(page)
  await page.goto('/')
  const figure = page.locator('a.metric.stat[data-metric="queue"][href="#card-queue"]')
  await expect(figure).toBeVisible()
  await expect(page.locator('#card-queue')).toHaveCount(0)
  await figure.click()
  const title = page.locator('#card-queue-title')
  await expect(title).toBeFocused()
  expect(await clearOfMasthead(title)).toMatchObject({ scrolled: true, below: true, drawn: true })
  expect(((await api.get('/account/preferences')) || {}).dashboard).toEqual(before)
})
