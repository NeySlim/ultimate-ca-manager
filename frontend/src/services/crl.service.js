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

  async getDeltaCRL(caId) {
    return apiClient.get(`/crl/${caId}/delta`)
  },

  async generateDelta(caId) {
    return apiClient.post(`/crl/${caId}/delta/regenerate`)
  },

  async configureDelta(caId, config) {
    return apiClient.post(`/crl/${caId}/delta-config`, config)
  },

  async getCrlConfig(caId) {
    return apiClient.get(`/crl/${caId}/config`)
  },

  async configureCrl(caId, config) {
    return apiClient.post(`/crl/${caId}/config`, config)
  },

  async getOcspStatus() {
    return apiClient.get('/ocsp/status')
  },

  async getOcspStats() {
    return apiClient.get('/ocsp/stats')
  },

  async getOcspResponder(caId) {
    return apiClient.get(`/cas/${caId}/ocsp-responder`)
  },

  async setOcspResponder(caId, certificateId) {
    return apiClient.post(`/cas/${caId}/ocsp-responder`, { certificate_id: certificateId })
  },

  async removeOcspResponder(caId) {
    return apiClient.delete(`/cas/${caId}/ocsp-responder`)
  },

  async getEligibleOcspResponders(caId) {
    return apiClient.get(`/cas/${caId}/eligible-ocsp-responders`)
  }
}
