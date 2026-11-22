import { test, expect, createCA, issueCert, uid } from './support/fixtures'

// The detached windows and the comparison of certificates, and the activity of the status bar

async function openInInspector(page, cn: string) {
  await page.getByRole('main').getByRole('searchbox').fill(cn)
  await page.getByRole('main').getByRole('button', { name: cn, exact: true }).click()
  await expect(page.locator('#inspector').getByRole('heading', { name: cn })).toBeVisible()
}

const box = async (locator) => (await locator.boundingBox())!

test('two certificates detached into windows move, come in front and close', async ({ page, api }) => {
  const ca = await createCA(api)
  const tag = uid('float')
  const a = await issueCert(api, ca.id, { cn: `${tag}-a.example.com` })
  const b = await issueCert(api, ca.id, { cn: `${tag}-b.example.com` })
  await page.goto('/certificates')

  await openInInspector(page, a.common_name)
  await page.locator('#inspector').getByRole('button', { name: 'Detach into a window' }).click()
  const winA = page.getByRole('dialog', { name: a.common_name })
  await expect(winA).toBeVisible()
  await expect(winA).toHaveAttribute('aria-modal', 'false')
  // The window shows the inspector's sections: its Extensions tab reads the certificate
  await winA.getByRole('tab', { name: 'Extensions', exact: true }).click()
  await expect(winA).toContainText(new RegExp(`DNS:\\s*${a.common_name.replace(/\./g, '\\.')}`))

  // Dragged by its title bar, the window moves by as much as the pointer (here off the list)
  const ra = await box(winA)
  const title = winA.locator('.float-title h2')
  const t = await box(title)
  await page.mouse.move(t.x + 10, t.y + t.height / 2)
  await page.mouse.down()
  await page.mouse.move(t.x + 610, t.y + t.height / 2 + 120, { steps: 8 })
  await page.mouse.up()
  const moved = await box(winA)
  expect(Math.round(moved.x - ra.x)).toBe(600)
  expect(Math.round(moved.y - ra.y)).toBe(120)

  await openInInspector(page, b.common_name)
  await page.locator('#inspector').getByRole('button', { name: 'Detach into a window' }).click()
  const winB = page.getByRole('dialog', { name: b.common_name })
  await expect(winB).toBeVisible()
  // Cascaded: the second opens down and right of where the first opened, in front of it
  const rb = await box(winB)
  expect(rb.x).toBeGreaterThan(ra.x)
  expect(rb.y).toBeGreaterThan(ra.y)
  const z = async (w) => Number(await w.evaluate((el) => el.style.zIndex))
  expect(await z(winB)).toBeGreaterThan(await z(winA))
  // Touched, the first comes in front of the second
  // A press on its title bar, clear of the second window and of the tools
  await winA.locator('.float-head').click({ position: { x: (await box(winA)).width - 140, y: 12 } })
  expect(await z(winA)).toBeGreaterThan(await z(winB))

  // The keyboard of its handle: an arrow moves it, Shift and an arrow resize it
  const handle = winA.getByRole('button', { name: 'Move or resize the window' })
  await handle.focus()
  await page.keyboard.press('ArrowRight')
  expect(Math.round((await box(winA)).x - moved.x)).toBe(20)
  await page.keyboard.press('Shift+ArrowDown')
  expect(Math.round((await box(winA)).height - moved.height)).toBe(20)

  // Inside the visible area, the status bar left free
  const view = page.viewportSize()!
  for (const w of [winA, winB]) {
    const r = await box(w)
    expect(r.x).toBeGreaterThanOrEqual(0)
    expect(r.x + r.width).toBeLessThanOrEqual(view.width)
    expect(r.y + r.height).toBeLessThanOrEqual(view.height)
  }

  // The status bar lists both and brings one back in front
  const bar = page.locator('footer.statusbar')
  // By the keyboard (a message of another test may sit over the bar): the front window first
  await bar.getByRole('button', { name: '2 windows' }).focus()
  await page.keyboard.press('Enter')
  await expect(bar.getByRole('menuitem', { name: a.common_name })).toBeFocused()
  await page.keyboard.press('ArrowDown')
  await expect(bar.getByRole('menuitem', { name: b.common_name })).toBeFocused()
  await page.keyboard.press('Enter')
  expect(await z(winB)).toBeGreaterThan(await z(winA))
  await expect(winB.getByRole('button', { name: 'Move or resize the window' })).toBeFocused()

  // The cross of the window behind closes it at the first press
  await winA.getByRole('button', { name: `Close the window ${a.common_name}` }).click()
  await expect(winA).toHaveCount(0)
  // Escape closes the window that has the focus
  await winB.getByRole('button', { name: 'Move or resize the window' }).focus()
  await page.keyboard.press('Escape')
  await expect(page.locator('[data-detached]')).toHaveCount(0)
})

test('a detached window stays when the page changes and keeps its place after a reload', async ({ page, api }) => {
  const cert = await issueCert(api, (await createCA(api)).id)
  await page.goto('/certificates')
  await openInInspector(page, cert.common_name)
  await page.locator('#inspector').getByRole('button', { name: 'Detach into a window' }).click()
  const win = page.getByRole('dialog', { name: cert.common_name })
  await win.getByRole('button', { name: 'Move or resize the window' }).focus()
  await page.keyboard.press('ArrowDown')
  const placed = await box(win)
  await page.goto('/cas')
  await expect(win).toBeVisible()
  await page.reload()
  await expect(win).toBeVisible()
  expect(Math.round((await box(win)).y)).toBe(Math.round(placed.y))
})

// Maximized: the work area under the masthead and over the status bar, inside the stage's margins (24 px here)
async function expectMaximized(page, win) {
  const view = page.viewportSize()!
  const main = await box(page.locator('.shell-main'))
  const bar = await box(page.locator('footer.statusbar'))
  const r = await box(win)
  expect(Math.round(r.x)).toBe(24)
  expect(Math.round(r.y)).toBe(Math.round(main.y) + 24)
  expect(Math.round(r.x + r.width)).toBe(view.width - 24)
  expect(Math.round(r.y + r.height)).toBe(Math.round(bar.y) - 24)
}

for (const size of [{ width: 1440, height: 900 }, { width: 1024, height: 700 }]) {
  test(`at ${size.width} x ${size.height} a window maximizes into the work area and restores to the pixel`, async ({ page, api }) => {
    await page.setViewportSize(size)
    const cert = await issueCert(api, (await createCA(api)).id)
    await page.goto('/certificates')
    await openInInspector(page, cert.common_name)
    await page.locator('#inspector').getByRole('button', { name: 'Detach into a window' }).click()
    const win = page.getByRole('dialog', { name: cert.common_name })
    await expect(win).toBeVisible()

    // The move handle, apart from the maximize button: the keyboard and the mouse move the window
    const handle = win.getByRole('button', { name: 'Move or resize the window' })
    const opened = await box(win)
    await handle.focus()
    await page.keyboard.press('ArrowRight')
    expect(Math.round((await box(win)).x - opened.x)).toBe(20)
    const h = await box(handle)
    await page.mouse.move(h.x + h.width / 2, h.y + h.height / 2)
    await page.mouse.down()
    await page.mouse.move(h.x + h.width / 2 + 40, h.y + h.height / 2 + 30, { steps: 5 })
    await page.mouse.up()
    const placed = await box(win)
    expect(Math.round(placed.x - opened.x)).toBe(60)
    expect(Math.round(placed.y - opened.y)).toBe(30)

    await win.getByRole('button', { name: 'Maximize the window' }).click()
    await expectMaximized(page, win)
    await win.getByRole('button', { name: 'Restore the window' }).click()
    expect(await box(win)).toEqual(placed)

    // A double-click on the title bar does the same, and a drag of a maximized window moves nothing
    await win.locator('.float-title h2').dblclick()
    await expectMaximized(page, win)
    const t = await box(win.locator('.float-title h2'))
    await page.mouse.move(t.x + 5, t.y + 5)
    await page.mouse.down()
    await page.mouse.move(t.x + 105, t.y + 85, { steps: 5 })
    await page.mouse.up()
    await expectMaximized(page, win)
    await win.locator('.float-title h2').dblclick()
    expect(await box(win)).toEqual(placed)
  })
}

test('an authority and a request detach from their pages into windows of their own', async ({ page, api }) => {
  const ca = await createCA(api)
  await page.goto(`/cas/${ca.id}`)
  await page.getByTestId('ca-side').getByRole('button', { name: 'Detach into a window' }).click()
  const caWin = page.getByRole('dialog', { name: ca.common_name })
  await expect(caWin.getByRole('heading', { name: ca.common_name, level: 2 }).last()).toBeVisible()
  await expect(caWin.getByTestId('ca-side')).toContainText('Self-signed')

  const cn = `${uid('csr')}.example.com`
  const csr = await api.post('/csrs', { cn, key_type: 'RSA 2048' })
  await page.goto('/csrs')
  await page.getByRole('main').getByRole('row').filter({ hasText: cn }).locator('.entity-name').click()
  await expect(page.locator('#inspector').getByText(cn).first()).toBeVisible()
  await page.locator('#inspector').getByRole('button', { name: 'Detach into a window' }).click()
  // The request leaves the dock for its window, which shows the same sections
  await expect(page.locator('#inspector')).toHaveCount(0)
  const csrWin = page.locator(`[data-detached="csr:${csr.id}"]`)
  await expect(csrWin.getByRole('tab', { name: 'Details' })).toBeVisible()
  await expect(csrWin).toContainText(cn)
  // Both stay open together
  await expect(page.locator('[data-detached]')).toHaveCount(2)
})

test('three certificates compared side by side, then only their differences', async ({ page, api }) => {
  const ca = await createCA(api)
  const tag = uid('cmp')
  const certs = []
  for (const s of ['a', 'b', 'c']) certs.push(await issueCert(api, ca.id, { cn: `${tag}-${s}.example.com` }))
  await page.goto('/certificates')
  await page.getByRole('main').getByRole('searchbox').fill(tag)
  for (const c of certs) {
    await page.getByRole('row', { name: new RegExp(c.common_name.replace(/\./g, '\\.')) }).getByRole('checkbox').check()
  }
  await page.locator('.batchbar').getByRole('button', { name: 'Compare' }).click()
  const win = page.getByRole('dialog', { name: 'Compare 3 certificates' })
  await expect(win).toBeVisible()
  const table = win.locator('table.compare-table')
  await expect(table.locator('thead th')).toHaveText(['Property', ...certs.map((c) => c.common_name)])
  // One issuer for the three: the same line; their subjects differ
  await expect(table.locator('tr[data-row="issuer"]')).not.toHaveClass(/different/)
  await expect(table.locator('tr[data-row="subject"]')).toHaveClass(/different/)
  await expect(table.locator('tr[data-row="key"]')).toBeVisible()
  await win.getByRole('checkbox', { name: 'Show only the differences' }).check()
  await expect(table.locator('tr[data-row="issuer"]')).toHaveCount(0)
  await expect(table.locator('tr[data-row="subject"]')).toBeVisible()
  await expect(table.locator('tbody tr:not(.different)')).toHaveCount(0)
  // The comparison maximizes as the other windows do
  const placed = await box(win)
  await win.getByRole('button', { name: 'Maximize the window' }).click()
  await expectMaximized(page, win)
  await win.getByRole('button', { name: 'Restore the window' }).click()
  expect(await box(win)).toEqual(placed)
})

test('the status bar sums up a pending approval and an entry of the queue, each a way to its page', async ({ page, api }) => {
  void api
  // The shared instance keeps its approvals empty for the other tests: the two reads answer here
  await page.route('**/api/v2/approvals/stats', (route) => route.fulfill({ json: { data: { pending: 1 } } }))
  await page.route('**/api/v2/dashboard/queue*', async (route) => {
    const response = await route.fetch()
    const body = await response.json()
    body.data = {
      ...body.data,
      items: [{ kind: 'approval_pending', tier: 'warning', id: 1, label: 'web', due_at: null, href_hint: '/approvals' }],
      counts: { ...(body.data?.counts || {}), approval_pending: 1, crl_missing: 0, ca_expiring: 0, truststore_expiring: 0, client_renewal_overdue: 0 },
      total: 1,
    }
    return route.fulfill({ response, json: body })
  })
  await page.goto('/certificates')
  const activity = page.locator('footer.statusbar').getByRole('group', { name: 'Activity' })
  await expect(activity.getByRole('link', { name: '1 approval pending' })).toBeVisible()
  await expect(activity.getByRole('link', { name: '1 to act on' })).toBeVisible()
  await expect(activity.getByText('Nothing pending')).toHaveCount(0)
  await activity.getByRole('link', { name: '1 approval pending' }).click()
  await expect(page).toHaveURL((url) => url.pathname === '/approvals')
  await activity.getByRole('link', { name: '1 to act on' }).click()
  await expect(page).toHaveURL((url) => url.pathname === '/')
})

test('no Detach button and no window at phone width', async ({ page, api }) => {
  const cert = await issueCert(api, (await createCA(api)).id)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/certificates')
  await page.getByRole('main').getByRole('searchbox').fill(cert.common_name)
  await page.getByRole('main').getByRole('button', { name: cert.common_name, exact: true }).first().click()
  await expect(page.locator('#inspector').getByRole('heading', { name: cert.common_name })).toBeVisible()
  await expect(page.locator('#inspector').getByRole('button', { name: 'Detach into a window' })).toHaveCount(0)
})
