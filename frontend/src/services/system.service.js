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

  async backup(password) {
    // Returns JSON with backup info (file saved on server)
    return apiClient.post('/system/backup', { password })
  },

  async downloadBackup(filename) {
    // Download saved backup file
    const response = await fetch(`/api/v2/system/backup/${encodeURIComponent(filename)}/download`, {
      credentials: 'include'
    })
    if (!response.ok) {
      throw new Error('Failed to download backup')
    }
    return response.blob()
  },

  async deleteBackup(filename) {
    return apiClient.delete(`/system/backup/${encodeURIComponent(filename)}`)
  },

  async restore(file, password) {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('password', password)
    
    return fetch('/api/v2/system/restore', {
      method: 'POST',
      body: formData,
      credentials: 'include'
    }).then(async res => {
      const data = await res.json()
      if (!res.ok) throw new Error(data.message || data.error || 'Restore failed')
      return data
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
