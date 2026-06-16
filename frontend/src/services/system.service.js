/**
 * System Service
 */
import { apiClient, buildQueryString } from './apiClient'

export const systemService = {
  // Version/Updates
  async getVersion() {
    return apiClient.get('/system/updates/version')
  },

  // Backup Management
  async listBackups(params = {}) {
    return apiClient.get(`/system/backups${buildQueryString(params)}`)
  },

  async bulkDeleteBackups(filenames) {
    return apiClient.post('/system/backups/bulk-delete', { filenames })
  },

  async runBackupRetention() {
    return apiClient.post('/system/backups/run-retention')
  },

  async backup(password) {
    // Returns JSON with backup info (file saved on server)
    return apiClient.post('/system/backup', { password })
  },

  async downloadBackup(filename) {
    // Download saved backup file
    return apiClient.download(`/system/backup/${encodeURIComponent(filename)}/download`)
  },

  async deleteBackup(filename) {
    return apiClient.delete(`/system/backup/${encodeURIComponent(filename)}`)
  },

  async restore(file, password) {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('password', password)
    
    return apiClient.upload('/system/restore', formData)
  },

  // Database Management
  async getDatabaseStats() {
    return apiClient.get('/system/database/stats')
  },

  async optimizeDatabase() {
    return apiClient.post('/system/database/optimize')
  },

  async integrityCheck() {
    return apiClient.post('/system/database/integrity-check')
  },

  async exportDatabase() {
    return apiClient.get('/system/database/export', {
      responseType: 'blob'
    })
  },

  async resetDatabase() {
    return apiClient.post('/system/database/reset')
  },

  // HTTPS Certificate Management
  async getHttpsCertInfo() {
    return apiClient.get('/system/https/cert-info')
  },

  async regenerateHttpsCert(data) {
    return apiClient.post('/system/https/regenerate', data)
  },

  async applyHttpsCert(certData) {
    return apiClient.post('/system/https/apply', certData)
  },

  // Logs
  async getLogs(limit = 100) {
    return apiClient.get(`/system/logs?limit=${limit}`)
  },

  // Service Management
  async getServiceStatus() {
    return apiClient.get('/system/service/status')
  },

  async restartService() {
    return apiClient.post('/system/service/restart')
  },

  // Scheduler
  async getSchedulerTasks() {
    return apiClient.get('/system/scheduler')
  },

  async runSchedulerTask(name) {
    return apiClient.post(`/system/scheduler/${encodeURIComponent(name)}/run`)
  }
}
