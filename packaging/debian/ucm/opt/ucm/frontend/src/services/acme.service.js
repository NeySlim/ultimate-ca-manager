/**
 * ACME Service
 */
import { apiClient } from './apiClient'

export const acmeService = {
  // Settings
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

  // Accounts
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

  // Orders
  async getOrders(accountId) {
    return apiClient.get(`/acme/accounts/${accountId}/orders`)
  },

  async getChallenges(accountId) {
    return apiClient.get(`/acme/accounts/${accountId}/challenges`)
  },

  // History
  async getHistory() {
    return apiClient.get('/acme/history')
  }
}
