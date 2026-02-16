/**
 * Reports Service
 */
import { apiClient } from './apiClient'

export const reportsService = {
  async getTypes() {
    return apiClient.get('/reports/types')
  },

  async generate(reportType, params = {}) {
    return apiClient.post('/reports/generate', { report_type: reportType, params })
  },

  async download(reportType, format = 'csv', days = 30) {
    return apiClient.get(`/reports/download/${reportType}?format=${format}&days=${days}`, {
      responseType: format === 'csv' ? 'text' : 'json',
    })
  },

  async getSchedule() {
    return apiClient.get('/reports/schedule')
  },

  async updateSchedule(data) {
    return apiClient.put('/reports/schedule', data)
  },

  async sendTest(reportType, recipient) {
    return apiClient.post('/reports/send-test', { report_type: reportType, recipient })
  },
}
