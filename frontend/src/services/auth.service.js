/**
 * Authentication Service
 * Handles login, logout, and CSRF token management
 */
import { apiClient } from './apiClient'

let pendingLock = null

export const authService = {
  async login(username, password) {
    const response = await apiClient.post('/auth/login', { username, password })
    
    // Store CSRF token from login response
    if (response?.data?.csrf_token) {
      apiClient.setCsrfToken(response.data.csrf_token)
    }
    
    return response
  },

  async logout() {
    const response = await apiClient.post('/auth/logout')
    
    // Clear CSRF token on logout
    apiClient.clearCsrfToken()
    
    return response
  },

  // Locks the session on the server, which keeps it until it is unlocked; `reason` is 'manual' or 'idle'
  lock(reason) {
    const request = (async () => {
      try {
        return await apiClient.post('/auth/lock', { reason })
      } finally {
        apiClient.clearCsrfToken()
      }
    })()
    pendingLock = request.catch(() => {})
    return request
  },

  // Settled once the lock this tab sent has been answered: the lock screen reads the server after it
  whenLocked() {
    return pendingLock || Promise.resolve()
  },

  async getCurrentUser() {
    const response = await apiClient.get('/auth/verify')
    
    // Refresh CSRF token on verify
    if (response?.data?.csrf_token) {
      apiClient.setCsrfToken(response.data.csrf_token)
    }
    
    return response
  },

  async verifySession() {
    const response = await apiClient.get('/auth/verify')
    
    // Refresh CSRF token on verify
    if (response?.data?.csrf_token) {
      apiClient.setCsrfToken(response.data.csrf_token)
    }
    
    return response
  },

  async isEmailConfigured() {
    return apiClient.get('/auth/email-configured')
  },

  async ldapLogin(username, password, providerId) {
    return apiClient.post('/sso/ldap/login', { username, password, provider_id: providerId })
  },

  async getSsoProviders() {
    return apiClient.get('/sso/available')
  },

  async forgotPassword(email) {
    return apiClient.post('/auth/forgot-password', { email })
  },

  async resetPassword(token, password) {
    return apiClient.post('/auth/reset-password', { token, password })
  }
}
