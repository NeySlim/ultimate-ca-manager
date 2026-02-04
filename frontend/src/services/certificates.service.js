/**
 * Certificates Service
 */
import { apiClient } from './apiClient'

export const certificatesService = {
  async getAll(filters = {}) {
    const params = new URLSearchParams()
    if (filters.status) params.append('status', filters.status)
    if (filters.ca_id) params.append('ca_id', filters.ca_id)
    if (filters.issuer) params.append('issuer', filters.issuer)
    if (filters.search) params.append('search', filters.search)
    if (filters.page) params.append('page', filters.page)
    if (filters.per_page) params.append('per_page', filters.per_page)
    if (filters.sort_by) params.append('sort_by', filters.sort_by)
    if (filters.sort_order) params.append('sort_order', filters.sort_order)
    
    const query = params.toString() ? `?${params.toString()}` : ''
    return apiClient.get(`/certificates${query}`)
  },

  async getStats() {
    return apiClient.get('/certificates/stats')
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

  async export(id, format = 'pem', options = {}) {
    const params = new URLSearchParams()
    params.append('format', format)
    if (options.includeKey) params.append('include_key', 'true')
    if (options.includeChain) params.append('include_chain', 'true')
    if (options.password) params.append('password', options.password)
    
    return apiClient.get(`/certificates/${id}/export?${params.toString()}`, {
      responseType: 'blob'
    })
  },

  async delete(id) {
    return apiClient.delete(`/certificates/${id}`)
  },

  async import(formData) {
    // FormData for file upload
    return apiClient.upload('/certificates/import', formData)
  },

  async uploadKey(id, keyPem, passphrase = null) {
    return apiClient.post(`/certificates/${id}/key`, { 
      key: keyPem,
      passphrase 
    })
  }
}
