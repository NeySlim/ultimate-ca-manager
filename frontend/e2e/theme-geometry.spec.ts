import { test, expect, createCA, issueCert, createUser } from './support/fixtures'
import { PALETTES, usePalette, expectPalette, boxes } from './support/themes'
import { freezeApi, type Frozen } from './support/frozen'

// Aurore set apart from Atelier by its accents only: a change of theme moves no box of the Certificates zone,
// and the focus ring glows in Aurore alone (the overview's boxes: overview.spec.ts)
test.use({ viewport: { width: 1600, height: 1000 } })

const CERTIFICATES = [
  '.masthead', '.main-nav > *', '.statusbar', '.view-btn', '.table-container', 'table.cert-table thead th',
  'table.cert-table tbody tr', 'table.cert-table tbody td', '.badge', '#inspector', '.detail-tabs [role=tab]', '.open-tab',
]

test('a change of theme moves nothing in the Certificates zone, its inspector open on a row', async ({ api, signIn }) => {
  const cert = await issueCert(api, (await createCA(api)).id)
  const user = await createUser(api, 'viewer')
  const measured: Record<string, Record<string, number[][]>> = {}
  // The view counters and the expiry count follow what other tests issue: every palette reads the first one's answers
  const kept: Frozen = new Map()
  for (const [family, mode] of PALETTES) {
    const { page } = await signIn(user.username, user.password)
    await freezeApi(page.context(), kept)
    await usePalette(page, family, mode)
    await page.goto('/certificates')
    await expectPalette(page, family, mode)
    const main = page.getByRole('main')
    await main.getByRole('searchbox').fill(cert.common_name)
    await main.getByRole('button', { name: cert.common_name, exact: true }).click()
    await expect(page.locator('#inspector').getByRole('heading', { name: cert.common_name })).toBeVisible()
    await expect(main.locator('table.cert-table tbody tr.opened')).toHaveCount(1)
    await expect(main.locator('table.measuring')).toHaveCount(0)
    measured[`${family}-${mode}`] = await boxes(page, CERTIFICATES)
    await page.context().close()
  }
  const reference = measured['atelier-dark']
  // Every selector found something: the pills, the sorted column and the open row are among the boxes
  for (const s of CERTIFICATES) expect(reference[s].length, s).toBeGreaterThan(0)
  expect(new Set(reference['table.cert-table tbody tr'].map((b) => b[3]))).toEqual(new Set([36]))
  for (const [key, got] of Object.entries(measured)) expect(got, key).toEqual(reference)
})

// The glow of the focus ring: a shadow with a blur, in the colour of --glow, beside the halo
async function focusModules(page) {
  for (let i = 0; i < 40; i++) {
    await page.keyboard.press('Tab')
    if (await page.evaluate(() => document.activeElement?.id === 'modules-button')) break
  }
  await expect(page.locator('#modules-button')).toBeFocused()
}
const ring = (page) => page.evaluate(() => {
  const el = document.activeElement as HTMLElement
  const css = getComputedStyle(el)
  const probe = document.createElement('span')
  probe.style.color = 'var(--glow)'
  el.append(probe)
  const glow = getComputedStyle(probe).color
  probe.remove()
  const blurred = css.boxShadow.split(/,(?![^(]*\))/).map((s) => s.trim()).find((s) => /^rgba?\([^)]*\) 0px 0px [1-9]\d*px/.test(s))
  return { outline: `${css.outlineStyle} ${css.outlineWidth}`, shadow: css.boxShadow, glow: Boolean(blurred?.startsWith(glow)) }
})

// `api` signs `page` in as the administrator
test('the focus ring glows in Aurore and not in Atelier, its outline kept in both', async ({ page, api: _signedIn }) => {
  for (const [family, mode] of PALETTES) {
    await usePalette(page, family, mode)
    await page.goto('/certificates')
    await expectPalette(page, family, mode)
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await focusModules(page)
    // Asked until it holds: Aurore eases its shadows in
    if (family === 'aurore') await expect.poll(async () => (await ring(page)).glow, `${family}-${mode}`).toBe(true)
    else expect((await ring(page)).shadow, `${family}-${mode}`).toBe('none')
    expect((await ring(page)).outline, `${family}-${mode}`).toBe('solid 2px')
    await page.unrouteAll({ behavior: 'ignoreErrors' })
  }
})

test('with motion reduced the hovers and the glow stand still', async ({ page, api: _signedIn }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await usePalette(page, 'aurore', 'dark')
  await page.goto('/certificates')
  await expectPalette(page, 'aurore', 'dark')
  const tab = page.locator('.view-btn').first()
  await expect(tab).toBeVisible()
  expect(await tab.evaluate((el) => getComputedStyle(el).transitionDuration.split(',').every((d) => parseFloat(d) === 0))).toBe(true)
  expect(await page.evaluate(() => getComputedStyle(document.body, '::before').animationName)).toBe('none')
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await expect.poll(() => tab.evaluate((el) => getComputedStyle(el).transitionDuration)).toMatch(/0\.14s/)
  expect(await page.evaluate(() => getComputedStyle(document.body, '::before').animationName)).toBe('shell-aurore-drift')
})
