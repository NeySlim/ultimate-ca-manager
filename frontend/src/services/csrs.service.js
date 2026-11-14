/**
 * Certificate Signing Requests Service
 */
import { apiClient, buildQueryString } from './apiClient'
import { runInBatches } from '../lib/bulkChunks'

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

  // extra_sans: { san_dns, san_ip, san_email, san_uri } added to the request's names;
  // options: { override_unique_subject } once the operator confirmed a taken subject
  async sign(id, ca_id, validity_days, cert_type = 'server', extra_ekus = [], extra_sans = {}, options = {}) {
    const payload = { ca_id, validity_days, cert_type, ...extra_sans, ...options }
    if (Array.isArray(extra_ekus) && extra_ekus.length) payload.extra_ekus = extra_ekus
    return apiClient.post(`/csrs/${id}/sign`, payload)
  },

  // A signed request back in the pending list, to be signed again
  async resubmit(id) {
    return apiClient.post(`/csrs/${id}/resubmit`)
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

  // Private key of a CSR generated in UCM (read:private_keys). A password
  // travels in the POST body only, never the query string.
  async downloadKey(id, password = null) {
    if (password) {
      return apiClient.post(`/csrs/${id}/export`, { format: 'key', password }, {
        responseType: 'blob'
      })
    }
    return apiClient.get(`/csrs/${id}/export?format=key`, {
      responseType: 'blob'
    })
  },

  // Bulk operations
  async bulkSign(ids, ca_id, validity_days = 365) {
    return runInBatches(ids, (batch) =>
      apiClient.post('/csrs/bulk/sign', { ids: batch, ca_id, validity_days }))
  },
  async bulkDelete(ids) {
    return runInBatches(ids, (batch) =>
      apiClient.post('/csrs/bulk/delete', { ids: batch }))
  }
}
