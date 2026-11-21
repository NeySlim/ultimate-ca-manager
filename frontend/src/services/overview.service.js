/**
 * Overview aggregates (GET /dashboard/queue, health, compliance, issuance).
 */
import { apiClient, buildQueryString } from './apiClient'

export const overviewService = {
  getQueue(limit = 100) {
    return apiClient.get(`/dashboard/queue${buildQueryString({ limit })}`)
  },
  getHealth(days = 7) {
    return apiClient.get(`/dashboard/health${buildQueryString({ days })}`)
  },
  getCompliance() {
    return apiClient.get('/dashboard/compliance')
  },
  getIssuance(days = 30) {
    return apiClient.get(`/dashboard/issuance${buildQueryString({ days })}`)
  },
}
