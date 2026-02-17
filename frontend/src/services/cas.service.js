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
    return apiClient.patch(`/cas/${id}`, data)
  },

  async delete(id) {
    return apiClient.delete(`/cas/${id}`)
  },

  async import(formData) {
    // FormData for file upload
    return apiClient.upload('/cas/import', formData)
  },

  async export(id, format = 'pem', options = {}) {
    const params = new URLSearchParams()
    params.append('format', format)
    if (options.includeKey) params.append('include_key', 'true')
    if (options.includeChain) params.append('include_chain', 'true')  
    if (options.password) params.append('password', options.password)
    
    return apiClient.get(`/cas/${id}/export?${params.toString()}`, {
      responseType: 'blob'
    })
  },

  async exportAll(format = 'pem', options = {}) {
    const params = new URLSearchParams()
    params.append('format', format)
    if (options.includeChain) params.append('include_chain', 'true')
    if (options.password) params.append('password', options.password)
    
    return apiClient.get(`/cas/export?${params.toString()}`, {
      responseType: 'blob'
    })
  },

  async getCertificates(id, filters = {}) {
    const params = new URLSearchParams()
    if (filters.page) params.append('page', filters.page)
    if (filters.per_page) params.append('per_page', filters.per_page)
    
    const query = params.toString() ? `?${params.toString()}` : ''
    return apiClient.get(`/cas/${id}/certificates${query}`)
  },

  // Bulk operations
  async bulkDelete(ids) {
    return apiClient.post('/cas/bulk/delete', { ids })
  },
  async bulkExport(ids, format = 'pem') {
    return apiClient.post('/cas/bulk/export', { ids, format }, { responseType: 'blob' })
  }
}
