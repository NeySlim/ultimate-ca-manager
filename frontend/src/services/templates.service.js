/**
 * Templates Service
 */
import { apiClient, createCRUDService } from './apiClient'

export const templatesService = {
  ...createCRUDService('templates'),

  async duplicate(id) {
    return apiClient.post(`/templates/${id}/duplicate`)
  },

  async export(id) {
    return apiClient.get(`/templates/${id}/export`, {
      responseType: 'blob'
    })
  },

  async exportAll() {
    return apiClient.get('/templates/export', {
      responseType: 'blob'
    })
  },

  async import(formData) {
    return apiClient.upload('/templates/import', formData)
  },

  async bulkDelete(ids) {
    return apiClient.post('/templates/bulk/delete', { ids })
  },

  // CA-Template pinning methods
  async getForCA(caId) {
    return apiClient.get(`/templates?ca_id=${caId}`)
  },

  async pinToCA(caId, templateId) {
    return apiClient.post(`/cas/${caId}/templates/${templateId}/pin`)
  },

  async unpinFromCA(caId, templateId) {
    return apiClient.delete(`/cas/${caId}/templates/${templateId}/pin`)
  },

  async getForCAWithPinStatus(caId) {
    return apiClient.get(`/cas/${caId}/templates`)
  }
}
