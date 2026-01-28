/**
 * Account Service - User profile management
 */
import { apiClient } from './apiClient'

export const accountService = {
  // Profile
  async getProfile() {
    return apiClient.get('/account/profile')
  },

  async updateProfile(data) {
    return apiClient.patch('/account/profile', data)
  },

  async changePassword(data) {
    return apiClient.post('/account/password', data)
  },

  // API Keys
  async getApiKeys() {
    return apiClient.get('/account/apikeys')
  },

  async createApiKey(data) {
    return apiClient.post('/account/apikeys', data)
  },

  async deleteApiKey(keyId) {
    return apiClient.delete(`/account/apikeys/${keyId}`)
  },

  // Sessions
  async getSessions() {
    return apiClient.get('/account/sessions')
  },

  async revokeSession(sessionId) {
    return apiClient.delete(`/account/sessions/${sessionId}`)
  },

  // 2FA TOTP
  async enable2FA() {
    return apiClient.post('/account/2fa/enable')
  },

  async confirm2FA(code) {
    return apiClient.post('/account/2fa/confirm', { code })
  },

  async disable2FA(code) {
    return apiClient.post('/account/2fa/disable', { code })
  },

  // WebAuthn / FIDO2
  async getWebAuthnCredentials() {
    return apiClient.get('/account/webauthn/credentials')
  },

  async startWebAuthnRegistration() {
    return apiClient.post('/account/webauthn/register/options')
  },

  async completeWebAuthnRegistration(credential, name) {
    return apiClient.post('/account/webauthn/register/verify', { credential, name })
  },

  async deleteWebAuthnCredential(credentialId) {
    return apiClient.delete(`/account/webauthn/credentials/${credentialId}`)
  },

  // mTLS Certificates
  async getMTLSCertificates() {
    return apiClient.get('/account/mtls/certificates')
  },

  async createMTLSCertificate(data) {
    return apiClient.post('/account/mtls/certificates/create', data)
  },

  async enrollMTLSCertificate(certificate, name) {
    return apiClient.post('/account/mtls/certificates/enroll', { certificate, name })
  },

  async deleteMTLSCertificate(certId) {
    return apiClient.delete(`/account/mtls/certificates/${certId}`)
  },

  async downloadMTLSCertificate(certId) {
    return apiClient.get(`/account/mtls/certificates/${certId}/download`, {
      responseType: 'blob'
    })
  }
}
