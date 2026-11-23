/**
 * SCEP (Simple Certificate Enrollment Protocol) Service
 */
import { apiClient, buildQueryString } from './apiClient'

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
    return apiClient.get(`/scep/requests${buildQueryString(filters)}`)
  },

  async getRequest(id) {
    return apiClient.get(`/scep/requests/${id}`)
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

  // The state of every CA's challenge, never the secret: no audited read
  async getChallengeStates() {
    return apiClient.get('/scep/challenges')
  },

  // One audited read of a CA's secret, on demand only
  async getChallenge(caId) {
    return apiClient.get(`/scep/challenge/${caId}`)
  },

  async regenerateChallenge(caId) {
    return apiClient.post(`/scep/challenge/${caId}/regenerate`)
  },

  // Profiles (named endpoints, issue #228)
  async getProfiles() {
    return apiClient.get('/scep/profiles')
  },

  async createProfile(data) {
    return apiClient.post('/scep/profiles', data)
  },

  async updateProfile(id, data) {
    return apiClient.patch(`/scep/profiles/${id}`, data)
  },

  async deleteProfile(id) {
    return apiClient.delete(`/scep/profiles/${id}`)
  },

  async regenerateProfileChallenge(id) {
    return apiClient.post(`/scep/profiles/${id}/challenge/regenerate`)
  },

  async testIntuneConnection(data) {
    return apiClient.post('/scep/profiles/test-intune-connection', data)
  },

  // Intune app registrations, defined once and picked per profile (#358)
  async getIntuneApps() {
    return apiClient.get('/scep/intune-apps')
  },

  async createIntuneApp(data) {
    return apiClient.post('/scep/intune-apps', data)
  },

  async updateIntuneApp(id, data) {
    return apiClient.patch(`/scep/intune-apps/${id}`, data)
  },

  async deleteIntuneApp(id) {
    return apiClient.delete(`/scep/intune-apps/${id}`)
  },

  async testIntuneApp(data) {
    return apiClient.post('/scep/intune-apps/test', data)
  }
}
