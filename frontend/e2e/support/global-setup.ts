import { request, type FullConfig } from '@playwright/test'
import { Api, ADMIN_USER, ADMIN_PASSWORD, dismissSupportCard } from './api'

// Once per run: the administrator's support card is acknowledged, so it covers no button,
// and the protocol URL the CA extensions need is set
export default async function globalSetup(config: FullConfig) {
  const { baseURL } = config.projects[0].use
  if (!baseURL) throw new Error('UCM_E2E_BASE_URL is not set: run the suite with scripts/ci/e2e.sh')
  const context = await request.newContext({ baseURL, ignoreHTTPSErrors: true })
  const api = await Api.login(context, ADMIN_USER, ADMIN_PASSWORD)
  await dismissSupportCard(api)
  // CDP and OCSP URLs are built on it; the instance serves no plain-HTTP port
  await api.patch('/settings/general', { protocol_base_url: 'http://ucm-e2e.test' })
  await context.dispose()
}

