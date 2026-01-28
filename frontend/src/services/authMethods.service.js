/**
 * Multi-Method Authentication Service
 * Supports: Password, mTLS, WebAuthn
 */

import { apiClient } from './apiClient'

class AuthMethodsService {
  /**
   * Detect available authentication methods
   * @param {string} username - Optional username to get user-specific methods
   * @returns {Promise<Object>} Available methods
   */
  async detectMethods(username = null) {
    if (username) {
      // POST with username to get user-specific methods (WebAuthn credentials count, etc.)
      const response = await apiClient.post('/auth/methods', { username })
      return response.data
    } else {
      // GET for global methods only
      const response = await apiClient.get('/auth/methods')
      return response.data
    }
  }

  /**
   * Login with password
   * @param {string} username 
   * @param {string} password 
   * @returns {Promise<Object>} User data + permissions
   */
  async loginPassword(username, password) {
    const response = await apiClient.post('/auth/login/password', { username, password })
    return response.data
  }

  /**
   * Login with mTLS (client certificate)
   * Certificate must already be presented in request
   * @returns {Promise<Object>} User data + permissions
   */
  async loginMTLS() {
    const response = await apiClient.post('/auth/login/mtls', {})
    return response.data
  }

  /**
   * Start WebAuthn authentication
   * @param {string} username
   * @returns {Promise<Object>} Challenge options for navigator.credentials.get()
   */
  async startWebAuthn(username) {
    const response = await apiClient.post('/auth/login/webauthn/start', { username })
    return response.data
  }

  /**
   * Verify WebAuthn response
   * @param {string} username
   * @param {Object} credentialResponse - From navigator.credentials.get()
   * @returns {Promise<Object>} User data + permissions
   */
  async verifyWebAuthn(username, credentialResponse) {
    const response = await apiClient.post('/auth/login/webauthn/verify', {
      username,
      response: credentialResponse
    })
    return response.data
  }

  /**
   * Check if WebAuthn is supported by browser
   * @returns {boolean}
   */
  isWebAuthnSupported() {
    return window.PublicKeyCredential !== undefined && 
           navigator.credentials !== undefined
  }

  /**
   * Perform WebAuthn authentication (start + verify)
   * @param {string} username
   * @returns {Promise<Object>} User data + permissions
   */
  async authenticateWebAuthn(username) {
    if (!this.isWebAuthnSupported()) {
      throw new Error('WebAuthn not supported by this browser')
    }

    // Start authentication (get challenge)
    const { options } = await this.startWebAuthn(username)

    // Convert base64url strings to ArrayBuffers
    const publicKeyOptions = {
      ...options,
      challenge: this.base64urlToBuffer(options.challenge),
      allowCredentials: options.allowCredentials?.map(cred => ({
        ...cred,
        id: this.base64urlToBuffer(cred.id)
      }))
    }

    // Get credential from authenticator
    const credential = await navigator.credentials.get({
      publicKey: publicKeyOptions
    })

    if (!credential) {
      throw new Error('No credential returned from authenticator')
    }

    // Convert credential to format for backend
    const credentialData = {
      id: credential.id,
      rawId: this.bufferToBase64url(credential.rawId),
      type: credential.type,
      response: {
        authenticatorData: this.bufferToBase64url(credential.response.authenticatorData),
        clientDataJSON: this.bufferToBase64url(credential.response.clientDataJSON),
        signature: this.bufferToBase64url(credential.response.signature),
        userHandle: credential.response.userHandle ? 
          this.bufferToBase64url(credential.response.userHandle) : null
      }
    }

    // Verify with backend
    return await this.verifyWebAuthn(username, credentialData)
  }

  /**
   * Convert base64url string to ArrayBuffer
   */
  base64urlToBuffer(base64url) {
    const padding = '='.repeat((4 - base64url.length % 4) % 4)
    const base64 = base64url.replace(/-/g, '+').replace(/_/g, '/') + padding
    const binary = atob(base64)
    const bytes = new Uint8Array(binary.length)
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i)
    }
    return bytes.buffer
  }

  /**
   * Convert ArrayBuffer to base64url string
   */
  bufferToBase64url(buffer) {
    const bytes = new Uint8Array(buffer)
    let binary = ''
    for (let i = 0; i < bytes.length; i++) {
      binary += String.fromCharCode(bytes[i])
    }
    const base64 = btoa(binary)
    return base64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '')
  }
}

export const authMethodsService = new AuthMethodsService()
