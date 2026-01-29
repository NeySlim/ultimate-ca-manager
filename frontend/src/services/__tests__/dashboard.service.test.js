/**
 * Dashboard Service Tests
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { dashboardService } from '../dashboard.service'
import { apiClient } from '../apiClient'

vi.mock('../apiClient', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn()
  }
}))

describe('Dashboard Service', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('getStats', () => {
    it('calls GET /dashboard/stats', async () => {
      apiClient.get.mockResolvedValue({ 
        data: { total_cas: 5, total_certs: 100 } 
      })
      
      await dashboardService.getStats()
      
      expect(apiClient.get).toHaveBeenCalledWith('/dashboard/stats')
    })
  })

  describe('getRecentCAs', () => {
    it('calls GET /cas with default limit', async () => {
      apiClient.get.mockResolvedValue({ data: [] })
      
      await dashboardService.getRecentCAs()
      
      expect(apiClient.get).toHaveBeenCalledWith('/cas?page=1&per_page=5')
    })

    it('calls GET /cas with custom limit', async () => {
      apiClient.get.mockResolvedValue({ data: [] })
      
      await dashboardService.getRecentCAs(10)
      
      expect(apiClient.get).toHaveBeenCalledWith('/cas?page=1&per_page=10')
    })
  })

  describe('getExpiringCerts', () => {
    it('calls GET /certificates with expiring filter', async () => {
      apiClient.get.mockResolvedValue({ data: [] })
      
      await dashboardService.getExpiringCerts()
      
      expect(apiClient.get).toHaveBeenCalledWith('/certificates?status=expiring&per_page=10')
    })
  })

  describe('getActivityLog', () => {
    it('calls GET /dashboard/activity with defaults', async () => {
      apiClient.get.mockResolvedValue({ data: [] })
      
      await dashboardService.getActivityLog()
      
      expect(apiClient.get).toHaveBeenCalledWith('/dashboard/activity?limit=20&offset=0')
    })

    it('calls GET /dashboard/activity with custom params', async () => {
      apiClient.get.mockResolvedValue({ data: [] })
      
      await dashboardService.getActivityLog(50, 10)
      
      expect(apiClient.get).toHaveBeenCalledWith('/dashboard/activity?limit=50&offset=10')
    })
  })

  describe('getSystemStatus', () => {
    it('calls GET /dashboard/system-status', async () => {
      apiClient.get.mockResolvedValue({ 
        data: { status: 'healthy', uptime: 3600 } 
      })
      
      await dashboardService.getSystemStatus()
      
      expect(apiClient.get).toHaveBeenCalledWith('/dashboard/system-status')
    })
  })
})
