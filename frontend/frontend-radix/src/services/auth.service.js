/**
 * Authentication Service
 */
import { apiClient } from './apiClient'

export const authService = {
  async login(username, password) {
    return apiClient.post('/auth/login', { username, password })
  },

  async logout() {
    return apiClient.post('/auth/logout')
  },

  async getCurrentUser() {
    return apiClient.get('/auth/verify')
  },

  async refreshToken() {
    return apiClient.post('/auth/refresh')
  },

  async verifySession() {
    return apiClient.get('/auth/verify')
  }
}
