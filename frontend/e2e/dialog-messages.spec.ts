import { test, expect, createCA, uid } from './support/fixtures'
import type { Locator, Page } from '@playwright/test'

// The element the browser hits at the centre of `target`: inside it, the target is on top and not inert
async function hitInside(page: Page, target: Locator) {
  const box = await target.boundingBox()
  expect(box).toBeTruthy()
  return page.evaluate(([x, y, id]) => {
    const hit = document.elementFromPoint(x, y)
    return !!hit && !!hit.closest(`#${id}`)
  }, [box!.x + box!.width / 2, box!.y + box!.height / 2, await target.getAttribute('id')] as const)
}

test('the error of a form dialog shows in the dialog, above its buttons (#456)', async ({ page, api }) => {
  void api // signs the page in
  await page.route('**/api/v2/templates', (route) => route.request().method() === 'POST'
    ? route.fulfill({ status: 409, contentType: 'application/problem+json',
      body: JSON.stringify({ status: 409, detail: 'E2E: a template of this name exists', message: 'E2E: a template of this name exists' }) })
    : route.fallback())
  await page.goto('/templates')
  await page.getByRole('main').getByRole('button', { name: 'Create Template', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: 'Create Template' })
  await dialog.getByLabel('Template Name').fill(uid('tpl'))
  await dialog.getByRole('button', { name: 'Create', exact: true }).click()

  const alert = dialog.getByRole('alert')
  await expect(alert).toHaveText(/E2E: a template of this name exists/)
  await expect(dialog.locator('.modal-actions').last().getByRole('alert')).toBeVisible()
  await expect(page.locator('#toast')).not.toHaveClass(/visible/)
  // Readable where it is: nothing covers it
  await alert.evaluate((el) => { el.id = 'e2e-dialog-alert' })
  expect(await hitInside(page, alert)).toBe(true)
  // Its close button at the right edge of the message, however short the text
  const [bar, cross] = await Promise.all([alert.boundingBox(), alert.getByRole('button', { name: 'Close the message' }).boundingBox()])
  expect(bar!.x + bar!.width - (cross!.x + cross!.width)).toBeLessThanOrEqual(12)
  await alert.getByRole('button', { name: 'Close the message' }).click()
  await expect(alert).toHaveCount(0)
  await expect(dialog).toBeVisible()
})

test('a toast raised before a dialog opens stays above it and its button answers (#456)', async ({ page, api }) => {
  const ca = await createCA(api)
  let publishes = 0
  await page.route(`**/api/v2/crl/${ca.id}/regenerate`, (route) => {
    publishes += 1
    return route.fulfill({ status: 500, contentType: 'application/problem+json',
      body: JSON.stringify({ status: 500, detail: 'E2E: publication failed', message: 'E2E: publication failed' }) })
  })
  // The queue shows six rows: this CA's row comes first, ahead of other tests' CAs on the shared instance
  await page.route('**/api/v2/dashboard/queue**', async (route) => {
    const response = await route.fetch()
    const body = await response.json()
    const items = body?.data?.items
    if (Array.isArray(items)) body.data.items = [...items.filter((i) => i.label === ca.common_name), ...items.filter((i) => i.label !== ca.common_name)]
    return route.fulfill({ response, json: body })
  })
  await page.goto('/')
  const queue = page.getByRole('region', { name: 'To handle' })
  await expect(queue.locator('.sk-body')).toHaveCount(0)
  await queue.getByRole('button', { name: `Publish now ${ca.common_name}`, exact: true }).first().click()
  const toast = page.locator('#toast')
  await expect(toast).toHaveText(/E2E: publication failed/)
  await expect.poll(() => publishes).toBe(1)

  await page.getByRole('button', { name: 'Help', exact: true }).first().click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible()
  // Drawn in the dialog, in the top layer above it
  await expect(dialog.locator('#toast')).toHaveCount(1)
  expect(await toast.evaluate((el) => el.matches(':popover-open'))).toBe(true)
  const retry = toast.locator('#toast-retry')
  expect(await hitInside(page, retry)).toBe(true)
  await retry.click()
  await expect.poll(() => publishes).toBe(2)
  await expect(dialog).toBeVisible()
  // Closed by its own button, the dialog stays
  await expect(toast).toHaveText(/E2E: publication failed/)
  const close = toast.locator('#toast-close')
  expect(await hitInside(page, close)).toBe(true)
  await close.click()
  await expect(toast).not.toHaveClass(/visible/)
  await expect(dialog).toBeVisible()
})
