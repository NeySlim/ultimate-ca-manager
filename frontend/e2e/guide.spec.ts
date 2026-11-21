import { test, expect, open } from './support/fixtures'

// Each test asks for `api`: it signs the administrator in on the page's own cookies

// The whole guide in a tab of its own: opened from the help dialog, its contents, an anchor, its search
test('the help dialog opens the guide on the page\'s chapter in a new tab', async ({ page, context, api: _api, consoleErrors }) => {
  await open(page, '/cas')
  await page.locator('.help-button').click()
  const dialog = page.getByTestId('help-dialog')
  await expect(dialog).toBeVisible()
  const link = dialog.getByRole('link', { name: 'Open in a new tab' })
  await expect(link).toHaveAttribute('href', '/guide/cas')
  const [guide] = await Promise.all([context.waitForEvent('page'), link.click()])
  await guide.waitForLoadState()
  expect(new URL(guide.url()).pathname).toBe('/guide/cas')
  await expect(guide.getByRole('heading', { level: 1 })).toHaveText('Certificate Authorities')
  await expect(guide).toHaveTitle('Certificate Authorities · Guide · UCM')
  expect(consoleErrors).toEqual([])
})

test('the contents reach a section, which takes the focus and enters the address', async ({ page, api: _api, consoleErrors }) => {
  await page.goto('/guide/acme')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('ACME')
  const contents = page.getByRole('navigation', { name: 'Contents of the guide' })
  await expect(contents.locator('a[aria-current="page"]')).toHaveAttribute('href', '/guide/acme')
  const section = contents.locator('.guide-toc-sections a').nth(3)
  const href = await section.getAttribute('href')
  await section.click()
  await expect(page).toHaveURL(new RegExp(`/guide/acme${href}$`))
  const heading = page.locator(href!)
  await expect(heading).toBeFocused()
  await expect(heading).toBeInViewport()
  await expect(section).toHaveAttribute('aria-current', 'true')
  expect(consoleErrors).toEqual([])
})

test('an address with an anchor opens on its section', async ({ page, api: _api, consoleErrors }) => {
  await page.goto('/guide/cas')
  const href = await page.locator('.guide-toc-sections a').nth(5).getAttribute('href')
  await page.goto(`/guide/cas${href}`)
  const heading = page.locator(href!)
  await expect(heading).toBeFocused()
  await expect(heading).toBeInViewport()
  expect(consoleErrors).toEqual([])
})

test('the search finds sections over the whole guide and marks the words in the one it opens', async ({ page, api: _api, consoleErrors }) => {
  await page.goto('/guide/navigation')
  const field = page.getByRole('searchbox', { name: 'Search the whole guide' })
  await field.fill('REVOCATION crl')
  const results = page.locator('.guide-result')
  await expect(results.first()).toBeVisible()
  await expect(page.locator('.guide-results-count')).toHaveText(/\d+ results?/)
  await expect(results.first().locator('mark.guide-hit').first()).toBeVisible()
  await field.press('ArrowDown')
  await expect(results.first()).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/guide\/[^?]+\?q=REVOCATION%20crl/)
  await expect(page.locator('#guide-article mark.guide-hit').first()).toBeVisible()
  await field.fill('zzqqxx nothing')
  await expect(page.locator('.guide-results')).toContainText('No results. Try another word.')
  await page.keyboard.press('Escape')
  await expect(page.locator('.guide-results')).toBeHidden()
  expect(consoleErrors).toEqual([])
})

test('the page has no horizontal scroll on a phone', async ({ page, api: _api }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/guide/acme')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('ACME')
  await expect(page.getByLabel('Chapter', { exact: true })).toBeVisible()
  const wide = await page.evaluate(() => [...document.querySelectorAll('.guide-scroll, html')].some((e) => e.scrollWidth > e.clientWidth + 1))
  expect(wide).toBe(false)
})
