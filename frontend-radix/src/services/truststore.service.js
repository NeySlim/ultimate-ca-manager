/**
 * TrustStore Service
 */
import { apiClient } from './apiClient'

export const truststoreService = {
  async getAll() {
    return apiClient.get('/truststore')
  },

  async getById(id) {
    return apiClient.get(`/truststore/${id}`)
  },

  async add(data) {
    return apiClient.post('/truststore', data)
  },

  async import(pemData) {
    return apiClient.post('/truststore/import', { pem: pemData })
  },

  async remove(id) {
    return apiClient.delete(`/truststore/${id}`)
  },

  async export(id) {
    return apiClient.get(`/truststore/${id}/export`, {
      responseType: 'blob'
    })
  },

  async verify(certId, trustedCaId) {
    return apiClient.post('/truststore/verify', {
      certificate_id: certId,
      trusted_ca_id: trustedCaId,
    })
  }
}
