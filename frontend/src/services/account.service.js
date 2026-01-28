/**
 * Account Service - User profile management
 */
import { apiClient } from './apiClient'

export const accountService = {
  // Profile
  async getProfile() {
    return apiClient.get('/api/v2/account/profile')
  },

  async updateProfile(data) {
    return apiClient.patch('/api/v2/account/profile', data)
  },

  async changePassword(data) {
    return apiClient.post('/api/v2/account/password', data)
  },

  // API Keys
  async getApiKeys() {
    return apiClient.get('/api/v2/account/apikeys')
  },

  async createApiKey(data) {
    return apiClient.post('/api/v2/account/apikeys', data)
  },

  async deleteApiKey(keyId) {
    return apiClient.delete(`/api/v2/account/apikeys/${keyId}`)
  },

  // Sessions
  async getSessions() {
    return apiClient.get('/api/v2/account/sessions')
  },

  async revokeSession(sessionId) {
    return apiClient.delete(`/api/v2/account/sessions/${sessionId}`)
  },

  // 2FA TOTP
  async enable2FA() {
    return apiClient.post('/api/v2/account/2fa/enable')
  },

  async confirm2FA(code) {
    return apiClient.post('/api/v2/account/2fa/confirm', { code })
  },

  async disable2FA(code) {
    return apiClient.post('/api/v2/account/2fa/disable', { code })
  },

  // WebAuthn / FIDO2
  async getWebAuthnCredentials() {
    return apiClient.get('/api/v2/account/webauthn/credentials')
  },

  async startWebAuthnRegistration() {
    return apiClient.post('/api/v2/account/webauthn/register/options')
  },

  async completeWebAuthnRegistration(credential, name) {
    return apiClient.post('/api/v2/account/webauthn/register/verify', { credential, name })
  },

  async deleteWebAuthnCredential(credentialId) {
    return apiClient.delete(`/api/v2/account/webauthn/credentials/${credentialId}`)
  },

  // mTLS Certificates
  async getMTLSCertificates() {
    return apiClient.get('/api/v2/account/mtls/certificates')
  },

  async createMTLSCertificate(data) {
    return apiClient.post('/api/v2/account/mtls/certificates/create', data)
  },

  async enrollMTLSCertificate(certificate, name) {
    return apiClient.post('/api/v2/account/mtls/certificates/enroll', { certificate, name })
  },

  async deleteMTLSCertificate(certId) {
    return apiClient.delete(`/api/v2/account/mtls/certificates/${certId}`)
  },

  async downloadMTLSCertificate(certId) {
    return apiClient.get(`/api/v2/account/mtls/certificates/${certId}/download`, {
      responseType: 'blob'
    })
  }
}
