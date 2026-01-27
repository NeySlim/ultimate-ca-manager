/**
 * Dashboard Service
 */
import { apiClient } from './apiClient'

export const dashboardService = {
  async getStats() {
    return apiClient.get('/dashboard/stats')
  },

  async getRecentCAs(limit = 5) {
    // Use the CAs endpoint with pagination
    return apiClient.get(`/cas?page=1&per_page=${limit}`)
  },

  async getExpiringCerts(days = 30) {
    // Use the certificates endpoint with expiring filter
    return apiClient.get(`/certificates?status=expiring&per_page=10`)
  },

  async getActivityLog(limit = 20, offset = 0) {
    return apiClient.get(`/dashboard/activity?limit=${limit}&offset=${offset}`)
  },

  async getSystemStatus() {
    // TODO: Backend endpoint not implemented yet
    return { data: {} }
  }
}
