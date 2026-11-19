import { test, expect, createCA, issueCert } from './support/fixtures'

const EPS = 0.5
type Box = { x: number; y: number; width: number; height: number }
const box = async (locator): Promise<Box> => {
  const b = await locator.boundingBox()
  expect(b).not.toBeNull()
  return b as Box
}

test.use({ viewport: { width: 1600, height: 1000 } })

test('the list shows its seven columns at 1600 px, rows of one height, without a horizontal scroll', async ({ page, api }) => {
  const ca = await createCA(api)
  await issueCert(api, ca.id)
  // A name near the 64 characters a common name may have
  await issueCert(api, ca.id, { cn: `${'long-name-'.repeat(3)}${Date.now()}.example.com` })
  await page.goto('/certificates')
  const table = page.getByRole('main').getByRole('table')
  await expect(table.locator('tbody tr.is-clickable').first()).toBeVisible()

  const measured = await page.evaluate(() => {
    const scroll = document.querySelector('.lv-scroll') as HTMLElement
    const frame = scroll.getBoundingClientRect()
    const heads = [...document.querySelectorAll('.lv-table thead th')]
      .filter((th) => !th.matches('.lv-col-check, .lv-col-actions'))
      .map((th) => {
        // The label is the sort button, or the bare text of a column that does not sort
        const label = th.querySelector('.lv-sort') as HTMLElement | null
        const range = document.createRange()
        range.selectNodeContents(label || [...th.childNodes].find((n) => n.nodeType === Node.TEXT_NODE) || th)
        const outer = th.getBoundingClientRect()
        const inner = range.getBoundingClientRect()
        return {
          text: (th.textContent || '').trim(),
          inside: outer.left >= frame.left - 0.5 && outer.right <= frame.right + 0.5,
          whole: inner.left >= outer.left - 0.5 && inner.right <= outer.right + 0.5,
        }
      })
    const rows = [...document.querySelectorAll('.lv-table tbody tr.is-clickable')].map((tr) => tr.getBoundingClientRect().height)
    // A cell may shorten its text with an ellipsis, in the name and the capped columns only
    const cut = [...document.querySelectorAll('.lv-table tbody td')]
      .filter((td) => !td.matches('.lv-grow, .lv-capped'))
      .filter((td) => [td, ...td.querySelectorAll('*')].some((el) => el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).overflowX !== 'visible'))
      .length
    return { heads, rows, cut, overflow: scroll.scrollWidth - scroll.clientWidth }
  })
  expect(measured.heads).toHaveLength(7)
  for (const head of measured.heads) {
    expect(head.text).not.toBe('')
    expect(head, head.text).toMatchObject({ inside: true, whole: true })
  }
  expect(measured.overflow).toBeLessThanOrEqual(0)
  expect(measured.cut).toBe(0)
  expect(new Set(measured.rows).size).toBe(1)
  expect(measured.rows[0]).toBe(36)
})

test('the inspector stands in the flow of the page, at its margins, over the status bar', async ({ page, api }) => {
  const cert = await issueCert(api, (await createCA(api)).id)
  await page.goto('/certificates')
  const main = page.getByRole('main')
  await main.getByRole('button', { name: cert.common_name, exact: true }).click()
  const dock = page.getByTestId('inspector-dock')
  await expect(dock).toBeVisible()
  // The position is a preference of the account: this check reads the bottom dock
  const toBottom = dock.getByRole('button', { name: 'Dock at the bottom' })
  if (await toBottom.count()) await toBottom.click()
  await expect(dock).toHaveClass(/is-bottom/)

  const view = page.viewportSize()!
  const d = await box(dock)
  const bar = await box(page.getByRole('contentinfo'))
  const list = await box(page.locator('.lv-table-box'))
  const scroll = await box(page.locator('.lv-scroll'))
  // In the flow: a child of the area it shares with the page, not laid over it
  expect(await dock.evaluate((el) => getComputedStyle(el).position)).not.toBe('fixed')
  expect(await dock.evaluate((el) => el.parentElement!.contains(document.querySelector('main')))).toBe(true)
  // At the margins of the page: the edges of the list
  expect(Math.abs(d.x - list.x)).toBeLessThanOrEqual(EPS)
  expect(Math.abs(d.x + d.width - (list.x + list.width))).toBeLessThanOrEqual(EPS)
  expect(d.x).toBeGreaterThan(0)
  // The list shrinks over it and keeps its own scroll; the status bar keeps the bottom
  expect(list.y + list.height).toBeLessThanOrEqual(d.y + EPS)
  expect(scroll.height).toBeGreaterThan(36)
  expect(Math.abs(d.y + d.height - bar.y)).toBeLessThanOrEqual(EPS)
  expect(Math.abs(bar.y + bar.height - view.height)).toBeLessThanOrEqual(EPS)

  // The opened row is marked, and the Overview stands in three columns
  await expect(main.getByRole('row', { name: new RegExp(cert.common_name.replace(/\./g, '\\.')) })).toHaveAttribute('aria-current', 'true')
  const columns = await dock.getByTestId('cert-overview').locator(':scope > section').evaluateAll(
    (sections) => sections.map((s) => Math.round(s.getBoundingClientRect().top)))
  expect(columns).toHaveLength(3)
  expect(new Set(columns).size).toBe(1)

  // Folded, it keeps its strip of tabs over the status bar
  await dock.getByRole('button', { name: 'Fold the inspector' }).click()
  const folded = await box(dock)
  expect(folded.height).toBeLessThan(40)
  expect(Math.abs(folded.y + folded.height - bar.y)).toBeLessThanOrEqual(EPS)
  await expect(dock.getByRole('tab', { name: cert.common_name })).toBeVisible()
  await dock.getByRole('button', { name: 'Unfold the inspector' }).click()
  await dock.getByRole('button', { name: 'Close inspector' }).click().catch(() => {})
})
