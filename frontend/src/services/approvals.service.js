/**
 * Approval Requests Service
 */
import { apiClient } from './apiClient'

export const approvalsService = {
  async list(status = 'pending') {
    const query = status !== 'all' ? `?status=${status}` : '?status=all'
    return apiClient.get(`/approvals${query}`)
  },

  async getById(id) {
    return apiClient.get(`/approvals/${id}`)
  },

  async approve(id, comment) {
    return apiClient.post(`/approvals/${id}/approve`, { comment })
  },

  async reject(id, comment) {
    return apiClient.post(`/approvals/${id}/reject`, { comment })
  },

  async getStats() {
    return apiClient.get('/approvals/stats')
  },
}
