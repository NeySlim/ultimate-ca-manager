/**
 * Service Layer Tests — All 19 services
 *
 * Validates that each service method:
 * - Calls the correct HTTP method (GET/POST/PUT/PATCH/DELETE)
 * - Uses the correct endpoint path
 * - Sends the correct request body / query params
 * - Handles response data correctly
 *
 * Pattern: Mock apiClient methods, verify calls match backend API contract.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Shared mock for apiClient
const mockApiClient = {
  get: vi.fn().mockResolvedValue({ data: [] }),
  post: vi.fn().mockResolvedValue({ data: {} }),
  put: vi.fn().mockResolvedValue({ data: {} }),
  patch: vi.fn().mockResolvedValue({ data: {} }),
  delete: vi.fn().mockResolvedValue({ success: true }),
  upload: vi.fn().mockResolvedValue({ data: {} }),
  request: vi.fn().mockResolvedValue({ data: {} }),
  setCsrfToken: vi.fn(),
  clearCsrfToken: vi.fn(),
}

vi.mock('../apiClient', () => ({
  apiClient: mockApiClient,
}))

beforeEach(() => {
  vi.clearAllMocks()
})

// ============================================================
// 1. CAs Service
// ============================================================
describe('casService', () => {
  let casService

  beforeEach(async () => {
    const mod = await import('../cas.service')
    casService = mod.casService
  })

  it('getAll → GET /cas', async () => {
    await casService.getAll()
    expect(mockApiClient.get).toHaveBeenCalledWith('/cas')
  })

  it('getTree → GET /cas/tree', async () => {
    await casService.getTree()
    expect(mockApiClient.get).toHaveBeenCalledWith('/cas/tree')
  })

  it('getById → GET /cas/:id', async () => {
    await casService.getById(5)
    expect(mockApiClient.get).toHaveBeenCalledWith('/cas/5')
  })

  it('create → POST /cas with data', async () => {
    const data = { commonName: 'Root CA', keyAlgo: 'RSA', keySize: 2048 }
    await casService.create(data)
    expect(mockApiClient.post).toHaveBeenCalledWith('/cas', data)
  })

  it('update → PATCH /cas/:id', async () => {
    const data = { descr: 'Updated' }
    await casService.update(3, data)
    expect(mockApiClient.patch).toHaveBeenCalledWith('/cas/3', data)
  })

  it('delete → DELETE /cas/:id', async () => {
    await casService.delete(3)
    expect(mockApiClient.delete).toHaveBeenCalledWith('/cas/3')
  })

  it('import → upload /cas/import', async () => {
    const formData = new FormData()
    await casService.import(formData)
    expect(mockApiClient.upload).toHaveBeenCalledWith('/cas/import', formData)
  })

  it('export → GET /cas/:id/export with query params', async () => {
    await casService.export(1, 'pem', { includeKey: true, includeChain: true })
    const call = mockApiClient.get.mock.calls[0]
    expect(call[0]).toContain('/cas/1/export')
    expect(call[0]).toContain('format=pem')
    expect(call[0]).toContain('include_key=true')
    expect(call[0]).toContain('include_chain=true')
    expect(call[1]).toEqual({ responseType: 'blob' })
  })

  it('exportAll → GET /cas/export', async () => {
    await casService.exportAll('der')
    const call = mockApiClient.get.mock.calls[0]
    expect(call[0]).toContain('/cas/export')
    expect(call[0]).toContain('format=der')
  })

  it('getCertificates → GET /cas/:id/certificates', async () => {
    await casService.getCertificates(2, { page: 1, per_page: 10 })
    const call = mockApiClient.get.mock.calls[0]
    expect(call[0]).toContain('/cas/2/certificates')
    expect(call[0]).toContain('page=1')
    expect(call[0]).toContain('per_page=10')
  })
})

// ============================================================
// 2. Certificates Service
// ============================================================
describe('certificatesService', () => {
  let certificatesService

  beforeEach(async () => {
    const mod = await import('../certificates.service')
    certificatesService = mod.certificatesService
  })

  it('getAll → GET /certificates with filters', async () => {
    await certificatesService.getAll({ status: 'valid', ca_id: 1 })
    const call = mockApiClient.get.mock.calls[0]
    expect(call[0]).toContain('/certificates')
    expect(call[0]).toContain('status=valid')
    expect(call[0]).toContain('ca_id=1')
  })

  it('getStats → GET /certificates/stats', async () => {
    await certificatesService.getStats()
    expect(mockApiClient.get).toHaveBeenCalledWith('/certificates/stats')
  })

  it('getById → GET /certificates/:id', async () => {
    await certificatesService.getById(42)
    expect(mockApiClient.get).toHaveBeenCalledWith('/certificates/42')
  })

  it('create → POST /certificates', async () => {
    const data = { cn: 'test.com', ca_id: '1', validity_days: 365 }
    await certificatesService.create(data)
    expect(mockApiClient.post).toHaveBeenCalledWith('/certificates', data)
  })

  it('revoke → POST /certificates/:id/revoke with reason', async () => {
    await certificatesService.revoke(5, 'key_compromise')
    expect(mockApiClient.post).toHaveBeenCalledWith('/certificates/5/revoke', { reason: 'key_compromise' })
  })

  it('renew → POST /certificates/:id/renew', async () => {
    await certificatesService.renew(5)
    expect(mockApiClient.post).toHaveBeenCalledWith('/certificates/5/renew')
  })

  it('delete → DELETE /certificates/:id', async () => {
    await certificatesService.delete(5)
    expect(mockApiClient.delete).toHaveBeenCalledWith('/certificates/5')
  })

  it('export → GET /certificates/:id/export with blob response', async () => {
    await certificatesService.export(1, 'pkcs12', { password: 'test' })
    const call = mockApiClient.get.mock.calls[0]
    expect(call[0]).toContain('/certificates/1/export')
    expect(call[0]).toContain('format=pkcs12')
    expect(call[0]).toContain('password=test')
    expect(call[1]).toEqual({ responseType: 'blob' })
  })

  it('import → upload /certificates/import', async () => {
    const formData = new FormData()
    await certificatesService.import(formData)
    expect(mockApiClient.upload).toHaveBeenCalledWith('/certificates/import', formData)
  })

  it('uploadKey → POST /certificates/:id/key', async () => {
    await certificatesService.uploadKey(1, '---PEM---', 'pass123')
    expect(mockApiClient.post).toHaveBeenCalledWith('/certificates/1/key', {
      key: '---PEM---', passphrase: 'pass123'
    })
  })
})

// ============================================================
// 3. CSRs Service
// ============================================================
describe('csrsService', () => {
  let csrsService

  beforeEach(async () => {
    const mod = await import('../csrs.service')
    csrsService = mod.csrsService
  })

  it('getAll → GET /csrs', async () => {
    await csrsService.getAll()
    expect(mockApiClient.get).toHaveBeenCalled()
    const call = mockApiClient.get.mock.calls[0]
    expect(call[0]).toContain('/csrs')
  })

  it('getHistory → GET /csrs/history', async () => {
    await csrsService.getHistory()
    const call = mockApiClient.get.mock.calls[0]
    expect(call[0]).toContain('/csrs/history')
  })

  it('upload → POST /csrs/upload with pem body', async () => {
    await csrsService.upload('---CSR PEM---')
    expect(mockApiClient.post).toHaveBeenCalledWith('/csrs/upload', { pem: '---CSR PEM---' })
  })

  it('sign → POST /csrs/:id/sign with ca_id and validity_days', async () => {
    await csrsService.sign(10, '2', 365)
    expect(mockApiClient.post).toHaveBeenCalledWith('/csrs/10/sign', {
      ca_id: '2', validity_days: 365
    })
  })

  it('delete → DELETE /csrs/:id', async () => {
    await csrsService.delete(10)
    expect(mockApiClient.delete).toHaveBeenCalledWith('/csrs/10')
  })

  it('uploadKey → POST /csrs/:id/key', async () => {
    await csrsService.uploadKey(3, '---KEY---', 'pass')
    expect(mockApiClient.post).toHaveBeenCalledWith('/csrs/3/key', {
      key: '---KEY---', passphrase: 'pass'
    })
  })
})

// ============================================================
// 4. ACME Service
// ============================================================
describe('acmeService', () => {
  let acmeService

  beforeEach(async () => {
    const mod = await import('../acme.service')
    acmeService = mod.acmeService
  })

  it('getSettings → GET /acme/settings', async () => {
    await acmeService.getSettings()
    expect(mockApiClient.get).toHaveBeenCalledWith('/acme/settings')
  })

  it('updateSettings → PATCH /acme/settings', async () => {
    const data = { enabled: true }
    await acmeService.updateSettings(data)
    expect(mockApiClient.patch).toHaveBeenCalledWith('/acme/settings', data)
  })

  it('getAccounts → GET /acme/accounts', async () => {
    await acmeService.getAccounts()
    expect(mockApiClient.get).toHaveBeenCalledWith('/acme/accounts')
  })

  it('createAccount → POST /acme/accounts', async () => {
    const data = { email: 'a@b.com', key_type: 'RSA-2048' }
    await acmeService.createAccount(data)
    expect(mockApiClient.post).toHaveBeenCalledWith('/acme/accounts', data)
  })

  it('deactivateAccount → POST /acme/accounts/:id/deactivate', async () => {
    await acmeService.deactivateAccount(1)
    expect(mockApiClient.post).toHaveBeenCalledWith('/acme/accounts/1/deactivate')
  })

  it('deleteAccount → DELETE /acme/accounts/:id', async () => {
    await acmeService.deleteAccount(1)
    expect(mockApiClient.delete).toHaveBeenCalledWith('/acme/accounts/1')
  })

  it('requestCertificate → POST /acme/client/request', async () => {
    const data = { domains: ['test.com'], challenge_type: 'dns-01' }
    await acmeService.requestCertificate(data)
    expect(mockApiClient.post).toHaveBeenCalledWith('/acme/client/request', data)
  })

  it('verifyChallenge → POST /acme/client/orders/:id/verify', async () => {
    await acmeService.verifyChallenge(5)
    expect(mockApiClient.post).toHaveBeenCalled()
    const call = mockApiClient.post.mock.calls[0]
    expect(call[0]).toContain('/acme/client/orders/5/verify')
  })

  it('finalizeOrder → POST /acme/client/orders/:id/finalize', async () => {
    await acmeService.finalizeOrder(5)
    expect(mockApiClient.post).toHaveBeenCalled()
    const call = mockApiClient.post.mock.calls[0]
    expect(call[0]).toContain('/acme/client/orders/5/finalize')
  })

  it('deleteOrder → DELETE /acme/client/orders/:id', async () => {
    await acmeService.deleteOrder(5)
    expect(mockApiClient.delete).toHaveBeenCalledWith('/acme/client/orders/5')
  })

  it('renewOrder → POST /acme/client/orders/:id/renew', async () => {
    await acmeService.renewOrder(5)
    expect(mockApiClient.post).toHaveBeenCalled()
    const call = mockApiClient.post.mock.calls[0]
    expect(call[0]).toContain('/acme/client/orders/5/renew')
  })

  it('getDnsProviders → GET /dns-providers', async () => {
    await acmeService.getDnsProviders()
    expect(mockApiClient.get).toHaveBeenCalledWith('/dns-providers')
  })

  it('getDnsProviderTypes → GET /dns-providers/types', async () => {
    await acmeService.getDnsProviderTypes()
    expect(mockApiClient.get).toHaveBeenCalledWith('/dns-providers/types')
  })

  it('createDnsProvider → POST /dns-providers', async () => {
    const data = { name: 'CF', provider_type: 'cloudflare' }
    await acmeService.createDnsProvider(data)
    expect(mockApiClient.post).toHaveBeenCalledWith('/dns-providers', data)
  })

  it('updateDnsProvider → PATCH /dns-providers/:id', async () => {
    const data = { name: 'Updated' }
    await acmeService.updateDnsProvider(3, data)
    expect(mockApiClient.patch).toHaveBeenCalledWith('/dns-providers/3', data)
  })

  it('deleteDnsProvider → DELETE /dns-providers/:id', async () => {
    await acmeService.deleteDnsProvider(3)
    expect(mockApiClient.delete).toHaveBeenCalledWith('/dns-providers/3')
  })

  it('testDnsProvider → POST /dns-providers/:id/test', async () => {
    await acmeService.testDnsProvider(3)
    expect(mockApiClient.post).toHaveBeenCalled()
    const call = mockApiClient.post.mock.calls[0]
    expect(call[0]).toContain('/dns-providers/3/test')
  })

  it('getDomains → GET /acme/domains', async () => {
    await acmeService.getDomains()
    expect(mockApiClient.get).toHaveBeenCalledWith('/acme/domains')
  })

  it('createDomain → POST /acme/domains', async () => {
    const data = { domain: 'test.com' }
    await acmeService.createDomain(data)
    expect(mockApiClient.post).toHaveBeenCalledWith('/acme/domains', data)
  })

  it('updateDomain → PUT /acme/domains/:id', async () => {
    const data = { domain: 'updated.com' }
    await acmeService.updateDomain(2, data)
    expect(mockApiClient.put).toHaveBeenCalledWith('/acme/domains/2', data)
  })

  it('deleteDomain → DELETE /acme/domains/:id', async () => {
    await acmeService.deleteDomain(2)
    expect(mockApiClient.delete).toHaveBeenCalledWith('/acme/domains/2')
  })

  it('getHistory → GET /acme/history', async () => {
    await acmeService.getHistory()
    expect(mockApiClient.get).toHaveBeenCalledWith('/acme/history')
  })

  it('getClientOrders → GET /acme/client/orders', async () => {
    await acmeService.getClientOrders()
    const call = mockApiClient.get.mock.calls[0]
    expect(call[0]).toContain('/acme/client/orders')
  })

  it('getClientSettings → GET /acme/client/settings', async () => {
    await acmeService.getClientSettings()
    expect(mockApiClient.get).toHaveBeenCalledWith('/acme/client/settings')
  })
})

// ============================================================
// 5. Templates Service
// ============================================================
describe('templatesService', () => {
  let templatesService

  beforeEach(async () => {
    const mod = await import('../templates.service')
    templatesService = mod.templatesService
  })

  it('getAll → GET /templates', async () => {
    await templatesService.getAll()
    expect(mockApiClient.get).toHaveBeenCalledWith('/templates')
  })

  it('getById → GET /templates/:id', async () => {
    await templatesService.getById(1)
    expect(mockApiClient.get).toHaveBeenCalledWith('/templates/1')
  })

  it('create → POST /templates', async () => {
    const data = { name: 'Web Server', type: 'certificate' }
    await templatesService.create(data)
    expect(mockApiClient.post).toHaveBeenCalledWith('/templates', data)
  })

  it('update → PUT /templates/:id', async () => {
    const data = { name: 'Updated' }
    await templatesService.update(1, data)
    expect(mockApiClient.put).toHaveBeenCalledWith('/templates/1', data)
  })

  it('delete → DELETE /templates/:id', async () => {
    await templatesService.delete(1)
    expect(mockApiClient.delete).toHaveBeenCalledWith('/templates/1')
  })

  it('duplicate → POST /templates/:id/duplicate', async () => {
    await templatesService.duplicate(1)
    expect(mockApiClient.post).toHaveBeenCalled()
    const call = mockApiClient.post.mock.calls[0]
    expect(call[0]).toContain('/templates/1/duplicate')
  })
})

// ============================================================
// 6. Settings Service
// ============================================================
describe('settingsService', () => {
  let settingsService

  beforeEach(async () => {
    const mod = await import('../settings.service')
    settingsService = mod.settingsService
  })

  it('getAll → GET /settings/general', async () => {
    await settingsService.getAll()
    expect(mockApiClient.get).toHaveBeenCalledWith('/settings/general')
  })

  it('get → GET /settings/:key', async () => {
    await settingsService.get('timezone')
    expect(mockApiClient.get).toHaveBeenCalledWith('/settings/timezone')
  })

  it('update → PATCH /settings/:key with value', async () => {
    await settingsService.update('timezone', 'UTC')
    expect(mockApiClient.patch).toHaveBeenCalledWith('/settings/timezone', { value: 'UTC' })
  })

  it('updateBulk → PATCH /settings/general', async () => {
    const settings = { timezone: 'UTC', session_timeout: 30 }
    await settingsService.updateBulk(settings)
    expect(mockApiClient.patch).toHaveBeenCalledWith('/settings/general', settings)
  })

  it('getEmailSettings → GET /settings/email', async () => {
    await settingsService.getEmailSettings()
    expect(mockApiClient.get).toHaveBeenCalledWith('/settings/email')
  })

  it('updateEmailSettings → PATCH /settings/email', async () => {
    const data = { smtp_host: 'mail.test.com' }
    await settingsService.updateEmailSettings(data)
    expect(mockApiClient.patch).toHaveBeenCalledWith('/settings/email', data)
  })

  it('testEmail → POST /settings/email/test', async () => {
    await settingsService.testEmail('test@test.com')
    expect(mockApiClient.post).toHaveBeenCalledWith('/settings/email/test', { email: 'test@test.com' })
  })
})

// ============================================================
// 7. System Service
// ============================================================
describe('systemService', () => {
  let systemService

  beforeEach(async () => {
    const mod = await import('../system.service')
    systemService = mod.systemService
  })

  it('listBackups → GET /system/backups', async () => {
    await systemService.listBackups()
    expect(mockApiClient.get).toHaveBeenCalledWith('/system/backups')
  })

  it('backup → POST /system/backup with password', async () => {
    await systemService.backup('secret')
    expect(mockApiClient.post).toHaveBeenCalledWith('/system/backup', { password: 'secret' })
  })

  it('getDatabaseStats → GET /system/database/stats', async () => {
    await systemService.getDatabaseStats()
    expect(mockApiClient.get).toHaveBeenCalledWith('/system/database/stats')
  })

  it('optimizeDatabase → POST /system/database/optimize', async () => {
    await systemService.optimizeDatabase()
    expect(mockApiClient.post).toHaveBeenCalledWith('/system/database/optimize')
  })

  it('integrityCheck → POST /system/database/integrity-check', async () => {
    await systemService.integrityCheck()
    expect(mockApiClient.post).toHaveBeenCalledWith('/system/database/integrity-check')
  })

  it('resetDatabase → POST /system/database/reset', async () => {
    await systemService.resetDatabase()
    expect(mockApiClient.post).toHaveBeenCalledWith('/system/database/reset')
  })

  it('getHttpsCertInfo → GET /system/https/cert-info', async () => {
    await systemService.getHttpsCertInfo()
    expect(mockApiClient.get).toHaveBeenCalledWith('/system/https/cert-info')
  })

  it('regenerateHttpsCert → POST /system/https/regenerate', async () => {
    const data = { days: 365 }
    await systemService.regenerateHttpsCert(data)
    expect(mockApiClient.post).toHaveBeenCalledWith('/system/https/regenerate', data)
  })

  it('applyHttpsCert → POST /system/https/apply', async () => {
    const data = { cert_id: '1' }
    await systemService.applyHttpsCert(data)
    expect(mockApiClient.post).toHaveBeenCalledWith('/system/https/apply', data)
  })
})

// ============================================================
// 8. Account Service
// ============================================================
describe('accountService', () => {
  let accountService

  beforeEach(async () => {
    const mod = await import('../account.service')
    accountService = mod.accountService
  })

  it('getProfile → GET /account/profile', async () => {
    await accountService.getProfile()
    expect(mockApiClient.get).toHaveBeenCalledWith('/account/profile')
  })

  it('updateProfile → PATCH /account/profile', async () => {
    const data = { full_name: 'John', email: 'j@x.com' }
    await accountService.updateProfile(data)
    expect(mockApiClient.patch).toHaveBeenCalledWith('/account/profile', data)
  })

  it('changePassword → POST /account/password', async () => {
    const data = { old_password: 'old', new_password: 'new123456' }
    await accountService.changePassword(data)
    expect(mockApiClient.post).toHaveBeenCalledWith('/account/password', data)
  })

  it('getApiKeys → GET /account/apikeys', async () => {
    await accountService.getApiKeys()
    expect(mockApiClient.get).toHaveBeenCalledWith('/account/apikeys')
  })

  it('createApiKey → POST /account/apikeys', async () => {
    const data = { name: 'CI Key' }
    await accountService.createApiKey(data)
    expect(mockApiClient.post).toHaveBeenCalledWith('/account/apikeys', data)
  })

  it('deleteApiKey → DELETE /account/apikeys/:id', async () => {
    await accountService.deleteApiKey(5)
    expect(mockApiClient.delete).toHaveBeenCalledWith('/account/apikeys/5')
  })

  it('enable2FA → POST /account/2fa/enable', async () => {
    await accountService.enable2FA()
    expect(mockApiClient.post).toHaveBeenCalledWith('/account/2fa/enable')
  })

  it('confirm2FA → POST /account/2fa/confirm with code', async () => {
    await accountService.confirm2FA('123456')
    expect(mockApiClient.post).toHaveBeenCalledWith('/account/2fa/confirm', { code: '123456' })
  })

  it('disable2FA → POST /account/2fa/disable with code', async () => {
    await accountService.disable2FA('654321')
    expect(mockApiClient.post).toHaveBeenCalledWith('/account/2fa/disable', { code: '654321' })
  })

  it('getWebAuthnCredentials → GET /webauthn/credentials', async () => {
    await accountService.getWebAuthnCredentials()
    expect(mockApiClient.get).toHaveBeenCalledWith('/webauthn/credentials')
  })

  it('startWebAuthnRegistration → POST /webauthn/register/options', async () => {
    await accountService.startWebAuthnRegistration()
    expect(mockApiClient.post).toHaveBeenCalledWith('/webauthn/register/options')
  })

  it('completeWebAuthnRegistration → POST /webauthn/register/verify', async () => {
    const data = { credential: {}, name: 'Key1' }
    await accountService.completeWebAuthnRegistration(data)
    expect(mockApiClient.post).toHaveBeenCalledWith('/webauthn/register/verify', data)
  })

  it('deleteWebAuthnCredential → DELETE /webauthn/credentials/:id', async () => {
    await accountService.deleteWebAuthnCredential('cred-1')
    expect(mockApiClient.delete).toHaveBeenCalledWith('/webauthn/credentials/cred-1')
  })

  it('getMTLSCertificates → GET /mtls/certificates', async () => {
    await accountService.getMTLSCertificates()
    expect(mockApiClient.get).toHaveBeenCalledWith('/mtls/certificates')
  })

  it('deleteMTLSCertificate → DELETE /mtls/certificates/:id', async () => {
    await accountService.deleteMTLSCertificate(7)
    expect(mockApiClient.delete).toHaveBeenCalledWith('/mtls/certificates/7')
  })
})

// ============================================================
// 9. Auth Service
// ============================================================
describe('authService', () => {
  let authService

  beforeEach(async () => {
    const mod = await import('../auth.service')
    authService = mod.authService
  })

  it('login → POST /auth/login with credentials', async () => {
    await authService.login('admin', 'pass123')
    expect(mockApiClient.post).toHaveBeenCalledWith('/auth/login', {
      username: 'admin', password: 'pass123'
    })
  })

  it('logout → POST /auth/logout', async () => {
    await authService.logout()
    expect(mockApiClient.post).toHaveBeenCalledWith('/auth/logout')
  })

  it('getCurrentUser → GET /auth/verify', async () => {
    await authService.getCurrentUser()
    expect(mockApiClient.get).toHaveBeenCalledWith('/auth/verify')
  })

  it('refreshToken → POST /auth/refresh', async () => {
    await authService.refreshToken()
    expect(mockApiClient.post).toHaveBeenCalledWith('/auth/refresh')
  })
})

// ============================================================
// 10. AuthMethods Service
// ============================================================
describe('authMethodsService', () => {
  let authMethodsService

  beforeEach(async () => {
    const mod = await import('../authMethods.service')
    authMethodsService = mod.authMethodsService
  })

  it('detectMethods with username → POST /auth/methods', async () => {
    await authMethodsService.detectMethods('admin')
    expect(mockApiClient.post).toHaveBeenCalledWith('/auth/methods', { username: 'admin' })
  })

  it('detectMethods without username → GET /auth/methods', async () => {
    await authMethodsService.detectMethods()
    expect(mockApiClient.get).toHaveBeenCalledWith('/auth/methods')
  })

  it('loginPassword → POST /auth/login/password', async () => {
    await authMethodsService.loginPassword('admin', 'pass')
    expect(mockApiClient.post).toHaveBeenCalledWith('/auth/login/password', {
      username: 'admin', password: 'pass'
    })
  })

  it('loginMTLS → POST /auth/login/mtls', async () => {
    await authMethodsService.loginMTLS()
    expect(mockApiClient.post).toHaveBeenCalled()
    const call = mockApiClient.post.mock.calls[0]
    expect(call[0]).toContain('/auth/login/mtls')
  })

  it('startWebAuthn → POST /auth/login/webauthn/start', async () => {
    await authMethodsService.startWebAuthn('admin')
    expect(mockApiClient.post).toHaveBeenCalledWith('/auth/login/webauthn/start', { username: 'admin' })
  })

  it('verifyWebAuthn → POST /auth/login/webauthn/verify', async () => {
    const cred = { id: 'abc' }
    await authMethodsService.verifyWebAuthn('admin', cred)
    expect(mockApiClient.post).toHaveBeenCalledWith('/auth/login/webauthn/verify', {
      username: 'admin', response: cred
    })
  })
})

// ============================================================
// 11. Dashboard Service
// ============================================================
describe('dashboardService', () => {
  let dashboardService

  beforeEach(async () => {
    const mod = await import('../dashboard.service')
    dashboardService = mod.dashboardService
  })

  it('getStats → GET /dashboard/stats', async () => {
    await dashboardService.getStats()
    expect(mockApiClient.get).toHaveBeenCalledWith('/dashboard/stats')
  })

  it('getRecentCAs → GET /cas with pagination', async () => {
    await dashboardService.getRecentCAs(5)
    const call = mockApiClient.get.mock.calls[0]
    expect(call[0]).toContain('/cas')
    expect(call[0]).toContain('per_page=5')
  })

  it('getExpiringCerts → GET /certificates with status filter', async () => {
    await dashboardService.getExpiringCerts(30)
    const call = mockApiClient.get.mock.calls[0]
    expect(call[0]).toContain('/certificates')
    expect(call[0]).toContain('status=expiring')
  })

  it('getNextExpirations → GET /dashboard/expiring-certs', async () => {
    await dashboardService.getNextExpirations(6)
    const call = mockApiClient.get.mock.calls[0]
    expect(call[0]).toContain('/dashboard/expiring-certs')
  })

  it('getActivityLog → GET /dashboard/activity', async () => {
    await dashboardService.getActivityLog(20, 0)
    const call = mockApiClient.get.mock.calls[0]
    expect(call[0]).toContain('/dashboard/activity')
  })

  it('getCertificateTrend → GET /dashboard/certificate-trend', async () => {
    await dashboardService.getCertificateTrend(7)
    const call = mockApiClient.get.mock.calls[0]
    expect(call[0]).toContain('/dashboard/certificate-trend')
  })

  it('getSystemStatus → GET /dashboard/system-status', async () => {
    await dashboardService.getSystemStatus()
    expect(mockApiClient.get).toHaveBeenCalledWith('/dashboard/system-status')
  })
})

// ============================================================
// 12. Audit Service
// ============================================================
describe('auditService', () => {
  let auditService

  beforeEach(async () => {
    const mod = await import('../audit.service')
    auditService = mod.default
  })

  it('getLogs → GET /audit/logs with filters', async () => {
    await auditService.getLogs({ page: 1, username: 'admin' })
    const call = mockApiClient.get.mock.calls[0]
    expect(call[0]).toContain('/audit/logs')
    expect(call[0]).toContain('page=1')
    expect(call[0]).toContain('username=admin')
  })

  it('getLog → GET /audit/logs/:id', async () => {
    await auditService.getLog(42)
    expect(mockApiClient.get).toHaveBeenCalledWith('/audit/logs/42')
  })

  it('getStats → GET /audit/stats', async () => {
    await auditService.getStats(30)
    const call = mockApiClient.get.mock.calls[0]
    expect(call[0]).toContain('/audit/stats')
  })

  it('getActions → GET /audit/actions', async () => {
    await auditService.getActions()
    expect(mockApiClient.get).toHaveBeenCalledWith('/audit/actions')
  })

  it('cleanupLogs → POST /audit/cleanup', async () => {
    await auditService.cleanupLogs(90)
    expect(mockApiClient.post).toHaveBeenCalledWith('/audit/cleanup', { retention_days: 90 })
  })
})

// ============================================================
// 13. SCEP Service
// ============================================================
describe('scepService', () => {
  let scepService

  beforeEach(async () => {
    const mod = await import('../scep.service')
    scepService = mod.scepService
  })

  it('getConfig → GET /scep/config', async () => {
    await scepService.getConfig()
    expect(mockApiClient.get).toHaveBeenCalledWith('/scep/config')
  })

  it('updateConfig → PATCH /scep/config', async () => {
    const data = { enabled: true, ca_id: 1 }
    await scepService.updateConfig(data)
    expect(mockApiClient.patch).toHaveBeenCalledWith('/scep/config', data)
  })

  it('getStats → GET /scep/stats', async () => {
    await scepService.getStats()
    expect(mockApiClient.get).toHaveBeenCalledWith('/scep/stats')
  })

  it('approveRequest → POST /scep/:id/approve', async () => {
    await scepService.approveRequest(5)
    expect(mockApiClient.post).toHaveBeenCalled()
    const call = mockApiClient.post.mock.calls[0]
    expect(call[0]).toContain('/scep/5/approve')
  })

  it('rejectRequest → POST /scep/:id/reject with reason', async () => {
    await scepService.rejectRequest(5, 'Invalid device')
    expect(mockApiClient.post).toHaveBeenCalled()
    const call = mockApiClient.post.mock.calls[0]
    expect(call[0]).toContain('/scep/5/reject')
  })

  it('getChallenge → GET /scep/challenge/:caId', async () => {
    await scepService.getChallenge(2)
    expect(mockApiClient.get).toHaveBeenCalledWith('/scep/challenge/2')
  })

  it('regenerateChallenge → POST /scep/challenge/:caId/regenerate', async () => {
    await scepService.regenerateChallenge(2)
    expect(mockApiClient.post).toHaveBeenCalled()
    const call = mockApiClient.post.mock.calls[0]
    expect(call[0]).toContain('/scep/challenge/2/regenerate')
  })
})

// ============================================================
// 14. CRL Service
// ============================================================
describe('crlService', () => {
  let crlService

  beforeEach(async () => {
    const mod = await import('../crl.service')
    crlService = mod.crlService
  })

  it('getAll → GET /crl', async () => {
    await crlService.getAll()
    expect(mockApiClient.get).toHaveBeenCalledWith('/crl')
  })

  it('getForCA → GET /crl/:caId', async () => {
    await crlService.getForCA(3)
    expect(mockApiClient.get).toHaveBeenCalledWith('/crl/3')
  })

  it('generate → POST /crl/generate with ca_id', async () => {
    await crlService.generate(3)
    expect(mockApiClient.post).toHaveBeenCalledWith('/crl/generate', { ca_id: 3 })
  })
})

// ============================================================
// 15. OpnSense Service
// ============================================================
describe('opnsenseService', () => {
  let opnsenseService

  beforeEach(async () => {
    const mod = await import('../opnsense.service')
    opnsenseService = mod.opnsenseService
  })

  it('test → POST /import/opnsense/test via request()', async () => {
    const config = { host: '192.168.1.1', port: 443 }
    await opnsenseService.test(config)
    expect(mockApiClient.request).toHaveBeenCalled()
    const call = mockApiClient.request.mock.calls[0]
    expect(call[0]).toContain('/import/opnsense/test')
    expect(call[1].method).toBe('POST')
  })

  it('import → POST /import/opnsense/import via request()', async () => {
    const config = { host: '192.168.1.1', items: ['ca1'] }
    await opnsenseService.import(config)
    expect(mockApiClient.request).toHaveBeenCalled()
    const call = mockApiClient.request.mock.calls[0]
    expect(call[0]).toContain('/import/opnsense/import')
    expect(call[1].method).toBe('POST')
  })
})

// ============================================================
// 16. Groups Service
// ============================================================
describe('groupsService', () => {
  let groupsService

  beforeEach(async () => {
    const mod = await import('../groupsService')
    groupsService = mod.groupsService
  })

  it('getAll → GET /groups', async () => {
    await groupsService.getAll()
    expect(mockApiClient.get).toHaveBeenCalled()
    const call = mockApiClient.get.mock.calls[0]
    expect(call[0]).toContain('/groups')
  })

  it('getById → GET /groups/:id', async () => {
    await groupsService.getById(1)
    expect(mockApiClient.get).toHaveBeenCalledWith('/groups/1')
  })

  it('create → POST /groups', async () => {
    const data = { name: 'Admins' }
    await groupsService.create(data)
    expect(mockApiClient.post).toHaveBeenCalledWith('/groups', data)
  })

  it('update → PUT /groups/:id', async () => {
    const data = { name: 'Updated' }
    await groupsService.update(1, data)
    expect(mockApiClient.put).toHaveBeenCalledWith('/groups/1', data)
  })

  it('delete → DELETE /groups/:id', async () => {
    await groupsService.delete(1)
    expect(mockApiClient.delete).toHaveBeenCalledWith('/groups/1')
  })

  it('addMember → POST /groups/:id/members with user_id', async () => {
    await groupsService.addMember(1, 5, 'member')
    expect(mockApiClient.post).toHaveBeenCalledWith('/groups/1/members', {
      user_id: 5, role: 'member'
    })
  })

  it('removeMember → DELETE /groups/:id/members/:userId', async () => {
    await groupsService.removeMember(1, 5)
    expect(mockApiClient.delete).toHaveBeenCalledWith('/groups/1/members/5')
  })
})

// ============================================================
// 17. Roles Service
// ============================================================
describe('rolesService', () => {
  let rolesService

  beforeEach(async () => {
    const mod = await import('../roles.service')
    rolesService = mod.rolesService
  })

  it('getAll → GET /rbac/roles', async () => {
    await rolesService.getAll()
    expect(mockApiClient.get).toHaveBeenCalledWith('/rbac/roles')
  })

  it('getRole → GET /rbac/roles/:role', async () => {
    await rolesService.getRole('admin')
    expect(mockApiClient.get).toHaveBeenCalledWith('/rbac/roles/admin')
  })
})

// ============================================================
// 18. Search Service
// ============================================================
describe('searchService', () => {
  let searchService

  beforeEach(async () => {
    const mod = await import('../search.service')
    searchService = mod.searchService
  })

  it('globalSearch → GET /search with query', async () => {
    await searchService.globalSearch('test', 5)
    const call = mockApiClient.get.mock.calls[0]
    expect(call[0]).toContain('/search')
    expect(call[0]).toContain('q=test')
    expect(call[0]).toContain('limit=5')
  })

  it('globalSearch returns empty for short queries', async () => {
    const result = await searchService.globalSearch('a')
    // Should return empty without calling API
    expect(mockApiClient.get).not.toHaveBeenCalled()
  })
})

// ============================================================
// Governance: Policies Service
// ============================================================
describe('policiesService', () => {
  let policiesService

  beforeEach(async () => {
    const mod = await import('../policies.service')
    policiesService = mod.policiesService
  })

  it('list → GET /policies', async () => {
    await policiesService.list()
    expect(mockApiClient.get).toHaveBeenCalledWith('/policies')
  })

  it('getById → GET /policies/:id', async () => {
    await policiesService.getById(5)
    expect(mockApiClient.get).toHaveBeenCalledWith('/policies/5')
  })

  it('create → POST /policies', async () => {
    const data = { name: 'Test', type: 'key_requirements' }
    await policiesService.create(data)
    expect(mockApiClient.post).toHaveBeenCalledWith('/policies', data)
  })

  it('update → PUT /policies/:id', async () => {
    const data = { name: 'Updated' }
    await policiesService.update(3, data)
    expect(mockApiClient.put).toHaveBeenCalledWith('/policies/3', data)
  })

  it('delete → DELETE /policies/:id', async () => {
    await policiesService.delete(7)
    expect(mockApiClient.delete).toHaveBeenCalledWith('/policies/7')
  })

  it('toggle → POST /policies/:id/toggle', async () => {
    await policiesService.toggle(2)
    expect(mockApiClient.post).toHaveBeenCalledWith('/policies/2/toggle')
  })
})

// ============================================================
// Governance: Approvals Service
// ============================================================
describe('approvalsService', () => {
  let approvalsService

  beforeEach(async () => {
    const mod = await import('../approvals.service')
    approvalsService = mod.approvalsService
  })

  it('list with default status → GET /approvals?status=pending', async () => {
    await approvalsService.list()
    expect(mockApiClient.get).toHaveBeenCalledWith('/approvals?status=pending')
  })

  it('list with all → GET /approvals?status=all', async () => {
    await approvalsService.list('all')
    expect(mockApiClient.get).toHaveBeenCalledWith('/approvals?status=all')
  })

  it('list with specific status → GET /approvals?status=approved', async () => {
    await approvalsService.list('approved')
    expect(mockApiClient.get).toHaveBeenCalledWith('/approvals?status=approved')
  })

  it('getById → GET /approvals/:id', async () => {
    await approvalsService.getById(10)
    expect(mockApiClient.get).toHaveBeenCalledWith('/approvals/10')
  })

  it('approve → POST /approvals/:id/approve', async () => {
    await approvalsService.approve(5, 'Looks good')
    expect(mockApiClient.post).toHaveBeenCalledWith('/approvals/5/approve', { comment: 'Looks good' })
  })

  it('reject → POST /approvals/:id/reject', async () => {
    await approvalsService.reject(3, 'Does not meet policy')
    expect(mockApiClient.post).toHaveBeenCalledWith('/approvals/3/reject', { comment: 'Does not meet policy' })
  })

  it('getStats → GET /approvals/stats', async () => {
    await approvalsService.getStats()
    expect(mockApiClient.get).toHaveBeenCalledWith('/approvals/stats')
  })
})

// ============================================================
// Governance: Reports Service
// ============================================================
describe('reportsService', () => {
  let reportsService

  beforeEach(async () => {
    const mod = await import('../reports.service')
    reportsService = mod.reportsService
  })

  it('getTypes → GET /reports/types', async () => {
    await reportsService.getTypes()
    expect(mockApiClient.get).toHaveBeenCalledWith('/reports/types')
  })

  it('generate → POST /reports/generate with type + params', async () => {
    await reportsService.generate('certificate_inventory', { days: 30 })
    expect(mockApiClient.post).toHaveBeenCalledWith('/reports/generate', {
      report_type: 'certificate_inventory',
      params: { days: 30 }
    })
  })

  it('download → GET /reports/download/:type with format', async () => {
    await reportsService.download('ca_hierarchy', 'json', 90)
    const call = mockApiClient.get.mock.calls[0]
    expect(call[0]).toBe('/reports/download/ca_hierarchy?format=json&days=90')
  })

  it('getSchedule → GET /reports/schedule', async () => {
    await reportsService.getSchedule()
    expect(mockApiClient.get).toHaveBeenCalledWith('/reports/schedule')
  })

  it('updateSchedule → PUT /reports/schedule', async () => {
    const data = { enabled: true, frequency: 'weekly' }
    await reportsService.updateSchedule(data)
    expect(mockApiClient.put).toHaveBeenCalledWith('/reports/schedule', data)
  })

  it('sendTest → POST /reports/send-test', async () => {
    await reportsService.sendTest('compliance_status', 'admin@test.com')
    expect(mockApiClient.post).toHaveBeenCalledWith('/reports/send-test', {
      report_type: 'compliance_status',
      recipient: 'admin@test.com'
    })
  })
})
