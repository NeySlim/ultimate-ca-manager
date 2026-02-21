/**
 * Certificate Authorities Service
 */
import { apiClient, buildQueryString } from './apiClient'

export const casService = {
  async getAll() {
    return apiClient.get('/cas')
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
    return apiClient.get(`/cas/${id}/export${buildQueryString({
      format,
      include_key: options.includeKey ?? false,
      include_chain: options.includeChain ?? false,
      password: options.password
    })}`, { responseType: 'blob' })
  },

  async exportAll(format = 'pem', options = {}) {
    return apiClient.get(`/cas/export${buildQueryString({
      format,
      include_chain: options.includeChain ?? false,
      password: options.password
    })}`, { responseType: 'blob' })
  },

  async getCertificates(id, filters = {}) {
    return apiClient.get(`/cas/${id}/certificates${buildQueryString(filters)}`)
  },

  // Bulk operations
  async bulkDelete(ids) {
    return apiClient.post('/cas/bulk/delete', { ids })
  },
  async bulkExport(ids, format = 'pem') {
    return apiClient.post('/cas/bulk/export', { ids, format }, { responseType: 'blob' })
  }
}
