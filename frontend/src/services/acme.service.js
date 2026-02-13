/**
 * ACME Service
 */
import { apiClient } from './apiClient'

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
  async registerProxy(email) {
    return apiClient.post('/acme/client/proxy/register', { email })
  },

  async unregisterProxy() {
    return apiClient.post('/acme/client/proxy/unregister')
  },

  // Client Account (Let's Encrypt account)
  async registerClientAccount(email, environment = 'staging') {
    return apiClient.post('/acme/client/account', { email, environment })
  },

  // Client Orders (certificates from Let's Encrypt)
  async getClientOrders(status, environment) {
    const params = new URLSearchParams()
    if (status) params.append('status', status)
    if (environment) params.append('environment', environment)
    const query = params.toString()
    return apiClient.get(`/acme/client/orders${query ? `?${query}` : ''}`)
  },

  async getClientOrder(orderId) {
    return apiClient.get(`/acme/client/orders/${orderId}`)
  },

  async requestCertificate(data) {
    // data: { domains, email, challenge_type, environment, dns_provider_id }
    return apiClient.post('/acme/client/request', data)
  },

  async verifyChallenge(orderId, domain = null) {
    return apiClient.post(`/acme/client/orders/${orderId}/verify`, domain ? { domain } : {})
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
    return apiClient.get(`/acme/domains/resolve?domain=${encodeURIComponent(domain)}`)
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
