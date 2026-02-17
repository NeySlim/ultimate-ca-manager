/**
 * HSM Service
 */
import { apiClient } from './apiClient'

export const hsmService = {
  async getProviders() {
    return apiClient.get('/hsm/providers')
  },

  async getStatus() {
    return apiClient.get('/system/hsm-status')
  },

  async getKeys(providerId) {
    return apiClient.get(`/hsm/keys?provider_id=${providerId}`)
  },

  async deleteProvider(id) {
    return apiClient.delete(`/hsm/providers/${id}`)
  },

  async testProvider(id) {
    return apiClient.post(`/hsm/providers/${id}/test`)
  },

  async createProvider(data) {
    return apiClient.post('/hsm/providers', data)
  },

  async updateProvider(id, data) {
    return apiClient.put(`/hsm/providers/${id}`, data)
  },

  async addKey(providerId, keyData) {
    return apiClient.post(`/hsm/providers/${providerId}/keys`, keyData)
  },

  async deleteKey(id) {
    return apiClient.delete(`/hsm/keys/${id}`)
  },

  async installDependencies() {
    return apiClient.post('/hsm/dependencies/install')
  }
}
