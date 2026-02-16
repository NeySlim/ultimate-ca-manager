/**
 * Certificate Policies Service
 */
import { apiClient } from './apiClient'

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
}
