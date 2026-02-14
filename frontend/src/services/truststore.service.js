/**
 * TrustStore Service
 */
import { apiClient } from './apiClient'

export const truststoreService = {
  async getAll() {
    return apiClient.get('/truststore')
  },

  async getStats() {
    return apiClient.get('/truststore/stats')
  },

  async getById(id) {
    return apiClient.get(`/truststore/${id}`)
  },

  async add(data) {
    return apiClient.post('/truststore', data)
  },

  async importFile(file, { name, purpose, description, notes } = {}) {
    const formData = new FormData()
    formData.append('file', file)
    if (name) formData.append('name', name)
    if (purpose) formData.append('purpose', purpose)
    if (description) formData.append('description', description)
    if (notes) formData.append('notes', notes)
    return apiClient.upload('/truststore/import', formData)
  },

  async syncFromSystem(limit = 50) {
    return apiClient.post('/truststore/sync', { source: 'system', limit })
  },

  async remove(id) {
    return apiClient.delete(`/truststore/${id}`)
  },

  async export(id) {
    return apiClient.get(`/truststore/${id}/export`, {
      responseType: 'blob'
    })
  },

  // Alias for backwards compatibility
  async delete(id) {
    return this.remove(id)
  },

  async exportBundle(format = 'pem', purpose = 'all') {
    return apiClient.get(`/truststore/export?format=${format}&purpose=${purpose}`, {
      responseType: 'blob'
    })
  },

  async getExpiring(days = 90) {
    return apiClient.get(`/truststore/expiring?days=${days}`)
  }
}
