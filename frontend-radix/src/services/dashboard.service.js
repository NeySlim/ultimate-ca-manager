/**
 * Dashboard Service
 */
import { apiClient } from './apiClient'

export const dashboardService = {
  async getStats() {
    return apiClient.get('/dashboard/stats')
  },

  async getRecentCAs(limit = 5) {
    return apiClient.get(`/dashboard/recent-cas?limit=${limit}`)
  },

  async getExpiringCerts(days = 30) {
    return apiClient.get(`/dashboard/expiring-certs?days=${days}`)
  },

  async getActivityLog(limit = 20, offset = 0) {
    return apiClient.get(`/dashboard/activity?limit=${limit}&offset=${offset}`)
  },

  async getSystemStatus() {
    return apiClient.get('/dashboard/system-status')
  }
}
