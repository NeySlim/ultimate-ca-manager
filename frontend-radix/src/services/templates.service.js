/**
 * Templates Service
 */
import { apiClient } from './apiClient'

export const templatesService = {
  async getAll() {
    return apiClient.get('/templates')
  },

  async getById(id) {
    return apiClient.get(`/templates/${id}`)
  },

  async create(data) {
    return apiClient.post('/templates', data)
  },

  async update(id, data) {
    return apiClient.put(`/templates/${id}`, data)
  },

  async delete(id) {
    return apiClient.delete(`/templates/${id}`)
  },

  async duplicate(id) {
    return apiClient.post(`/templates/${id}/duplicate`)
  }
}
