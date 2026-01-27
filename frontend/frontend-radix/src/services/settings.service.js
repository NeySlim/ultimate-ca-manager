/**
 * Settings Service
 */
import { apiClient } from './apiClient'

export const settingsService = {
  async getAll() {
    // Get all settings by fetching general settings
    return apiClient.get('/settings/general')
  },

  async get(key) {
    return apiClient.get(`/settings/${key}`)
  },

  async update(key, value) {
    return apiClient.patch(`/settings/${key}`, { value })
  },

  async updateBulk(settings) {
    return apiClient.patch('/settings/general', settings)
  },

  async getEmailSettings() {
    return apiClient.get('/settings/email')
  },

  async updateEmailSettings(data) {
    return apiClient.patch('/settings/email', data)
  },

  async testEmail(to) {
    return apiClient.post('/settings/email/test', { to })
  }
}
