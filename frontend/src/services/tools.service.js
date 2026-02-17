/**
 * Certificate Tools Service
 */
import { apiClient } from './apiClient'

export const toolsService = {
  async checkSsl(data) {
    return apiClient.post('/tools/check-ssl', data)
  },

  async decodeCsr(data) {
    return apiClient.post('/tools/decode-csr', data)
  },

  async decodeCert(data) {
    return apiClient.post('/tools/decode-cert', data)
  },

  async matchKeys(data) {
    return apiClient.post('/tools/match-keys', data)
  },

  async convert(data) {
    return apiClient.post('/tools/convert', data)
  }
}
