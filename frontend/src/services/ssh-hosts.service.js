/**
 * SSH hosts and their enrollment tokens (issue #451)
 */
import { apiClient, buildQueryString } from './apiClient'

export const sshHostsService = {
  async getAll(params) {
    return apiClient.get(`/ssh/hosts${buildQueryString(params)}`)
  },

  async getById(id) {
    return apiClient.get(`/ssh/hosts/${id}`)
  },

  async revoke(id, reason) {
    return apiClient.post(`/ssh/hosts/${id}/revoke`, { reason })
  },

  async setAutoRenew(id, enabled) {
    return apiClient.post(`/ssh/hosts/${id}/auto-renew`, { enabled })
  },

  async getTokens(params) {
    return apiClient.get(`/ssh/enrollment-tokens${buildQueryString(params)}`)
  },

  async createToken(data) {
    return apiClient.post('/ssh/enrollment-tokens', data)
  },

  async revokeToken(id) {
    return apiClient.post(`/ssh/enrollment-tokens/${id}/revoke`)
  },
}
