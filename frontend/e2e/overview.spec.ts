import { test, expect, createCA } from './support/fixtures'

const CARDS = ['To handle', 'Automation health', 'Hierarchy', 'Expiry horizon', 'Compliance', 'Latest operations']

test('the overview cards load their data', async ({ page, api }) => {
  const ca = await createCA(api)
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1, name: 'Overview' })).toBeVisible()
  for (const name of CARDS) {
    const card = page.getByRole('region', { name })
    await expect(card.getByRole('heading', { name })).toBeVisible()
    await expect(card.getByRole('status')).toHaveCount(0)
  }
  // The activity card reports what the test just did
  await expect(page.getByRole('region', { name: 'Latest operations' }).getByText(ca.common_name).first()).toBeVisible()
})

test('a queue entry opens the object it names', async ({ page, api }) => {
  // A CA that expires within a year is an item to handle
  const ca = await createCA(api, { validityDays: 100 })
  await page.goto('/')
  const queue = page.getByRole('region', { name: 'To handle' })
  // Six entries are shown folded, critical ones first: unfold to list them all
  await queue.getByRole('button', { name: 'Show the totals per kind' }).click()
  const entry = queue.getByRole('link', { name: new RegExp(`^${ca.common_name} CA expiring`) })
  await expect(entry).toBeVisible()
  await entry.click()

  await expect(page).toHaveURL(url => url.pathname === '/cas' || url.pathname === `/cas/${ca.id}`)
  // The link names the CA's own page, not another one's
  await expect(page.getByRole('tabpanel', { name: ca.common_name }).getByRole('heading', { name: ca.common_name })).toBeVisible()
})
