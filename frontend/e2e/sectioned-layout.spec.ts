import { test, expect } from './support/fixtures'

// Real geometry of the sectioned pages at 1600 px, as the Atelier form with a table of
// contents draws it: 200 px contents, 24 px gap, frames of 960 px at most (adjust.css --form-max)
const EPS = 1
const W = 1600
const H = 1000
const GUTTER = 24
const TOC = 200
const FORM = 960
type Box = { x: number; y: number; width: number; height: number }
const box = async (locator): Promise<Box> => {
  const b = await locator.boundingBox()
  expect(b).not.toBeNull()
  return b as Box
}

test.use({ viewport: { width: W, height: H } })

const PAGES = [
  { path: '/settings', toc: 'Settings sections', first: 'General' },
  { path: '/account', toc: 'Account sections', first: 'Profile' },
  { path: '/tools', toc: 'Tools', first: 'SSL Checker' },
  { path: '/operations', toc: 'Operations', first: 'Import' },
]

for (const { path, toc, first } of PAGES) {
  test(`${path} puts its contents left of frames held to the form measure`, async ({ page, api }) => {
    await page.goto(path)
    const nav = page.getByRole('navigation', { name: toc, exact: true })
    const frame = page.getByRole('region', { name: first, exact: true })
    await expect(frame).toBeVisible()
    const n = await box(nav)
    const f = await box(frame)
    expect(Math.abs(n.x - GUTTER)).toBeLessThanOrEqual(EPS)
    expect(Math.abs(n.width - TOC)).toBeLessThanOrEqual(EPS)
    expect(Math.abs(f.x - (GUTTER + TOC + GUTTER))).toBeLessThanOrEqual(EPS)
    expect(Math.abs(f.width - FORM)).toBeLessThanOrEqual(EPS)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  })
}

test('the settings save bar stays above the status bar and counts a change', async ({ page, api }) => {
  await page.goto('/settings')
  const bar = page.locator('#settings-savebar')
  await expect(bar).toBeVisible()
  const b = await box(bar)
  const status = await box(page.getByRole('contentinfo'))
  // 24 px above the status bar, the content scrolls in that band (the mockup's scroll-view padding)
  expect(Math.abs(status.y - (b.y + b.height) - 24)).toBeLessThanOrEqual(EPS)
  await expect(bar.getByRole('button', { name: 'Save', exact: true })).toBeDisabled()

  await page.getByLabel('Syslog hostname').fill(`e2e-${Date.now()}`)
  await expect(bar.getByRole('button', { name: 'Save', exact: true })).toBeEnabled()
  await bar.getByRole('button', { name: 'Undo changes' }).click()
  await expect(bar.getByRole('button', { name: 'Save', exact: true })).toBeDisabled()
})

test('a link to ?tab= lands the settings page on that frame', async ({ page, api }) => {
  await page.goto('/settings?tab=email')
  const title = page.locator('#set-title-email')
  await expect(title).toBeFocused()
  const t = await box(title)
  expect(t.y).toBeGreaterThanOrEqual(0)
  expect(t.y).toBeLessThan(H / 2)
})

test('every settings section is in view in the table of contents, no title cut', async ({ page, api }) => {
  await page.goto('/settings')
  const nav = page.getByRole('navigation', { name: 'Settings sections', exact: true })
  await expect(nav).toBeVisible()
  const status = await box(page.getByRole('contentinfo'))
  const links = nav.getByRole('link')
  expect(await links.count()).toBe(19)
  for (const item of await links.all()) {
    const r = await box(item)
    expect(r.y + r.height).toBeLessThanOrEqual(status.y - 24 + EPS)
  }
  expect(await nav.evaluate((el) => el.scrollHeight <= el.clientHeight)).toBe(true)
})

test('a short field takes one column of four, a button the width of its text', async ({ page, api }) => {
  await page.goto('/settings')
  const general = page.getByRole('region', { name: 'General', exact: true })
  await expect(general).toBeVisible()
  const port = await box(general.getByLabel('ACME public port'))
  const base = await box(general.getByLabel('Public URL', { exact: true }))
  // 918 px of fields in a 960 px card: 4 columns of 217.5 (short), the public URL on the whole line, 16 px gaps
  expect(Math.abs(port.width - 217.5)).toBeLessThanOrEqual(2)
  expect(Math.abs(base.width - 918)).toBeLessThanOrEqual(2)

  await page.goto('/tools')
  const run = page.getByRole('button', { name: 'Check SSL', exact: true })
  const r = await box(run)
  expect(r.width).toBeLessThan(200)
  expect(Math.abs(r.height - 32)).toBeLessThanOrEqual(EPS)
})

test('a field out of its bounds takes the error border, is named in the bar and sends nothing', async ({ page, api }) => {
  await page.goto('/settings')
  const general = page.getByRole('region', { name: 'General', exact: true })
  const field = general.getByLabel('Sign-out after inactivity (minutes)')
  await field.fill('99999')
  const bar = page.locator('#settings-savebar')
  // The bar names the changed field, as the mockup does
  await expect(bar).toContainText('Modified, not saved: Sign-out after inactivity (minutes).')
  let sent = false
  page.on('request', (r) => { if (r.method() !== 'GET' && r.url().includes('/api/v2/settings')) sent = true })
  await bar.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(field).toHaveAttribute('aria-invalid', 'true')
  await expect(general.getByText('Duration out of range: a whole number from 5 to 1440 minutes.')).toBeVisible()
  // The border itself turns to the error colour, not only the ring
  // Asked until it holds: the border colour eases in
  await expect.poll(() => field.evaluate((el) => {
    const probe = document.createElement('span')
    probe.style.color = 'var(--bad)'
    document.body.append(probe)
    const bad = getComputedStyle(probe).color
    probe.remove()
    return getComputedStyle(el).borderTopColor === bad
  })).toBe(true)
  expect(sent).toBe(false)
  await bar.getByRole('button', { name: 'Undo changes' }).click()
})

test('in Aurore a field in error keeps its red ring once focused, not the focus halo', async ({ page, api }) => {
  await page.goto('/settings')
  await page.evaluate(() => document.documentElement.setAttribute('data-theme', 'aurore'))
  const general = page.getByRole('region', { name: 'General', exact: true })
  const field = general.getByLabel('Sign-out after inactivity (minutes)')
  await field.fill('99999')
  const bar = page.locator('#settings-savebar')
  await bar.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(field).toBeFocused()
  // Asked until it holds: the ring eases in
  await expect.poll(() => field.evaluate((el) => {
    const probe = document.createElement('span')
    probe.style.color = 'var(--bad)'
    document.body.append(probe)
    const bad = getComputedStyle(probe).color
    probe.remove()
    return getComputedStyle(el).boxShadow === `${bad} 0px 0px 0px 1px`
  })).toBe(true)
  await bar.getByRole('button', { name: 'Undo changes' }).click()
})

test('the scheduler lists its tasks in the mockup module table, a mockup button in each row', async ({ page, api }) => {
  await page.goto('/settings?tab=scheduler')
  const rows = page.locator('#set-sec-scheduler .module-table tbody tr')
  await expect(rows.first()).toBeVisible()
  const run = rows.first().getByRole('button', { name: 'Run now' })
  // The mockup's .btn, at the height of the row's icon buttons (27 px), so that every row keeps the 36 px density (D1)
  expect(Math.abs((await box(run)).height - 27)).toBeLessThanOrEqual(EPS)
  const heights = await rows.evaluateAll((els) => els.map((el) => el.getBoundingClientRect().height))
  expect(Math.max(...heights)).toBeLessThanOrEqual(36 + EPS)
})

test('groups of a frame stand 20 px apart', async ({ page, api }) => {
  await page.goto('/settings')
  const groups = page.locator('#set-sec-general > .settings-body > .settings-group')
  await expect(groups.first()).toBeVisible()
  const boxes = await groups.evaluateAll((els) => els.map((el) => el.getBoundingClientRect()).map((r) => ({ top: r.top, bottom: r.bottom })))
  for (let i = 1; i < boxes.length; i++) expect(Math.abs(boxes[i].top - boxes[i - 1].bottom - 20)).toBeLessThanOrEqual(EPS)
})

test.describe('on a phone', () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })
  for (const [path, layout] of [['/settings', '.settings-layout'], ['/account', '.settings-layout'], ['/tools', '.settings-layout'], ['/operations', '.settings-layout']]) {
    test(`${path} is no wider than the phone`, async ({ page, api }) => {
      await page.goto(path)
      await expect(page.locator(layout)).toBeVisible()
      const wide = await page.evaluate((sel) => {
        const W = window.innerWidth
        return [...document.querySelectorAll(`${sel} *`)].filter((el) => {
          const r = el.getBoundingClientRect()
          if (!r.width || r.right <= W + 1) return false
          // content scrolling in its own box (tables, code) is not an overflow of the page
          for (let a = el.parentElement; a; a = a.parentElement) {
            if (['auto', 'scroll'].includes(getComputedStyle(a).overflowX)) return false
          }
          return true
        }).length
      }, layout)
      expect(wide).toBe(0)
    })
  }

  test('the bulk list of Operations keeps to its frame, its rows scrolling inside it', async ({ page, api }) => {
    await page.goto('/operations?tab=bulk')
    const frame = page.getByRole('region', { name: 'Bulk Actions', exact: true })
    await expect(frame.locator('.table-workspace')).toBeVisible()
    const f = await box(frame)
    for (const sel of ['.filters-row', '.table-workspace', '.table-workspace > .toolbar']) {
      const b = await box(frame.locator(sel).first())
      expect(b.x + b.width).toBeLessThanOrEqual(f.x + f.width + EPS)
    }
  })

  test('each scheduler task is a card with its run button on the screen', async ({ page, api }) => {
    await page.goto('/settings?tab=scheduler')
    const run = page.locator('#scheduler-records .mobile-record').getByRole('button', { name: 'Run now' })
    await expect(run.first()).toBeVisible()
    const off = await run.evaluateAll((els) => els.filter((el) => el.getBoundingClientRect().right > window.innerWidth).length)
    expect(off).toBe(0)
    await expect(page.locator('#set-sec-scheduler table')).toHaveCount(0)
  })
})
