/**
 * Background jobs (backup, restore, audit verification): read, list, cancel.
 */
import { apiClient, buildQueryString } from './apiClient'

export const FINAL_JOB_STATES = ['succeeded', 'failed', 'cancelled']

export const isFinalJob = (job) => FINAL_JOB_STATES.includes(job?.state)

// The job a starting route answered with 202, or null when it answered the result itself
export const acceptedJob = (response) => response?.data?.job || null

const jobsService = {
  get: async (id) => apiClient.get(`/system/jobs/${encodeURIComponent(id)}`),

  list: async (params = {}) => apiClient.get(`/system/jobs${buildQueryString(params)}`),

  cancel: async (id) => apiClient.post(`/system/jobs/${encodeURIComponent(id)}/cancel`),
}

export default jobsService
