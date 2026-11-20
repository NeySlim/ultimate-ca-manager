import { test, expect, createUser } from './support/fixtures'

// Geometry of the Atelier shell: bars, Modules menu and notification panel, measured in the browser
const EPS = 1
type Box = { x: number; y: number; width: number; height: number }
const box = async (locator): Promise<Box> => {
  // The first paint of the bar comes before the rights: a measure waits for its element
  await expect(locator).toBeVisible()
  const b = await locator.boundingBox()
  expect(b).not.toBeNull()
  return b as Box
}

test('the top bar, its links and the status bar keep the mockup heights', async ({ page, api }) => {
  await page.setViewportSize({ width: 1600, height: 1000 })
  await page.goto('/certificates')
  const top = await box(page.locator('.shell-topbar'))
  expect(top.y).toBeLessThanOrEqual(EPS)
  expect(Math.abs(top.height - 62)).toBeLessThanOrEqual(EPS)
  const nav = page.getByRole('navigation', { name: 'Main navigation' })
  // The four main pages, Activity last, as links of the bar's full height
  const links = nav.locator('a.shell-navlink')
  await expect(links.nth(3)).toHaveAttribute('href', '/audit')
  for (const link of await links.all()) {
    const b = await box(link)
    expect(b.y).toBeLessThanOrEqual(EPS)
    expect(Math.abs(b.y + b.height - (top.y + top.height))).toBeLessThanOrEqual(2)
  }
  const status = await box(page.getByRole('contentinfo'))
  expect(Math.abs(status.height - 25)).toBeLessThanOrEqual(EPS)
  expect(Math.abs(status.y + status.height - 1000)).toBeLessThanOrEqual(EPS)
  // The live connection lives in the status bar, not the top bar
  await expect(page.locator('.shell-topbar .shell-ws')).toHaveCount(0)
  await expect(page.locator('.shell-statusbar .shell-ws')).toHaveCount(1)
})

test('the Modules menu opens under its button, inside the window', async ({ page, api }) => {
  await page.setViewportSize({ width: 1600, height: 1000 })
  await page.goto('/')
  // The bar is complete once the rights are in: the last fixed link is there
  await expect(page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Activity' })).toBeVisible()
  const button = page.getByRole('button', { name: 'Modules' })
  await button.click()
  const menu = page.getByRole('navigation', { name: 'Product modules' })
  await expect(menu).toBeVisible()
  const b = await box(button)
  const m = await box(menu)
  const top = await box(page.locator('.shell-topbar'))
  expect(Math.abs(m.y - (top.y + top.height))).toBeLessThanOrEqual(2)
  expect(m.x).toBeGreaterThanOrEqual(16 - EPS)
  expect(m.x + m.width).toBeLessThanOrEqual(1600 - 16 + EPS)
  expect(m.x).toBeLessThanOrEqual(b.x + EPS)
  // Every item carries the line that says what its page is for
  const items = menu.locator('a[data-module]')
  expect(await items.count()).toBeGreaterThan(0)
  for (const item of await items.all()) await expect(item.locator('small')).toHaveText(/\S/)
})

for (const width of [1600, 390]) {
  test(`the notification panel holds its place at ${width}px`, async ({ page, api }) => {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/certificates')
    await page.getByRole('button', { name: /^Notifications/ }).click()
    const panel = page.getByRole('complementary', { name: 'Notifications' })
    await expect(panel).toBeVisible()
    const p = await box(panel)
    const top = await box(page.locator('.shell-topbar'))
    expect(Math.abs(p.x + p.width - width)).toBeLessThanOrEqual(EPS)
    expect(Math.abs(p.width - Math.min(420, width))).toBeLessThanOrEqual(EPS)
    if (width > 700) {
      expect(Math.abs(p.y - (top.y + top.height))).toBeLessThanOrEqual(EPS)
      const status = await box(page.getByRole('contentinfo'))
      expect(Math.abs(p.y + p.height - status.y)).toBeLessThanOrEqual(EPS)
    } else {
      // On a phone the panel covers the screen, bars included
      expect(p.y).toBeLessThanOrEqual(EPS)
      expect(Math.abs(p.height - 900)).toBeLessThanOrEqual(EPS)
    }
    await page.keyboard.press('Escape')
    await expect(panel).toBeHidden()
  })
}

// Intermediate widths fold the bar as the mockup: pins leave at 1100 px, icons and help at 1000 px
for (const width of [1250, 1100, 1000, 900, 801]) {
  test(`the top bar folds without overlap or empty box at ${width}px`, async ({ api: admin, signIn }) => {
    // Its own administrator: pins are a preference of the account, and the other tests share one
    const user = await createUser(admin, 'admin')
    const { page, api } = await signIn(user.username, user.password)
    await api.put('/account/preferences', { ...((await api.get('/account/preferences')) || {}), pins: ['reports', 'users', 'hsm'] })
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/certificates')
    const nav = page.getByRole('navigation', { name: 'Main navigation' })
    if (width <= 1100) for (const pin of await nav.locator('.shell-pinned').all()) await expect(pin).toBeHidden()
    else await expect(nav.locator('.shell-pinned')).toHaveCount(3)
    // Every visible item of the bar shows something, and none runs over the search
    const search = await box(page.locator('.shell-search'))
    for (const item of await nav.locator('.shell-navlink').all()) {
      if (!(await item.isVisible())) continue
      const b = await box(item)
      expect(b.x + b.width).toBeLessThanOrEqual(search.x + EPS)
      expect(b.width).toBeGreaterThan(30)
    }
    if (width <= 1000) for (const help of await page.locator('.shell-help').all()) await expect(help).toBeHidden()
  })
}

test('the search field, its key and the status dot keep the mockup sizes', async ({ page, api }) => {
  await page.setViewportSize({ width: 1600, height: 1000 })
  await page.goto('/certificates')
  const search = await box(page.locator('.shell-search'))
  expect(Math.abs(search.width - 177)).toBeLessThanOrEqual(EPS)
  expect(Math.abs(search.height - 35)).toBeLessThanOrEqual(EPS)
  expect(Math.abs((await box(page.locator('.shell-search kbd'))).height - 21)).toBeLessThanOrEqual(EPS)
  const dot = await box(page.locator('.shell-statusbar .shell-dot'))
  expect(Math.abs(dot.width - 6)).toBeLessThanOrEqual(0.5)
})

test('wide screens give the bars and the page 34 px margins', async ({ page, api }) => {
  await page.setViewportSize({ width: 1920, height: 1000 })
  await page.goto('/certificates')
  expect(Math.abs((await box(page.locator('.shell-brand'))).x - 34)).toBeLessThanOrEqual(EPS)
  expect(Math.abs((await box(page.locator('.shell-statusbar .shell-dot'))).x - 34)).toBeLessThanOrEqual(EPS)
})

test('a phone reads the whole page name in the picker, keeps 44 px targets and scrolls the whole document', async ({ page, api }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/certificates')
  const picker = page.getByRole('combobox', { name: 'Navigate' })
  const p = await box(picker)
  expect(p.width).toBeGreaterThanOrEqual(133)
  expect(await picker.evaluate(el => getComputedStyle(el).fontSize)).toBe('12px')
  for (const target of await page.locator('.shell-tools > *:visible, .shell-tools .shell-pop-wrap > button').all()) {
    if (!(await target.isVisible())) continue
    const b = await box(target)
    expect(b.height).toBeGreaterThanOrEqual(44 - EPS)
  }
  await expect(page.locator('.shell-help')).toBeHidden()
  // The status bar ends the document; the top bar sticks while it scrolls
  // Asked until it holds: the list still grows the document while its rows arrive
  await expect.poll(async () => {
    const docHeight = await page.evaluate(() => document.documentElement.scrollHeight)
    const status = await box(page.getByRole('contentinfo'))
    return Math.abs(status.y + status.height - docHeight)
  }).toBeLessThanOrEqual(1)
  await page.evaluate(() => window.scrollTo({ top: 400, behavior: 'instant' }))
  expect(Math.abs((await box(page.locator('.shell-topbar'))).y)).toBeLessThanOrEqual(EPS)
})

test('offline, the banner says so and the write buttons wait for the network', async ({ page, context, api }) => {
  await page.setViewportSize({ width: 1600, height: 1000 })
  await page.goto('/certificates')
  const issue = page.locator('.lv-head .lv-btn.is-primary')
  await expect(issue).toBeEnabled()
  await context.setOffline(true)
  try {
    await expect(page.locator('#shell-offline-banner')).toBeVisible()
    await expect(issue).toBeDisabled()
    await expect(issue).toHaveAttribute('aria-describedby', 'shell-offline-note')
  } finally {
    await context.setOffline(false)
  }
  await expect(page.locator('#shell-offline-banner')).toHaveCount(0)
  await expect(issue).toBeEnabled()
})
