/**
 * Settings Service
 */
import { apiClient } from './apiClient'

export const settingsService = {
  async getAll() {
    // Get all settings by fetching general settings
    return apiClient.get('/settings/general')
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

  async testEmail(email) {
    return apiClient.post('/settings/email/test', { email })
  },

  async getSmtpOAuthAuthorizeUrl(redirectUri) {
    return apiClient.post('/settings/email/oauth/authorize-url', redirectUri ? { redirect_uri: redirectUri } : {})
  },

  async revokeSmtpOAuth() {
    return apiClient.post('/settings/email/oauth/revoke', {})
  },

  async getSmtpOAuthProviders() {
    return apiClient.get('/settings/email/oauth/providers')
  },

  // Expiry Alerts
  async getExpiryAlerts() {
    return apiClient.get('/system/alerts/expiry')
  },

  async updateExpiryAlerts(data) {
    return apiClient.put('/system/alerts/expiry', data)
  },

  async checkExpiryAlerts() {
    return apiClient.post('/system/alerts/expiry/check')
  },

  // Webhooks
  async getWebhooks() {
    return apiClient.get('/webhooks')
  },

  async createWebhook(data) {
    return apiClient.post('/webhooks', data)
  },

  async updateWebhook(id, data) {
    return apiClient.put(`/webhooks/${id}`, data)
  },

  async deleteWebhook(id) {
    return apiClient.delete(`/webhooks/${id}`)
  },

  async toggleWebhook(id) {
    return apiClient.post(`/webhooks/${id}/toggle`)
  },

  async testWebhook(id) {
    return apiClient.post(`/webhooks/${id}/test`)
  },

  // Encryption
  async getEncryptionStatus() {
    return apiClient.get('/system/security/encryption-status')
  },

  async enableEncryption() {
    return apiClient.post('/system/security/enable-encryption')
  },

  async disableEncryption() {
    return apiClient.post('/system/security/disable-encryption')
  },

  // Security Anomalies
  async getSecurityAnomalies() {
    return apiClient.get('/system/security/anomalies')
  },

  // Syslog
  async getSyslogConfig() {
    return apiClient.get('/system/audit/syslog')
  },

  async updateSyslogConfig(data) {
    return apiClient.put('/system/audit/syslog', data)
  },

  async testSyslog() {
    return apiClient.post('/system/audit/syslog/test')
  },

  // Certificate Transparency
  async getCTSettings() {
    return apiClient.get('/settings/ct')
  },

  async updateCTSettings(data) {
    return apiClient.patch('/settings/ct', data)
  }
}
