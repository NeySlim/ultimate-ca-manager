import { test, expect, createCA } from './support/fixtures'
import type { Locator } from '@playwright/test'

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

test('the To handle figure brings the queue title below the masthead', async ({ page, api }) => {
  await createCA(api, { validityDays: 100 })
  await page.goto('/')
  const figure = page.locator('a.metric.stat[href="#card-queue"]').first()
  await expect(figure).toBeVisible()
  await figure.click()
  const title = page.locator('#card-queue-title')
  await expect(title).toBeFocused()
  expect(await clearOfMasthead(title)).toMatchObject({ scrolled: true, below: true, drawn: true })
})
