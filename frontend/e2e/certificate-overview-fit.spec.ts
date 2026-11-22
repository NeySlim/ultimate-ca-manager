import { test, expect, createCA, issueCert, uid } from './support/fixtures'

// The overview of an ordinary certificate (four alternative names, a chain of three levels) shows
// « More details » without a scroll: in a floating window at its default size and at 840 x 500, and
// in the dock at the right at its default width, at 1440 x 900 and 1280 x 800 (INSP-FIT)

// The page reads the dock at the right; the shared account's preference is never written
async function dockRight(page) {
  const right = { position: 'right', height: 278, width: 460 }
  await page.route('**/api/v2/account/preferences', async (route) => {
    if (route.request().method() !== 'GET') return route.fulfill({ status: 200, contentType: 'application/json', body: '{"data":{}}' })
    const response = await route.fetch()
    const body = await response.json()
    body.data = { ...(body.data || {}), inspector: right }
    return route.fulfill({ response, json: body })
  })
  await page.route('**/api/v2/auth/verify', async (route) => {
    const response = await route.fetch()
    const body = await response.json()
    if (body?.data) body.data.preferences = { ...(body.data.preferences || {}), inspector: right }
    return route.fulfill({ response, json: body })
  })
}

async function ordinaryCertificate(api) {
  const root = await createCA(api)
  const issuing = await createCA(api, { parentCAId: root.id })
  const cn = `${uid('fit')}.example.com`
  return issueCert(api, issuing.id, { cn, san_dns: [cn, `www.${cn}`], san_ip: ['192.0.2.10'], san_email: [`admin@${cn}`] })
}

async function openInDock(page, cn: string) {
  await page.goto('/certificates')
  await page.getByRole('main').getByRole('searchbox').fill(cn)
  await page.getByRole('main').getByRole('button', { name: cn, exact: true }).click()
  const dock = page.locator('#inspector')
  await expect(dock.getByRole('heading', { name: cn })).toBeVisible()
  await expect(dock.locator('[data-testid=certificate-overview] .chain-mini li')).toHaveCount(3)
  return dock
}

// The toggle lies inside the panel's visible box, the panel not scrolled
async function expectMoreDetailsInView(scope) {
  const panel = scope.locator('.detail-panel')
  const toggle = panel.locator('.advanced-toggle')
  await expect(toggle).toBeVisible()
  expect(await panel.evaluate((el) => el.scrollTop)).toBe(0)
  const p = (await panel.boundingBox())!
  const b = (await toggle.boundingBox())!
  expect(b.y).toBeGreaterThanOrEqual(p.y - 0.5)
  expect(b.y + b.height, 'the bottom of « More details » against the bottom of the panel').toBeLessThanOrEqual(p.y + p.height + 0.5)
}

test.describe('in a floating window', () => {
  test.use({ viewport: { width: 1440, height: 900 } })

  test('at its default size and at 840 x 500', async ({ page, api }) => {
    const cert = await ordinaryCertificate(api)
    const dock = await openInDock(page, cert.common_name)
    await dock.getByRole('button', { name: 'Detach into a window' }).click()
    const win = page.getByRole('dialog', { name: cert.common_name })
    await expect(win.locator('[data-testid=certificate-overview]')).toBeVisible()
    let r = (await win.boundingBox())!
    expect([Math.round(r.width), Math.round(r.height)]).toEqual([620, 560])
    await expectMoreDetailsInView(win)

    // Shift and the arrows resize the window by 20 px a step
    await win.locator('[data-action=float-move]').focus()
    for (let i = 0; i < 11; i += 1) await page.keyboard.press('Shift+ArrowRight')
    for (let i = 0; i < 3; i += 1) await page.keyboard.press('Shift+ArrowUp')
    await expect.poll(async () => { r = (await win.boundingBox())!; return [Math.round(r.width), Math.round(r.height)] }).toEqual([840, 500])
    await expectMoreDetailsInView(win)
  })
})

for (const [w, h] of [[1440, 900], [1280, 800]]) {
  test.describe(`in the dock at the right at ${w} x ${h}`, () => {
    test.use({ viewport: { width: w, height: h } })

    test('at its default width', async ({ page, api }) => {
      const cert = await ordinaryCertificate(api)
      await dockRight(page)
      const dock = await openInDock(page, cert.common_name)
      expect(Math.round((await dock.boundingBox())!.width)).toBe(460)
      await expectMoreDetailsInView(dock)
    })
  })
}
