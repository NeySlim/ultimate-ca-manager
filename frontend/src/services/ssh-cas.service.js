/**
 * SSH Certificate Authorities Service
 */
import { apiClient, createCRUDService } from './apiClient'

export const sshCasService = {
  ...createCRUDService('ssh/cas'),

  async getPublicKey(id) {
    return apiClient.get(`/ssh/cas/${id}/public-key`)
  },

  async getKRL(id) {
    return apiClient.get(`/ssh/cas/${id}/krl`, { responseType: 'blob' })
  },

  async getSetupScript(id, platform = 'unix') {
    const qs = platform && platform !== 'unix' ? `?platform=${encodeURIComponent(platform)}` : ''
    return apiClient.get(`/ssh/cas/${id}/setup-script${qs}`, { responseType: 'blob' })
  },

  async importCA(data) {
    return apiClient.post('/ssh/cas/import', data)
  },
}
