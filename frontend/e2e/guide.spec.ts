import { test, expect, open } from './support/fixtures'

// Each test asks for `api`: it signs the administrator in on the page's own cookies

// The whole guide in a tab of its own: opened from the help dialog, its contents, an anchor, its search
test('the help dialog opens the guide on the page\'s chapter in a new tab', async ({ page, context, api: _api, consoleErrors }) => {
  await open(page, '/cas')
  await page.locator('.help-button').click()
  const dialog = page.getByTestId('help-dialog')
  await expect(dialog).toBeVisible()
  // At the top of the help, in its toolbar, in sight without scrolling the dialog
  const link = dialog.locator('.toolbar').getByRole('link', { name: 'Open in a new tab' })
  await expect(link).toHaveAttribute('href', '/guide/cas')
  await expect(link).toBeInViewport()
  await expect(dialog.locator('.modal-actions').getByRole('link')).toHaveCount(0)
  const [guide] = await Promise.all([context.waitForEvent('page'), link.click()])
  await guide.waitForLoadState()
  expect(new URL(guide.url()).pathname).toBe('/guide/cas')
  await expect(guide.getByRole('heading', { level: 1 })).toHaveText('Certificate Authorities')
  await expect(guide).toHaveTitle('Certificate Authorities · Guide · UCM')
  expect(consoleErrors).toEqual([])
})

test('on a phone, the help dialog keeps the guide\'s button in sight at its top, as an icon', async ({ page, api: _api, consoleErrors }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await open(page, '/cas')
  await page.keyboard.press('?')
  const dialog = page.getByTestId('help-dialog')
  await expect(dialog).toBeVisible()
  const link = dialog.locator('.toolbar').getByRole('link', { name: 'Open in a new tab' })
  await expect(link).toBeInViewport()
  expect(await dialog.evaluate((d) => d.scrollWidth <= d.clientWidth + 1)).toBe(true)
  expect(consoleErrors).toEqual([])
})

test('On this page reaches a section, which takes the focus and enters the address', async ({ page, api: _api, consoleErrors }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/guide/acme')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('ACME')
  const contents = page.getByRole('navigation', { name: 'Contents of the guide' })
  await expect(contents.locator('a[aria-current="page"]')).toHaveAttribute('href', '/guide/acme')
  await expect(contents.locator('a[href^="#"]')).toHaveCount(0)
  const onPage = page.getByRole('navigation', { name: 'On this page' })
  const section = onPage.locator('a[data-level="2"]').nth(3)
  const href = await section.getAttribute('href')
  await section.click()
  await expect(page).toHaveURL(new RegExp(`/guide/acme${href}$`))
  const heading = page.locator(href!)
  await expect(heading).toBeFocused()
  await expect(heading).toBeInViewport()
  await expect(section).toHaveAttribute('aria-current', 'true')
  // The document scrolled, the masthead and On this page held at the top, the heading clear of the masthead
  expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(200)
  await expect(page.locator('.guide-head')).toBeInViewport()
  await expect(onPage).toBeInViewport()
  const [bar, top] = await Promise.all([page.locator('.guide-head').boundingBox(), heading.boundingBox()])
  expect(top!.y).toBeGreaterThanOrEqual(bar!.y + bar!.height)
  // Reading on: the section further down becomes the one marked
  const later = onPage.locator('a[data-level="2"]').nth(5)
  await page.locator((await later.getAttribute('href'))!).evaluate((n) => window.scrollTo(0, window.scrollY + n.getBoundingClientRect().top - 70))
  await expect(later).toHaveAttribute('aria-current', 'true')
  expect(consoleErrors).toEqual([])
})

test('an address with an anchor opens on its section', async ({ page, api: _api, consoleErrors }) => {
  await page.goto('/guide/cas')
  const href = await page.locator('.guide-onpage a').nth(5).getAttribute('href')
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
  // On this page folds above the chapter, outside its article
  const fold = page.locator('details.guide-onpage-fold')
  await expect(fold).toBeVisible()
  await fold.locator('summary').click()
  await expect(fold.locator('a').first()).toBeVisible()
  const wide = await page.evaluate(() => [document.documentElement, document.body].some((e) => e.scrollWidth > e.clientWidth + 1))
  expect(wide).toBe(false)
})

// A browser's reader view decides at load: the chapter is in the page the server sends, before any script
test('the chapter\'s text is in the page at DOMContentLoaded, and React takes it over without a warning', async ({ page, api: _api, consoleErrors }) => {
  await page.addInitScript(() => {
    document.addEventListener('DOMContentLoaded', () => {
      const article = document.getElementById('guide-article')
      Object.assign(window, {
        atContentLoaded: { text: article?.textContent?.length || 0, sections: article?.querySelectorAll('h2').length || 0 },
        servedTitle: document.getElementById('guide-title'),
      })
    })
  })
  const raw = await (await page.request.get('/guide/acme')).text()
  expect(raw).toContain('<title>ACME · Guide · UCM</title>')
  expect(raw).toContain('<meta property="og:title" content="ACME" />')
  expect(raw).toMatch(/<h1 id="guide-title"[^>]*>ACME<\/h1>/)
  expect(raw).not.toContain('Open the page')
  await page.goto('/guide/acme', { waitUntil: 'domcontentloaded' })
  const seen = await page.evaluate(() => (window as unknown as { atContentLoaded: { text: number, sections: number } }).atContentLoaded)
  expect(seen.text).toBeGreaterThan(5000)
  expect(seen.sections).toBeGreaterThan(3)
  // Taken over: the account's rights add the page of the chapter
  await expect(page.locator('.guide-actions').getByRole('link', { name: 'Open the page' })).toHaveAttribute('href', '/acme')
  await expect(page).toHaveTitle('ACME · Guide · UCM')
  await expect(page.locator('meta[property="og:title"]')).toHaveCount(1)
  // The node the server sent is the one React holds: hydrated, not drawn again
  expect(await page.evaluate(() => {
    const served = (window as unknown as { servedTitle: Element | null }).servedTitle
    return !!served && served === document.getElementById('guide-title') && served.isConnected
  })).toBe(true)
  expect(consoleErrors).toEqual([])
})
