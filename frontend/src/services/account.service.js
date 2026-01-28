/**
 * Account Service - User profile management
 */
import { apiClient } from './apiClient'

export const accountService = {
  async getProfile() {
    return apiClient.get('/account/profile')
  },

  async updateProfile(data) {
    return apiClient.put('/account/profile', data)
  },

  async changePassword(currentPassword, newPassword) {
    return apiClient.post('/account/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    })
  },

  async getApiKeys() {
    return apiClient.get('/account/apikeys')
  },

  async createApiKey(name, expiresIn) {
    return apiClient.post('/account/apikeys', {
      name,
      expires_in: expiresIn,
    })
  },

  async revokeApiKey(keyId) {
    return apiClient.delete(`/account/apikeys/${keyId}`)
  },

  async getSessions() {
    return apiClient.get('/account/sessions')
  },

  async revokeSession(sessionId) {
    return apiClient.delete(`/account/sessions/${sessionId}`)
  },

  async get2FAStatus() {
    return apiClient.get('/account/2fa')
  },

  async enable2FA() {
    return apiClient.post('/account/2fa/enable')
  },

  async disable2FA() {
    return apiClient.post('/account/2fa/disable')
  },

  async verify2FA(code) {
    return apiClient.post('/account/2fa/verify', { code })
  }
}
