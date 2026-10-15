/**
 * Certificate Policies Service
 */
import { apiClient, buildQueryString } from './apiClient'

export const policiesService = {
  async list() {
    return apiClient.get('/policies')
  },

  async getById(id) {
    return apiClient.get(`/policies/${id}`)
  },

  async create(data) {
    return apiClient.post('/policies', data)
  },

  async update(id, data) {
    return apiClient.put(`/policies/${id}`, data)
  },

  async delete(id) {
    return apiClient.delete(`/policies/${id}`)
  },

  async toggle(id) {
    return apiClient.post(`/policies/${id}/toggle`)
  },

  // Key types and signature hashes the active policies allow for a CA/template (null = unrestricted)
  async getEffective({ ca_id, template_id } = {}) {
    return apiClient.get(`/policies/effective${buildQueryString({ ca_id, template_id })}`)
  },
}
