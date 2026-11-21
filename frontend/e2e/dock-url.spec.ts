import { test, expect, createCA, issueCert } from './support/fixtures'

// The object open in a dock and its section live in the URL (`item`, `section`), as the mockup's:
// a reload reopens them, the browser's Back closes the dock, a search result lands on the object.
// The Certificates dock lists its open certificates in `open` once there are several.

test('a reload reopens the certificate, its section and the list as they were; Back closes the dock', async ({ page, api }) => {
  const cert = await issueCert(api, (await createCA(api)).id)
  const cn = cert.common_name
  await page.goto('/certificates')
  await page.getByRole('main').getByRole('searchbox').fill(cn)
  await expect(page).toHaveURL(url => url.searchParams.get('q') === cn)
  await page.getByRole('main').getByRole('button', { name: cn, exact: true }).click()
  const panel = page.locator('#inspector')
  await expect(panel.getByRole('heading', { name: cn })).toBeVisible()
  await panel.getByRole('tab', { name: 'Extensions', exact: true }).click()
  await expect(page).toHaveURL(url => url.searchParams.get('item') === String(cert.id) && url.searchParams.get('section') === 'extensions')

  await page.reload()
  await expect(panel.getByRole('heading', { name: cn })).toBeVisible()
  await expect(panel.getByRole('tab', { name: 'Extensions', exact: true })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByRole('main').getByRole('searchbox')).toHaveValue(cn)

  await page.goBack()
  await expect(page.locator('#inspector')).toHaveCount(0)
  await expect(page).toHaveURL(url => url.searchParams.get('q') === cn && !url.searchParams.has('item'))
})

test('several open certificates survive a reload and a visit to another page, each tab named', async ({ page, api }) => {
  const ca = (await createCA(api)).id
  const a = await issueCert(api, ca)
  const b = await issueCert(api, ca)
  // The mockup's open=…&active=…: every open certificate in `open`, the shown one in `item`
  await page.goto(`/certificates?item=${b.id}&open=${a.id},${b.id}`)
  const panel = page.locator('#inspector')
  const tab = (cert) => panel.locator(`[data-active="${cert.id}"]`).first()
  await expect(panel.getByRole('heading', { name: b.common_name })).toBeVisible()
  await expect(tab(a)).toHaveAttribute('title', a.common_name)
  await expect(tab(b)).toHaveAttribute('title', b.common_name)

  await page.reload()
  await expect(panel.getByRole('heading', { name: b.common_name })).toBeVisible()
  await expect(tab(a)).toHaveAttribute('title', a.common_name)

  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: 'Authorities' }).click()
  await expect(page).toHaveURL(url => url.pathname === '/cas')
  await page.goBack()
  await expect(panel.getByRole('heading', { name: b.common_name })).toBeVisible()
  await expect(tab(a)).toHaveAttribute('title', a.common_name)
  await expect(page).toHaveURL(url => url.searchParams.get('item') === String(b.id) && url.searchParams.get('open') === `${a.id},${b.id}`)
})

test('the sort of the certificate list survives a reload', async ({ page, api }) => {
  // Signed in, with a certificate for the list to sort
  await issueCert(api, (await createCA(api)).id)
  await page.goto('/certificates?sort=name&order=desc')
  await expect(page.getByRole('main').locator('th.col-name')).toHaveAttribute('aria-sort', 'descending')
  await page.reload()
  await expect(page.getByRole('main').locator('th.col-name')).toHaveAttribute('aria-sort', 'descending')
})

test('a template opened in its dock comes back on its section after a reload', async ({ page, api }) => {
  const data = await api.get('/templates?per_page=500')
  const tpl = ((Array.isArray(data) ? data : data.items || data.templates) as any[])[0]
  await page.goto('/templates')
  await page.getByRole('main').getByRole('button', { name: tpl.name, exact: true }).first().click()
  const panel = page.locator('#inspector')
  const second = panel.getByRole('tab').nth(1)
  await second.click()
  await expect(page).toHaveURL(url => url.searchParams.get('item') === String(tpl.id) && url.searchParams.has('section'))
  await page.reload()
  await expect(panel.getByRole('heading', { level: 2 })).toContainText(tpl.name)
  await expect(panel.getByRole('tab').nth(1)).toHaveAttribute('aria-selected', 'true')
})

test('a template found by the search opens in its page\'s dock', async ({ page, api }) => {
  const data = await api.get('/templates?per_page=500')
  const tpl = ((Array.isArray(data) ? data : data.items || data.templates) as any[])[0]
  await page.goto('/cas')
  await page.keyboard.press('Control+k')
  const palette = page.getByTestId('command-palette')
  await palette.getByPlaceholder('Certificate, page or action…').fill(tpl.name)
  await palette.getByRole('button', { name: new RegExp(`^${tpl.name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`) }).first().click()
  await expect(page).toHaveURL(url => url.pathname === '/templates' && url.searchParams.get('item') === String(tpl.id))
  await expect(page.locator('#inspector').getByRole('heading', { level: 2 })).toContainText(tpl.name)
})
