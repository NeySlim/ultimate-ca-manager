import { test, expect, createCA, ADMIN_USER, ADMIN_PASSWORD, Api } from './support/fixtures'
import { readFileSync } from 'node:fs'

// A restore replaces the whole database: the configuration runs this file alone, after the others
test('a backup created on screen is restored on screen and the report says what came back', async ({ page, api, request }) => {
  const kept = await createCA(api)
  const password = 'Backup-pass-12345'

  await page.goto('/settings?tab=backup')
  await page.getByRole('button', { name: 'Create Backup' }).click()
  const create = page.getByRole('dialog', { name: 'Create Encrypted Backup' })
  await create.getByLabel('Encryption Password').fill(password)
  const download = page.waitForEvent('download')
  await create.getByRole('button', { name: 'Create and Download' }).click()
  const archive = await (await download).path()
  await expect(create).toBeHidden()

  // Made after the backup: the restore removes it
  const later = await createCA(api)

  await page.locator('input[type="file"]').last().setInputFiles({
    name: 'e2e.ucmbkp', mimeType: 'application/octet-stream', buffer: readFileSync(archive),
  })
  const restore = page.getByRole('dialog', { name: 'Restore from Backup' })
  await restore.getByLabel('Backup Password').fill(password)
  await restore.getByRole('button', { name: 'Restore Backup' }).click()

  const report = page.getByRole('dialog', { name: 'Restore report' })
  await expect(report.getByText(/Backup restored successfully: \d+ users, \d+ CAs, \d+ certificates/)).toBeVisible()

  const fresh = await Api.login(request, ADMIN_USER, ADMIN_PASSWORD)
  const names = JSON.stringify(await fresh.get('/cas?per_page=500'))
  expect(names).toContain(kept.common_name)
  expect(names).not.toContain(later.common_name)
})
