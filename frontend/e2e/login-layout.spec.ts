import { test, expect } from './support/fixtures'

// Real geometry of the sign-in card at 1600 x 1000 and at phone width: jsdom measures nothing
const EPS = 1
type Box = { x: number; y: number; width: number; height: number }
const box = async (locator): Promise<Box> => {
  const b = await locator.boundingBox()
  expect(b).not.toBeNull()
  return b as Box
}

test.describe('sign-in card at 1600 px', () => {
  test.use({ viewport: { width: 1600, height: 1000 } })

  test('a 420 px card centred on the page, fields and button its full inner width', async ({ page }) => {
    await page.context().clearCookies()
    await page.goto('/login')
    const card = page.getByRole('region', { name: 'Sign in', exact: true })
    await expect(card).toBeVisible()
    const c = await box(card)
    expect(Math.abs(c.width - 420)).toBeLessThanOrEqual(EPS)
    expect(Math.abs(c.x + c.width / 2 - 800)).toBeLessThanOrEqual(EPS)

    // 32 px of padding each side: the fields and the button span 356 px
    const user = await box(page.getByLabel('Username', { exact: true }))
    const pass = await box(page.getByLabel('Password', { exact: true }))
    const submit = await box(page.getByRole('button', { name: 'Sign in', exact: true }))
    for (const b of [user, pass, submit]) {
      expect(Math.abs(b.x - (c.x + 33))).toBeLessThanOrEqual(EPS)
      expect(Math.abs(b.width - 354)).toBeLessThanOrEqual(EPS)
      expect(Math.abs(b.height - 40)).toBeLessThanOrEqual(EPS)
    }
    // Username above password above the button, 14 px apart between field blocks
    expect(user.y).toBeLessThan(pass.y)
    expect(pass.y).toBeLessThan(submit.y)
    expect(Math.abs(submit.y - (pass.y + pass.height) - 14)).toBeLessThanOrEqual(EPS)

    // The title at 24 px, semibold; the theme and language buttons at the top right
    const title = page.getByRole('heading', { level: 1, name: 'Sign in', exact: true })
    expect(await title.evaluate(el => getComputedStyle(el).fontSize)).toBe('24px')
    expect(await title.evaluate(el => getComputedStyle(el).fontWeight)).toBe('600')
    const theme = await box(page.getByRole('button', { name: /^Theme: / }))
    expect(Math.abs(theme.x + theme.width - (1600 - 16))).toBeLessThanOrEqual(EPS)
    expect(Math.abs(theme.y - 12)).toBeLessThanOrEqual(EPS)
    await expect(page.getByRole('button', { name: 'Language', exact: true })).toBeVisible()

    // Nothing scrolls sideways
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  })

  test('hover and focus change at once: no fade on the fields, buttons and links of the frame', async ({ page }) => {
    await page.context().clearCookies()
    await page.goto('/login')
    await expect(page.getByRole('region', { name: 'Sign in', exact: true })).toBeVisible()
    const durations = await page.evaluate(() => ['#login-user', '#login-pass', '.auth-submit', '#login-reveal', '.auth-foot a', '.auth-tools .icon-btn']
      .map(s => getComputedStyle(document.querySelector(s) as Element).transitionDuration))
    expect(durations).toEqual(['0s', '0s', '0s', '0s', '0s', '0s'])
  })
})

test('a window shorter than the sign-in card scrolls down to the foot', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 420 })
  await page.context().clearCookies()
  await page.goto('/login')
  const foot = page.locator('.auth-foot')
  await expect(foot).toBeAttached()
  // By the wheel, as a reader does: a script could scroll a clipped page, a hand cannot
  await page.mouse.move(640, 210)
  await page.mouse.wheel(0, 3000)
  await expect.poll(async () => {
    const f = await foot.boundingBox()
    return f ? f.y + f.height : Infinity
  }).toBeLessThanOrEqual(420)
  await page.mouse.wheel(0, -3000)
  await expect.poll(async () => (await page.locator('.auth-tools').boundingBox())?.y).toBeGreaterThanOrEqual(0)
})

test.describe('sign-in card at phone width', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('the card takes the width less 14 px each side and starts under the tools', async ({ page }) => {
    await page.context().clearCookies()
    await page.goto('/login')
    const card = page.getByRole('region', { name: 'Sign in', exact: true })
    await expect(card).toBeVisible()
    const c = await box(card)
    expect(Math.abs(c.x - 14)).toBeLessThanOrEqual(EPS)
    expect(Math.abs(c.width - (390 - 28))).toBeLessThanOrEqual(EPS)
    expect(Math.abs(c.y - 56)).toBeLessThanOrEqual(EPS)
    const theme = await box(page.getByRole('button', { name: /^Theme: / }))
    expect(Math.abs(theme.width - 40)).toBeLessThanOrEqual(EPS)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  })

  test('the theme and language menus open 8 px under their button, never over it', async ({ page }) => {
    await page.context().clearCookies()
    await page.goto('/login')
    for (const [name, menu] of [[/^Theme: /, '#theme-menu'], ['Language', '#language-menu']] as const) {
      const button = page.getByRole('button', { name, exact: true })
      const b = await box(button)
      await button.click()
      const m = await box(page.locator(menu))
      expect(Math.abs(m.y - (b.y + b.height + 8))).toBeLessThanOrEqual(EPS)
      expect(Math.abs(m.x + m.width - (b.x + b.width))).toBeLessThanOrEqual(EPS)
      expect(m.x).toBeGreaterThanOrEqual(0)
      await page.keyboard.press('Escape')
    }
  })

  test('in Aurore the language menu is the glass panel of the theme menu, 220 px', async ({ page }) => {
    await page.context().clearCookies()
    await page.goto('/login')
    await page.getByRole('button', { name: /^Theme: / }).click()
    await page.getByRole('menuitemradio', { name: 'Aurore dark', exact: true }).click()
    await page.getByRole('button', { name: 'Language', exact: true }).click()
    const menu = page.getByRole('menu', { name: 'Language', exact: true })
    await expect(menu).toBeVisible()
    const panel = await menu.evaluate(el => ({ blur: getComputedStyle(el).backdropFilter, width: el.getBoundingClientRect().width }))
    expect(panel.blur).toContain('blur(16px)')
    expect(Math.abs(panel.width - 220)).toBeLessThanOrEqual(EPS)
  })
})

test.describe('sign-in page by keyboard', () => {
  test('the first tab stop skips to the content, the tab names the screen', async ({ page }) => {
    await page.context().clearCookies()
    await page.goto('/login')
    await expect(page.getByRole('heading', { level: 1, name: 'Sign in', exact: true })).toBeVisible()
    await expect(page).toHaveTitle('Sign in · UCM')
    await page.keyboard.press('Tab')
    const skip = page.getByRole('link', { name: 'Skip to content', exact: true })
    await expect(skip).toBeFocused()
    const s = await box(skip)
    expect(Math.abs(s.y - 12)).toBeLessThanOrEqual(EPS)
  })
})
