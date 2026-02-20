/**
 * OpnSense Import Service
 */
import { apiClient } from './apiClient'

export const opnsenseService = {
  async test(config) {
    return apiClient.post('/import/opnsense/test', config)
  },

  async import(config) {
    return apiClient.post('/import/opnsense/import', config)
  }
}
