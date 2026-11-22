import { test, expect, createCA, issueCert, uid } from './support/fixtures'

// The columns of a list beside the dock at the right (DataTable, adjust.css): no cell's text runs under its
// neighbour; free text short of room ends in an ellipsis with its whole text in a title; the expiry column
// keeps its content's width, the time left beside its date. jsdom has no layout: this is the real geometry.

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

// Every cell of the list: its text inside its own box once clipped, a clipped box ending in an ellipsis with a title
const cells = (page) => page.evaluate(() => {
  const out: string[] = []
  for (const td of document.querySelectorAll('.atl .page-content tbody td')) {
    const box = td.getBoundingClientRect()
    const walker = document.createTreeWalker(td, NodeFilter.SHOW_TEXT)
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      if (!n.textContent!.trim()) continue
      let right = Infinity
      for (let el = n.parentElement; el && el !== td.parentElement; el = el.parentElement) {
        if (getComputedStyle(el).overflowX !== 'visible') right = Math.min(right, el.getBoundingClientRect().right)
      }
      const range = document.createRange()
      range.selectNodeContents(n)
      if (Math.min(range.getBoundingClientRect().right, right) > box.right + 1) out.push(`spill: ${n.textContent}`)
    }
    for (const el of [td, ...td.querySelectorAll('*')] as HTMLElement[]) {
      const cs = getComputedStyle(el)
      if (cs.overflowX === 'visible' || el.scrollWidth <= el.clientWidth + 1 || el.matches('svg, svg *')) continue
      if (cs.textOverflow !== 'ellipsis' || /flex|grid/.test(cs.display)) out.push(`cut: ${el.textContent}`)
      else if (!(el.title || td.title).includes(el.textContent!.trim())) out.push(`no title: ${el.textContent}`)
    }
  }
  return out
})

test.describe('beside the dock at the right', () => {
  test.use({ viewport: { width: 1406, height: 809 } })

  test('an issuer narrowed by hand ends in an ellipsis, and the time left stays beside its date', async ({ page, api }) => {
    const issuer = `Production Intermediate Authority ${uid('ca')}`
    const cert = await issueCert(api, (await createCA(api, { commonName: issuer })).id)
    await dockRight(page)
    // The description hidden by the Colonnes dialog, the issuer set to 160 px by its grip
    await page.addInitScript(() => {
      localStorage.setItem('ucm-certs-table-columns', JSON.stringify({ hidden: ['description', 'grade', 'pair', 'created'] }))
      localStorage.setItem('ucm-certs-table-widths', JSON.stringify({ ca: 160 }))
    })
    await page.goto('/certificates')
    await page.getByRole('main').getByRole('searchbox').fill(cert.common_name)
    await page.getByRole('main').getByRole('button', { name: cert.common_name, exact: true }).click()
    await expect(page.locator('.atl #app')).toHaveClass(/dock-right/)
    // Other tests issue certificates at the same time: the list holds this one only
    await expect(page.locator('.atl .page-content tbody tr')).toHaveCount(1)

    const ca = page.locator('.atl .page-content tbody td').filter({ hasText: issuer.slice(0, 20) })
    await expect(ca).toHaveAttribute('title', issuer)
    expect(await ca.evaluate((el) => el.scrollWidth > el.clientWidth && getComputedStyle(el).textOverflow === 'ellipsis')).toBe(true)
    await expect.poll(() => cells(page)).toEqual([])
    // The expiry column is as wide as its cell: the date, the mockup's 8 px beside the dock, the time left
    const gap = await page.locator('.atl .page-content tbody .expiry-cell').first().evaluate((cell) => {
      const left = cell.querySelector('.remaining')!
      const range = document.createRange()
      range.setStart(cell, 0)
      range.setEndBefore(left)
      return left.getBoundingClientRect().left - range.getBoundingClientRect().right
    })
    expect(gap).toBeLessThanOrEqual(9)
  })
})

test.describe('at 1200 px beside the dock at the right', () => {
  test.use({ viewport: { width: 1200, height: 900 } })

  test('a long name and a long issuer give way by an ellipsis: nothing overlaps, nothing scrolls', async ({ page, api }) => {
    const issuer = `Regional Issuing Authority for the West ${uid('ca')}`
    const cert = await issueCert(api, (await createCA(api, { commonName: issuer })).id, { cn: `${uid('long-service-name')}.internal.example.com` })
    await dockRight(page)
    await page.goto('/certificates')
    await page.getByRole('main').getByRole('searchbox').fill(cert.common_name)
    await page.getByRole('main').getByRole('button', { name: cert.common_name, exact: true }).click()
    await expect(page.locator('.atl #app')).toHaveClass(/dock-right/)
    // Other tests issue certificates at the same time: the list holds this one only
    await expect(page.locator('.atl .page-content tbody tr')).toHaveCount(1)

    const region = page.getByRole('main').locator('#cert-scroll')
    await expect.poll(() => region.evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(1)
    await expect.poll(() => cells(page)).toEqual([])
    await expect(page.locator('.atl .page-content tbody .entity-label').first()).toHaveAttribute('title', cert.common_name)
  })
})
