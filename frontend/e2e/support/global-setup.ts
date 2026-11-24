import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { request, type FullConfig } from '@playwright/test'
import { Api, ADMIN_USER, ADMIN_PASSWORD, SEED_DIR_ENV, dismissSupportCard } from './api'

// Once per run on the instance scripts/ci/e2e.sh started: the administrator's support card is
// acknowledged, so it covers no button, and the protocol URL the CA extensions need is set.
// Any other instance (lab) is left exactly as it is.
export default async function globalSetup(config: FullConfig) {
  const { baseURL } = config.projects[0].use
  if (!baseURL) throw new Error('UCM_E2E_BASE_URL is not set: run the suite with scripts/ci/e2e.sh')
  // One directory per run: a seed made once is never read by another run (seedOnce)
  process.env[SEED_DIR_ENV] = mkdtempSync(join(tmpdir(), 'ucm-e2e-seed-'))
  if (process.env.UCM_E2E_MANAGED !== '1' || process.env.UCM_LAB === '1') return
  const context = await request.newContext({ baseURL, ignoreHTTPSErrors: true })
  const api = await Api.login(context, ADMIN_USER, ADMIN_PASSWORD)
  await dismissSupportCard(api)
  // CDP and OCSP URLs are built on it; the instance serves no plain-HTTP port
  await api.patch('/settings/general', { protocol_base_url: 'http://ucm-e2e.test' })
  await context.dispose()
}

