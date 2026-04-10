/**
 * SSH Certificates Service
 */
import { apiClient, buildQueryString } from './apiClient'

export const sshCertificatesService = {
  async getAll(params) {
    return apiClient.get(`/ssh/certificates${buildQueryString(params)}`)
  },

  async getById(id) {
    return apiClient.get(`/ssh/certificates/${id}`)
  },

  async sign(data) {
    return apiClient.post('/ssh/certificates', data)
  },

  async generate(data) {
    return apiClient.post('/ssh/certificates/generate', data)
  },

  async revoke(id, reason) {
    return apiClient.post(`/ssh/certificates/${id}/revoke`, { reason })
  },

  async delete(id) {
    return apiClient.delete(`/ssh/certificates/${id}`)
  },

  async export(id) {
    return apiClient.get(`/ssh/certificates/${id}/export`)
  },

  async verify(certificate) {
    return apiClient.post('/ssh/certificates/verify', { certificate })
  },

  async getStats() {
    return apiClient.get('/ssh/stats')
  },

  async importCertificate(data) {
    return apiClient.post('/ssh/certificates/import', data)
  },
}
