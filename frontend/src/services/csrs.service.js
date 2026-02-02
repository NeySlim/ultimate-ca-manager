/**
 * Certificate Signing Requests Service
 */
import { apiClient } from './apiClient'

export const csrsService = {
  async getAll(filters = {}) {
    const params = new URLSearchParams()
    if (filters.page) params.append('page', filters.page)
    if (filters.per_page) params.append('per_page', filters.per_page)
    
    const query = params.toString() ? `?${params.toString()}` : ''
    return apiClient.get(`/csrs${query}`)
  },

  async getHistory(filters = {}) {
    const params = new URLSearchParams()
    if (filters.page) params.append('page', filters.page)
    if (filters.per_page) params.append('per_page', filters.per_page)
    
    const query = params.toString() ? `?${params.toString()}` : ''
    return apiClient.get(`/csrs/history${query}`)
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
    return apiClient.get(`/csrs/${id}/download`, {
      responseType: 'blob'
    })
  }
}
