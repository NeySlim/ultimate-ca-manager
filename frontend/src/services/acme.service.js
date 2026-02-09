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

  // Proxy
  async registerProxy(email) {
    return apiClient.post('/acme/proxy/register', { email })
  },

  async unregisterProxy() {
    return apiClient.post('/acme/proxy/unregister')
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
  }
}
