/**
 * System Service
 */
import { apiClient } from './apiClient'

export const systemService = {
  async getHealth() {
    return apiClient.get('/system/health')
  },

  async getVersion() {
    return apiClient.get('/system/version')
  },

  async getInfo() {
    return apiClient.get('/system/info')
  },

  // Backup Management
  async listBackups() {
    return apiClient.get('/system/backups')
  },

  async backup() {
    return apiClient.post('/system/backup', {}, {
      responseType: 'blob'
    })
  },

  async downloadBackup(filename) {
    return apiClient.get(`/system/backups/${filename}`, {
      responseType: 'blob'
    })
  },

  async deleteBackup(filename) {
    return apiClient.delete(`/system/backups/${filename}`)
  },

  async restore(file) {
    const formData = new FormData()
    formData.append('file', file)
    
    return apiClient.request('/system/restore', {
      method: 'POST',
      body: formData,
      headers: {
        // Don't set Content-Type, let browser set it with boundary
      }
    })
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
  }
}
