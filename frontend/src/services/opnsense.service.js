/**
 * OpnSense Import Service
 */
import { apiClient } from './apiClient'

export const opnsenseService = {
  async test(config) {
    const response = await apiClient.post('/import/opnsense/test', config)
    return response.data || response
  },

  async import(config) {
    const response = await apiClient.post('/import/opnsense/import', config)
    return response.data || response
  }
}
