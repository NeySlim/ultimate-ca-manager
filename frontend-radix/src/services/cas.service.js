/**
 * Certificate Authorities Service
 */
import { apiClient } from './apiClient'

export const casService = {
  async getAll() {
    return apiClient.get('/cas')
  },

  async getTree() {
    return apiClient.get('/cas/tree')
  },

  async getById(id) {
    return apiClient.get(`/cas/${id}`)
  },

  async create(data) {
    return apiClient.post('/cas', data)
  },

  async update(id, data) {
    return apiClient.put(`/cas/${id}`, data)
  },

  async delete(id) {
    return apiClient.delete(`/cas/${id}`)
  },

  async export(id, format = 'pem') {
    return apiClient.get(`/cas/${id}/export?format=${format}`, {
      responseType: 'blob'
    })
  },

  async getCertificates(id, filters = {}) {
    const params = new URLSearchParams()
    if (filters.page) params.append('page', filters.page)
    if (filters.per_page) params.append('per_page', filters.per_page)
    
    const query = params.toString() ? `?${params.toString()}` : ''
    return apiClient.get(`/cas/${id}/certificates${query}`)
  }
}
