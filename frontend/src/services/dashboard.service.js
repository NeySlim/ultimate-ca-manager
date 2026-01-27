/**
 * Dashboard Service
 */
import { apiClient } from './apiClient'

export const dashboardService = {
  async getStats() {
    return apiClient.get('/dashboard/stats')
  },

  async getRecentCAs(limit = 5) {
    // TODO: Backend endpoint not implemented yet
    return { data: [] }
  },

  async getExpiringCerts(days = 30) {
    // TODO: Backend endpoint not implemented yet  
    return { data: [] }
  },

  async getActivityLog(limit = 20, offset = 0) {
    return apiClient.get(`/dashboard/activity?limit=${limit}&offset=${offset}`)
  },

  async getSystemStatus() {
    // TODO: Backend endpoint not implemented yet
    return { data: {} }
  }
}
