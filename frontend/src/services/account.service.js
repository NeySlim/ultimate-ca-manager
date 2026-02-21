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
    return apiClient.get('/webauthn/credentials')
  },

  async startWebAuthnRegistration() {
    return apiClient.post('/webauthn/register/options')
  },

  async completeWebAuthnRegistration(data) {
    // data should contain { credential, name }
    return apiClient.post('/webauthn/register/verify', data)
  },

  async deleteWebAuthnCredential(credentialId) {
    return apiClient.delete(`/webauthn/credentials/${credentialId}`)
  },

  // mTLS Certificates
  async getMTLSCertificates() {
    return apiClient.get('/mtls/certificates')
  },

  async createMTLSCertificate(data) {
    return apiClient.post('/mtls/certificates', data)
  },

  async enrollMTLSCertificate(certificate, name) {
    return apiClient.post('/mtls/certificates', { certificate, name })
  },

  async deleteMTLSCertificate(certId) {
    return apiClient.delete(`/mtls/certificates/${certId}`)
  },

  async downloadMTLSCertificate(certId) {
    return apiClient.get(`/mtls/certificates/${certId}/download`, {
      responseType: 'blob'
    })
  },

  async importMTLSCertificate(pem, name) {
    return apiClient.post('/mtls/enroll-import', { pem, name })
  },

  async getAvailableMTLSCertificates() {
    return apiClient.get('/mtls/available-certificates')
  },

  async assignMTLSCertificate(certId, name) {
    return apiClient.post('/mtls/assign', { cert_id: certId, name })
  }
}
