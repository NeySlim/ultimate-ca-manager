import { test, expect, createCA, issueCert, createUser } from './support/fixtures'

// Real geometry of the Certificates zone (the Atelier mockup's tableView() and inspector()) at
// 1600 px and on a phone: jsdom measures nothing
const EPS = 1
const W = 1600
const H = 1000
const GUTTER = 24
type Box = { x: number; y: number; width: number; height: number }
const box = async (locator): Promise<Box> => {
  const b = await locator.boundingBox()
  expect(b).not.toBeNull()
  return b as Box
}

// Other tests issue certificates at the same time: the list is searched down to this one
async function openListOn(page, name: string) {
  await page.goto('/certificates')
  await page.getByRole('main').getByRole('searchbox').fill(name)
  await expect(page.getByRole('main').getByRole('button', { name, exact: true }).first()).toBeVisible()
}

test.use({ viewport: { width: W, height: H } })

// The inspector's size and fold are preferences of the account: tests that change them take their own
async function ownSession(api, signIn) {
  const user = await createUser(api, 'viewer')
  return (await signIn(user.username, user.password)).page
}

test('the list shows its seven columns on one line and the inspector opens under it', async ({ api, signIn }) => {
  const cert = await issueCert(api, (await createCA(api)).id)
  const page = await ownSession(api, signIn)
  await openListOn(page, cert.common_name)
  const main = page.getByRole('main')

  // Seven data columns, none pushing the table sideways
  const headers = main.locator('table.cert-table thead th').filter({ hasNotText: /^$/ }).filter({ hasNotText: 'Actions' })
  await expect(headers).toHaveCount(7)
  const scroller = main.locator('#cert-scroll')
  expect(await scroller.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true)

  // The mockup's 36 px rows
  const heights = await main.locator('table.cert-table tbody tr').evaluateAll(rows => rows.map(r => Math.round(r.getBoundingClientRect().height)))
  expect(heights.length).toBeGreaterThan(0)
  expect(new Set(heights)).toEqual(new Set([36]))

  // Opened: the inspector follows the list inside the page margins, above the status bar
  await main.getByRole('button', { name: cert.common_name, exact: true }).click()
  const dock = page.locator('#inspector')
  await expect(dock).toBeVisible()
  await expect(dock.getByRole('heading', { name: cert.common_name })).toBeVisible()
  const d = await box(dock)
  const bar = await box(page.getByRole('contentinfo'))
  const list = await box(main.locator('.table-container'))
  expect(Math.abs(d.x - GUTTER)).toBeLessThanOrEqual(EPS)
  expect(Math.abs(W - (d.x + d.width) - GUTTER)).toBeLessThanOrEqual(EPS)
  expect(Math.abs(d.y + d.height - bar.y)).toBeLessThanOrEqual(EPS)
  expect(list.y + list.height).toBeLessThanOrEqual(d.y + EPS)
  expect(await dock.evaluate(el => getComputedStyle(el).position)).not.toBe('fixed')
  // The row of the open certificate is marked
  await expect(main.getByRole('row', { name: new RegExp(cert.common_name.replace(/\./g, '\\.')) })).toHaveClass(/opened/)

  // Folded to its tab strip (35 px), it gives the room back to the list
  await dock.getByRole('button', { name: 'Fold the inspector' }).click()
  expect(Math.round((await box(dock)).height)).toBe(35)
  await dock.getByRole('button', { name: 'Unfold the inspector' }).click()
})

test('the inspector band grows to 420 px and Escape closes it from the list', async ({ api, signIn }) => {
  const cert = await issueCert(api, (await createCA(api)).id)
  const page = await ownSession(api, signIn)
  await openListOn(page, cert.common_name)
  const main = page.getByRole('main')
  await main.getByRole('button', { name: cert.common_name, exact: true }).click()
  const dock = page.locator('#inspector')
  await expect(dock).toBeVisible()
  expect(Math.round((await box(dock)).height)).toBe(278)
  await dock.getByRole('button', { name: 'Enlarge the inspector' }).click()
  expect(Math.round((await box(dock)).height)).toBe(420)
  await main.getByRole('searchbox').focus()
  await page.keyboard.press('Escape')
  await expect(dock).toBeHidden()
})

test('the actions of a certificate open in the mockup dialog, revoke in red', async ({ page, api }) => {
  const cert = await issueCert(api, (await createCA(api)).id)
  await openListOn(page, cert.common_name)
  await page.getByRole('main').getByRole('button', { name: cert.common_name, exact: true }).click()
  const dock = page.locator('#inspector')
  await dock.getByRole('button', { name: `Other actions for ${cert.common_name}` }).click()
  const dialog = page.getByRole('dialog', { name: 'Certificate actions' })
  await expect(dialog).toBeVisible()
  expect(Math.round((await box(dialog)).width)).toBe(520)
  await expect(dialog.locator('.columns-list .btn.danger').first()).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()
})

// The page scrolls under a finger or a wheel until the pagination of the list is on screen
async function footerReachedByScrolling(page, api, height: number) {
  const ca = await createCA(api)
  for (let i = 0; i < 8; i++) await issueCert(api, ca.id)
  await page.goto('/certificates')
  const main = page.getByRole('main')
  const next = main.locator('.table-footer').getByRole('button', { name: 'Next page' })
  await expect(next).toBeAttached()
  await page.mouse.move(195, height / 2)
  for (let i = 0; i < 8; i++) await page.mouse.wheel(0, 500)
  const bar = (await box(page.getByRole('contentinfo'))).y
  await expect.poll(async () => { const b = await box(next); return b.y >= 0 && b.y + b.height <= bar }).toBe(true)
}

for (const [w, h] of [[390, 844], [800, 1000]]) {
  test.describe(`the list at ${w} x ${h}`, () => {
    test.use({ viewport: { width: w, height: h } })
    test('scrolls down to its pagination, nothing sideways', async ({ page, api }) => {
      await footerReachedByScrolling(page, api, h)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    })
  })
}

test.describe('on a phone', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('each certificate is a record with its chevron on screen, and the inspector takes the screen', async ({ page, api }) => {
    const cert = await issueCert(api, (await createCA(api)).id)
    await openListOn(page, cert.common_name)
    const main = page.getByRole('main')
    await expect(main.getByRole('table')).toHaveCount(0)
    const record = main.locator('article.mobile-record').filter({ has: page.getByRole('button', { name: cert.common_name, exact: true }) })
    await expect(record).toBeVisible()
    const r = await box(record)
    expect(r.x).toBeGreaterThanOrEqual(16 - EPS)
    expect(r.x + r.width).toBeLessThanOrEqual(390 - 16 + EPS)
    const chevron = await box(record.locator('.row-top > .icon-btn'))
    expect(chevron.x + chevron.width).toBeLessThanOrEqual(390)
    expect(Math.round(chevron.width)).toBeGreaterThanOrEqual(44)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await record.locator('.row-meta').click()
    const dock = page.locator('#inspector')
    await expect(dock).toBeVisible()
    const d = await box(dock)
    expect(Math.round(d.x)).toBe(0)
    expect(Math.round(d.width)).toBe(390)
    expect(Math.round(d.height)).toBe(844)
    await expect(dock.getByRole('button', { name: 'Close inspector' })).toBeFocused()
  })
})

test.describe('at 1000 px', () => {
  test.use({ viewport: { width: 1000, height: 1000 } })

  test('the overview takes two columns and leaves the chain out, as the mockup', async ({ page, api }) => {
    const cert = await issueCert(api, (await createCA(api)).id)
    await openListOn(page, cert.common_name)
    await page.getByRole('main').getByRole('button', { name: cert.common_name, exact: true }).click()
    const overview = page.getByTestId('certificate-overview')
    await expect(overview).toBeVisible()
    expect(await overview.evaluate(el => getComputedStyle(el).gridTemplateColumns.split(' ').length)).toBe(2)
    await expect(overview.locator('.overview-chain')).toBeHidden()
  })
})
