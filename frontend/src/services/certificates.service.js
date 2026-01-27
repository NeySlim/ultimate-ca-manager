/**
 * Certificates Service
 */
import { apiClient } from './apiClient'

export const certificatesService = {
  async getAll(filters = {}) {
    const params = new URLSearchParams()
    if (filters.status) params.append('status', filters.status)
    if (filters.issuer) params.append('issuer', filters.issuer)
    if (filters.search) params.append('search', filters.search)
    if (filters.page) params.append('page', filters.page)
    if (filters.per_page) params.append('per_page', filters.per_page)
    
    const query = params.toString() ? `?${params.toString()}` : ''
    return apiClient.get(`/certificates${query}`)
  },

  async getById(id) {
    return apiClient.get(`/certificates/${id}`)
  },

  async create(data) {
    return apiClient.post('/certificates', data)
  },

  async revoke(id, reason) {
    return apiClient.post(`/certificates/${id}/revoke`, { reason })
  },

  async renew(id) {
    return apiClient.post(`/certificates/${id}/renew`)
  },

  async export(id, format = 'pem') {
    return apiClient.get(`/certificates/${id}/export?format=${format}`, {
      responseType: 'blob'
    })
  },

  async delete(id) {
    return apiClient.delete(`/certificates/${id}`)
  },

  async import(data) {
    return apiClient.post('/certificates/import', data)
  }
}
