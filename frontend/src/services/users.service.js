/**
 * Users Service
 */
import { apiClient } from './apiClient'

export const usersService = {
  async getAll(filters = {}) {
    const params = new URLSearchParams()
    if (filters.role) params.append('role', filters.role)
    if (filters.active !== undefined) params.append('active', filters.active)
    
    const query = params.toString() ? `?${params.toString()}` : ''
    return apiClient.get(`/users${query}`)
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
