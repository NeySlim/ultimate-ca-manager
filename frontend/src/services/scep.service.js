/**
 * SCEP (Simple Certificate Enrollment Protocol) Service
 */
import { apiClient } from './apiClient'

export const scepService = {
  // Config
  async getConfig() {
    return apiClient.get('/scep/config')
  },

  async updateConfig(data) {
    return apiClient.patch('/scep/config', data)
  },

  async getStats() {
    return apiClient.get('/scep/stats')
  },

  // Requests (enrollments)
  async getRequests(filters = {}) {
    const params = new URLSearchParams()
    if (filters.status) params.append('status', filters.status)
    if (filters.page) params.append('page', filters.page)
    
    const query = params.toString() ? `?${params.toString()}` : ''
    return apiClient.get(`/scep/requests${query}`)
  },

  async approveRequest(id) {
    return apiClient.post(`/scep/${id}/approve`)
  },

  async rejectRequest(id, reason) {
    return apiClient.post(`/scep/${id}/reject`, { reason })
  },

  // Legacy methods for compatibility
  async getEnrollments(filters = {}) {
    return this.getRequests(filters)
  },

  async approveEnrollment(id) {
    return this.approveRequest(id)
  },

  async rejectEnrollment(id, reason) {
    return this.rejectRequest(id, reason)
  },

  async getChallenge(caId) {
    return apiClient.get(`/scep/challenge/${caId}`)
  },

  async regenerateChallenge(caId) {
    return apiClient.post(`/scep/challenge/${caId}/regenerate`)
  }
}
