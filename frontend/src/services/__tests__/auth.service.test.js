/**
 * Auth Service Tests
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { authService } from '../auth.service'
import { apiClient } from '../apiClient'

// Mock apiClient
vi.mock('../apiClient', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn()
  }
}))

describe('Auth Service', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('login', () => {
    it('calls POST /auth/login with credentials', async () => {
      apiClient.post.mockResolvedValue({ data: { user: { id: 1 } } })
      
      await authService.login('admin', 'password123')
      
      expect(apiClient.post).toHaveBeenCalledWith('/auth/login', {
        username: 'admin',
        password: 'password123'
      })
    })

    it('returns user data on success', async () => {
      apiClient.post.mockResolvedValue({ data: { user: { id: 1, username: 'admin' } } })
      
      const result = await authService.login('admin', 'password123')
      
      expect(result.data.user.username).toBe('admin')
    })
  })

  describe('logout', () => {
    it('calls POST /auth/logout', async () => {
      apiClient.post.mockResolvedValue({ message: 'Logged out' })
      
      await authService.logout()
      
      expect(apiClient.post).toHaveBeenCalledWith('/auth/logout')
    })
  })

  describe('getCurrentUser', () => {
    it('calls GET /auth/verify', async () => {
      apiClient.get.mockResolvedValue({ data: { user: { id: 1 } } })
      
      await authService.getCurrentUser()
      
      expect(apiClient.get).toHaveBeenCalledWith('/auth/verify')
    })
  })

  describe('refreshToken', () => {
    it('calls POST /auth/refresh', async () => {
      apiClient.post.mockResolvedValue({ data: { token: 'new-token' } })
      
      await authService.refreshToken()
      
      expect(apiClient.post).toHaveBeenCalledWith('/auth/refresh')
    })
  })

  describe('verifySession', () => {
    it('calls GET /auth/verify', async () => {
      apiClient.get.mockResolvedValue({ data: { valid: true } })
      
      await authService.verifySession()
      
      expect(apiClient.get).toHaveBeenCalledWith('/auth/verify')
    })
  })
})
