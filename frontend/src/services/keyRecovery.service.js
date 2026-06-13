/**
 * Key Recovery (escrow) Service — dual-control private-key recovery workflow.
 */
import { apiClient } from './apiClient'

export const keyRecoveryService = {
  // Open a recovery request for a certificate's archived private key.
  async request(certId, reason) {
    return apiClient.post(`/certificates/${certId}/key-recovery`, { reason })
  },

  async list(status) {
    const qs = status ? `?status=${encodeURIComponent(status)}` : ''
    return apiClient.get(`/key-recovery${qs}`)
  },

  async approve(id, note) {
    return apiClient.post(`/key-recovery/${id}/approve`, { note })
  },

  async reject(id, note) {
    return apiClient.post(`/key-recovery/${id}/reject`, { note })
  },

  // Returns a PKCS#12 blob (the recovered key). Once, after approval.
  async recover(id, password) {
    return apiClient.post(`/key-recovery/${id}/recover`, { password }, { responseType: 'blob' })
  },
}
