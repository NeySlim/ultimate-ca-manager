/**
 * ACME Service
 */
import { apiClient, buildQueryString } from './apiClient'

export const acmeService = {
  // Settings (ACME Server)
  async getSettings() {
    return apiClient.get('/acme/settings')
  },

  async updateSettings(data) {
    return apiClient.patch('/acme/settings', data)
  },

  async getStats() {
    return apiClient.get('/acme/stats')
  },

  // Accounts (ACME Server accounts)
  async getAccounts() {
    return apiClient.get('/acme/accounts')
  },

  async getAccountById(id) {
    return apiClient.get(`/acme/accounts/${id}`)
  },

  async createAccount(data) {
    return apiClient.post('/acme/accounts', data)
  },

  async deactivateAccount(id) {
    return apiClient.post(`/acme/accounts/${id}/deactivate`)
  },

  async deleteAccount(id) {
    return apiClient.delete(`/acme/accounts/${id}`)
  },

  // Orders (ACME Server orders)
  async getOrders(accountId) {
    return apiClient.get(`/acme/accounts/${accountId}/orders`)
  },

  async getChallenges(accountId) {
    return apiClient.get(`/acme/accounts/${accountId}/challenges`)
  },

  // History
  async getHistory() {
    return apiClient.get('/acme/history')
  },

  // =========================================================================
  // EAB Credentials (RFC 8555 §7.3.4 — External Account Binding)
  // =========================================================================

  async getEabRequired() {
    return apiClient.get('/acme/eab-required')
  },

  async setEabRequired(value) {
    return apiClient.put('/acme/eab-required', { eab_required: !!value })
  },

  async listEabCredentials(status) {
    const qs = status ? buildQueryString({ status }) : ''
    return apiClient.get(`/acme/eab-credentials${qs}`)
  },

  async createEabCredential(data) {
    // Returns { kid, hmac_key, ... } — hmac_key is shown ONCE.
    return apiClient.post('/acme/eab-credentials', data)
  },

  async getEabCredential(id) {
    return apiClient.get(`/acme/eab-credentials/${id}`)
  },

  async patchEabCredential(id, data) {
    return apiClient.patch(`/acme/eab-credentials/${id}`, data)
  },

  async deleteEabCredential(id) {
    return apiClient.delete(`/acme/eab-credentials/${id}`)
  },

  async revokeEabCredential(id) {
    return apiClient.delete(`/acme/eab-credentials/${id}`)
  },

  // =========================================================================
  // ACME Client (Let's Encrypt)
  // =========================================================================

  // Client Settings
  async getClientSettings() {
    return apiClient.get('/acme/client/settings')
  },

  async updateClientSettings(data) {
    return apiClient.patch('/acme/client/settings', data)
  },

  // LE Proxy
  async registerProxy(email, acmeAccountId) {
    const payload = { email }
    if (acmeAccountId != null) payload.acme_account_id = acmeAccountId
    return apiClient.post('/acme/client/proxy/register', payload)
  },

  async unregisterProxy(acmeAccountId) {
    const payload = {}
    if (acmeAccountId != null) payload.acme_account_id = acmeAccountId
    return apiClient.post('/acme/client/proxy/unregister', payload)
  },

  async testProxyConnection({ url, acmeAccountId } = {}) {
    const payload = {}
    if (url) payload.url = url
    if (acmeAccountId != null) payload.acme_account_id = acmeAccountId
    return apiClient.post('/acme/client/proxy/test-connection', payload)
  },

  // Client Account (Let's Encrypt account)
  async registerClientAccount(email, environment = 'staging') {
    return apiClient.post('/acme/client/account', { email, environment })
  },

  // Client CA Accounts (multi-CA: Let's Encrypt, Actalis, ZeroSSL...)
  async getCaAccounts() {
    return apiClient.get('/acme/client/accounts')
  },

  async getCaAccount(id) {
    return apiClient.get(`/acme/client/accounts/${id}`)
  },

  async createCaAccount(data) {
    return apiClient.post('/acme/client/accounts', data)
  },

  async updateCaAccount(id, data) {
    return apiClient.patch(`/acme/client/accounts/${id}`, data)
  },

  async deleteCaAccount(id) {
    return apiClient.delete(`/acme/client/accounts/${id}`)
  },

  async setDefaultCaAccount(id) {
    return apiClient.post(`/acme/client/accounts/${id}/default`)
  },

  async registerCaAccount(id, email) {
    return apiClient.post(`/acme/client/accounts/${id}/register`, email ? { email } : {})
  },

  // Client Orders (certificates from Let's Encrypt)
  async getClientOrders(status, environment) {
    return apiClient.get(`/acme/client/orders${buildQueryString({ status, environment })}`)
  },

  async getClientOrder(orderId) {
    return apiClient.get(`/acme/client/orders/${orderId}`)
  },

  async requestCertificate(data) {
    return apiClient.post('/acme/client/request', data)
  },

  async preflightCertificate(data) {
    return apiClient.post('/acme/client/preflight', data)
  },

  async verifyChallenge(orderId, domain = null, force = false) {
    const body = {}
    if (domain) body.domain = domain
    if (force) body.force = true
    return apiClient.post(`/acme/client/orders/${orderId}/verify`, body)
  },

  async checkOrderStatus(orderId) {
    return apiClient.get(`/acme/client/orders/${orderId}/status`)
  },

  async finalizeOrder(orderId) {
    return apiClient.post(`/acme/client/orders/${orderId}/finalize`)
  },

  async cancelOrder(orderId) {
    return apiClient.delete(`/acme/client/orders/${orderId}`)
  },

  async deleteOrder(orderId) {
    return apiClient.delete(`/acme/client/orders/${orderId}`)
  },

  async renewOrder(orderId) {
    return apiClient.post(`/acme/client/orders/${orderId}/renew`)
  },

  // =========================================================================
  // DNS Providers
  // =========================================================================

  async getDnsProviders() {
    return apiClient.get('/dns-providers')
  },

  async getDnsProviderTypes() {
    return apiClient.get('/dns-providers/types')
  },

  async getDnsProvider(id) {
    return apiClient.get(`/dns-providers/${id}`)
  },

  async createDnsProvider(data) {
    return apiClient.post('/dns-providers', data)
  },

  async updateDnsProvider(id, data) {
    return apiClient.patch(`/dns-providers/${id}`, data)
  },

  async deleteDnsProvider(id) {
    return apiClient.delete(`/dns-providers/${id}`)
  },

  async testDnsProvider(id) {
    return apiClient.post(`/dns-providers/${id}/test`)
  },

  // =========================================================================
  // ACME Domains (Domain to Provider mapping)
  // =========================================================================

  async getDomains() {
    return apiClient.get('/acme/domains')
  },

  async getDomain(id) {
    return apiClient.get(`/acme/domains/${id}`)
  },

  async createDomain(data) {
    return apiClient.post('/acme/domains', data)
  },

  async updateDomain(id, data) {
    return apiClient.put(`/acme/domains/${id}`, data)
  },

  async deleteDomain(id) {
    return apiClient.delete(`/acme/domains/${id}`)
  },

  async resolveDomain(domain) {
    return apiClient.get(`/acme/domains/resolve${buildQueryString({ domain })}`)
  },

  async testDomainAccess(domain, dnsProviderId = null) {
    return apiClient.post('/acme/domains/test', { 
      domain, 
      dns_provider_id: dnsProviderId 
    })
  },

  // =========================================================================
  // Local ACME Domains (Domain to CA mapping)
  // =========================================================================

  async getLocalDomains() {
    return apiClient.get('/acme/local-domains')
  },

  async createLocalDomain(data) {
    return apiClient.post('/acme/local-domains', data)
  },

  async updateLocalDomain(id, data) {
    return apiClient.put(`/acme/local-domains/${id}`, data)
  },

  async deleteLocalDomain(id) {
    return apiClient.delete(`/acme/local-domains/${id}`)
  }
}
