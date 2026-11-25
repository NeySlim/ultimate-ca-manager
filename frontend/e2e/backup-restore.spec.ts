import { test, expect, createCA, ADMIN_USER, ADMIN_PASSWORD, Api } from './support/fixtures'
import { readFileSync } from 'node:fs'
import { RESTORE_ANSWER_MS, TEST_TIMEOUT_MS } from './support/timeouts'

// A restore replaces the whole database: the configuration runs this file alone, after the others,
// one test at a time (two restores at once: the second answers 409)
test('a backup created on screen is restored on screen and the report says what came back', async ({ page, api, request }) => {
  test.setTimeout(TEST_TIMEOUT_MS + RESTORE_ANSWER_MS)
  const kept = await createCA(api)
  const password = 'Backup-pass-12345'

  await page.goto('/settings?tab=backup')
  await page.locator('#set-sec-backup').getByRole('button', { name: 'Create Backup' }).click()
  const create = page.getByRole('dialog', { name: 'Create Encrypted Backup' })
  await create.getByLabel('Encryption Password').fill(password)
  const download = page.waitForEvent('download')
  await create.getByRole('button', { name: 'Create and Download' }).click()
  const archive = await (await download).path()
  await expect(create).toBeHidden()

  // Made after the backup: the restore removes it
  const later = await createCA(api)

  await page.locator('#set-sec-backup input[type="file"]').last().setInputFiles({
    name: 'e2e.ucmbkp', mimeType: 'application/octet-stream', buffer: readFileSync(archive),
  })
  const restore = page.getByRole('dialog', { name: 'Restore from Backup' })
  await restore.getByLabel('Backup Password').fill(password)
  await restore.getByRole('button', { name: 'Restore Backup' }).click()

  // Answered within the server's bounded wait, not the default 15 s: a slow runner needs more
  const report = page.getByRole('dialog', { name: 'Restore report' })
  await expect(report.getByText(/Backup restored successfully: \d+ users, \d+ CAs, \d+ certificates/))
    .toBeVisible({ timeout: RESTORE_ANSWER_MS })

  const fresh = await Api.login(request, ADMIN_USER, ADMIN_PASSWORD)
  const names = JSON.stringify(await fresh.get('/cas?per_page=500'))
  expect(names).toContain(kept.common_name)
  expect(names).not.toContain(later.common_name)
})

// Past the bounded wait (forced here by Prefer: respond-async) the restore is a job: the dialog
// follows it, its own sign-out is a request to sign in again, and the report follows the sign-in
test('a restore that runs as a job signs the page out and shows its report after the sign-in', async ({ page, api, request }) => {
  const kept = await createCA(api)
  const password = 'Backup-pass-67890'
  const made = await api.post('/system/backup', { password })
  const blob = await (await page.request.get(`/api/v2/system/backup/${made.filename}/download`)).body()
  const later = await createCA(api)

  await page.route('**/api/v2/system/restore', route =>
    route.continue({ headers: { ...route.request().headers(), prefer: 'respond-async' } }))
  await page.goto('/settings?tab=backup')
  await page.locator('#set-sec-backup input[type="file"]').last().setInputFiles({
    name: 'e2e-job.ucmbkp', mimeType: 'application/octet-stream', buffer: blob,
  })
  const restore = page.getByRole('dialog', { name: 'Restore from Backup' })
  await restore.getByLabel('Backup Password').fill(password)
  await restore.getByRole('button', { name: 'Restore Backup' }).click()

  await expect(restore.getByText(/The restore has probably committed/)).toBeVisible({ timeout: 120_000 })
  await restore.getByRole('button', { name: 'Sign in again' }).click()
  await page.getByLabel('Username', { exact: true }).fill(ADMIN_USER)
  await page.getByLabel('Password', { exact: true }).fill(ADMIN_PASSWORD)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()

  const report = page.getByRole('dialog', { name: 'Restore report' })
  await expect(report.getByText(/Backup restored successfully/)).toBeVisible({ timeout: 60_000 })
  const fresh = await Api.login(request, ADMIN_USER, ADMIN_PASSWORD)
  const names = JSON.stringify(await fresh.get('/cas?per_page=500'))
  expect(names).toContain(kept.common_name)
  expect(names).not.toContain(later.common_name)
})
