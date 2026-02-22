/**
 * CRL (Certificate Revocation List) Service
 */
import { apiClient } from './apiClient'

export const crlService = {
  async getAll() {
    return apiClient.get('/crl')
  },

  async getById(id) {
    return apiClient.get(`/crl/${id}`)
  },

  async getForCA(caId) {
    return apiClient.get(`/crl/${caId}`)
  },

  async generate(caId) {
    return apiClient.post(`/crl/${caId}/regenerate`)
  },

  async download(id) {
    return apiClient.get(`/crl/${id}/download`, {
      responseType: 'blob'
    })
  },

  async regenerate(caId) {
    return apiClient.post(`/crl/${caId}/regenerate`)
  },

  async toggleAutoRegen(caId, enabled) {
    return apiClient.post(`/crl/${caId}/auto-regen`, { enabled })
  },

  async getOcspStatus() {
    return apiClient.get('/ocsp/status')
  },

  async getOcspStats() {
    return apiClient.get('/ocsp/stats')
  }
}
