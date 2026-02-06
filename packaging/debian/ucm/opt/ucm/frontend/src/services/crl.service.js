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
    return apiClient.post('/crl/generate', { ca_id: caId })
  },

  async download(id) {
    return apiClient.get(`/crl/${id}/download`, {
      responseType: 'blob'
    })
  },

  async getDistributionPoints(caId) {
    return apiClient.get(`/crl/distribution-points/${caId}`)
  },

  async updateDistributionPoint(caId, url) {
    return apiClient.put(`/crl/distribution-points/${caId}`, { url })
  }
}
