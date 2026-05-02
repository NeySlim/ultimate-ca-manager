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
  }
}
