/**
 * Certificates Service
 */
import { apiClient, buildQueryString } from './apiClient'

export const certificatesService = {
  async getAll(filters = {}) {
    return apiClient.get(`/certificates${buildQueryString(filters)}`)
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
    return apiClient.get(`/certificates/${id}/export${buildQueryString({
      format,
      include_key: options.includeKey || undefined,
      include_chain: options.includeChain || undefined,
      password: options.password
    })}`, { responseType: 'blob' })
  },

  async exportAll(format = 'pem', options = {}) {
    return apiClient.get(`/certificates/export${buildQueryString({
      format,
      include_chain: options.includeChain || undefined,
      password: options.password
    })}`, { responseType: 'blob' })
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
  },

  // Bulk operations
  async bulkRevoke(ids, reason = 'unspecified') {
    return apiClient.post('/certificates/bulk/revoke', { ids, reason })
  },
  async bulkRenew(ids) {
    return apiClient.post('/certificates/bulk/renew', { ids })
  },
  async bulkDelete(ids) {
    return apiClient.post('/certificates/bulk/delete', { ids })
  },
  async bulkExport(ids, format = 'pem') {
    return apiClient.post('/certificates/bulk/export', { ids, format }, { responseType: 'blob' })
  }
}
