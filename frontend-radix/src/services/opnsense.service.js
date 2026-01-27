/**
 * OpnSense Import Service
 */
import { apiClient } from './apiClient'

export const opnsenseService = {
  /**
   * Test OpnSense connection and fetch available CAs/Certificates
   * @param {Object} config - {host, port, api_key, api_secret, verify_ssl}
   * @returns {Promise<{success: boolean, items: Array, stats: {cas: number, certificates: number}}>}
   */
  async test(config) {
    return apiClient.request('/import/opnsense/test', {
      method: 'POST',
      body: JSON.stringify(config)
    })
  },

  /**
   * Import selected items from OpnSense
   * @param {Object} config - {host, port, api_key, api_secret, verify_ssl, items: Array<string>}
   * @returns {Promise<{success: boolean, imported: {cas: number, certificates: number}, skipped: number}>}
   */
  async import(config) {
    return apiClient.request('/import/opnsense/import', {
      method: 'POST',
      body: JSON.stringify(config)
    })
  }
}
