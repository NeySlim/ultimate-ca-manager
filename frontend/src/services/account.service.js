/**
 * Account Service - User profile management
 */
import { apiClient, buildQueryString } from './apiClient'

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

  // Preferences (issue #73) — UI settings persisted server-side
  async getPreferences() {
    return apiClient.get('/account/preferences')
  },

  async updatePreferences(prefs) {
    return apiClient.put('/account/preferences', prefs)
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

  /**
   * Run the browser registration ceremony and store the new key
   * @param {string} name - Label shown in the key list
   */
  async registerWebAuthnKey(name) {
    const response = await this.startWebAuthnRegistration()
    const options = response.data
    
    const base64urlToUint8Array = (base64url) => {
      let base64 = base64url.replace(/-/g, '+').replace(/_/g, '/')
      while (base64.length % 4) base64 += '='
      return Uint8Array.from(atob(base64), c => c.charCodeAt(0))
    }
    
    const stringToUint8Array = (str) => new TextEncoder().encode(str)
    
    const publicKeyOptions = {
      challenge: base64urlToUint8Array(options.challenge),
      rp: options.rp,
      user: {
        id: stringToUint8Array(String(options.user.id)),
        name: options.user.name,
        displayName: options.user.displayName
      },
      pubKeyCredParams: options.pubKeyCredParams,
      timeout: options.timeout || 60000,
      authenticatorSelection: options.authenticatorSelection,
      attestation: options.attestation || 'none'
    }
    
    if (options.excludeCredentials?.length > 0) {
      publicKeyOptions.excludeCredentials = options.excludeCredentials.map(c => ({
        type: c.type,
        id: base64urlToUint8Array(c.id),
        transports: c.transports
      }))
    }
    
    const credential = await navigator.credentials.create({ publicKey: publicKeyOptions })
    
    const uint8ArrayToBase64url = (arr) => {
      const str = String.fromCharCode.apply(null, new Uint8Array(arr))
      return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '')
    }
    
    const attestationResponse = {
      id: credential.id,
      rawId: uint8ArrayToBase64url(credential.rawId),
      type: credential.type,
      response: {
        clientDataJSON: uint8ArrayToBase64url(credential.response.clientDataJSON),
        attestationObject: uint8ArrayToBase64url(credential.response.attestationObject)
      }
    }
    
    return this.completeWebAuthnRegistration({
      credential: attestationResponse,
      name
    })
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

  async downloadMTLSCertificate(certId, {
    format = 'pem', password, includeChain = true, includeRoot = false, legacy = false,
  } = {}) {
    const fmt = (format === 'p12' ? 'pkcs12' : format).toLowerCase()
    if (fmt === 'pkcs12') {
      return apiClient.post(
        `/mtls/certificates/${certId}/download`,
          {
            format: 'pkcs12',
            password,
            include_chain: includeChain,
            include_root: includeRoot,
            legacy,
          },
        { responseType: 'blob' },
      )
    }
    return apiClient.get(`/mtls/certificates/${certId}/download${buildQueryString({
      format: fmt,
      include_chain: includeChain,
      include_root: includeRoot,
    })}`, {
      responseType: 'blob',
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
