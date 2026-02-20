/**
 * Users Service
 */
import { apiClient, buildQueryString } from './apiClient'

export const usersService = {
  async getAll(filters = {}) {
    return apiClient.get(`/users${buildQueryString(filters)}`)
  },

  async getById(id) {
    return apiClient.get(`/users/${id}`)
  },

  async create(data) {
    return apiClient.post('/users', data)
  },

  async update(id, data) {
    return apiClient.put(`/users/${id}`, data)
  },

  async delete(id) {
    return apiClient.delete(`/users/${id}`)
  },

  async resetPassword(id) {
    return apiClient.post(`/users/${id}/reset-password`)
  },

  async toggleActive(id) {
    return apiClient.post(`/users/${id}/toggle-active`)
  },

  // Bulk operations
  async bulkDelete(ids) {
    return apiClient.post('/users/bulk/delete', { ids })
  }
}
