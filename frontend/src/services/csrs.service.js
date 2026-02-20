/**
 * Certificate Signing Requests Service
 */
import { apiClient, buildQueryString } from './apiClient'

export const csrsService = {
  async getAll(filters = {}) {
    return apiClient.get(`/csrs${buildQueryString(filters)}`)
  },

  async getHistory(filters = {}) {
    return apiClient.get(`/csrs/history${buildQueryString(filters)}`)
  },

  async getById(id) {
    return apiClient.get(`/csrs/${id}`)
  },

  async create(data) {
    return apiClient.post('/csrs', data)
  },

  async upload(pemData) {
    return apiClient.post('/csrs/upload', { pem: pemData })
  },

  async import(formData) {
    return apiClient.upload('/csrs/import', formData)
  },

  async export(id) {
    return apiClient.get(`/csrs/${id}/export`, {
      responseType: 'blob'
    })
  },

  async sign(id, ca_id, validity_days) {
    return apiClient.post(`/csrs/${id}/sign`, { ca_id, validity_days })
  },

  async delete(id) {
    return apiClient.delete(`/csrs/${id}`)
  },

  async uploadKey(id, keyPem, passphrase = null) {
    return apiClient.post(`/csrs/${id}/key`, { 
      key: keyPem,
      passphrase 
    })
  },

  async download(id) {
    return apiClient.get(`/csrs/${id}/export`, {
      responseType: 'blob'
    })
  },

  // Bulk operations
  async bulkSign(ids, ca_id, validity_days = 365) {
    return apiClient.post('/csrs/bulk/sign', { ids, ca_id, validity_days })
  },
  async bulkDelete(ids) {
    return apiClient.post('/csrs/bulk/delete', { ids })
  }
}
