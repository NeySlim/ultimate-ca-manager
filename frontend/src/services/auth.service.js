/**
 * Authentication Service
 * Handles login, logout, and CSRF token management
 */
import { apiClient } from './apiClient'

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
  }
}
