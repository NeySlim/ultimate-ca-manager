/**
 * SSH Certificate Authorities Service
 */
import { apiClient, buildQueryString } from './apiClient'

export const sshCasService = {
  async getAll(params) {
    return apiClient.get(`/ssh/cas${buildQueryString(params)}`)
  },

  async getById(id) {
    return apiClient.get(`/ssh/cas/${id}`)
  },

  async create(data) {
    return apiClient.post('/ssh/cas', data)
  },

  async update(id, data) {
    return apiClient.put(`/ssh/cas/${id}`, data)
  },

  async delete(id) {
    return apiClient.delete(`/ssh/cas/${id}`)
  },

  async getPublicKey(id) {
    return apiClient.get(`/ssh/cas/${id}/public-key`)
  },

  async getKRL(id) {
    return apiClient.get(`/ssh/cas/${id}/krl`, { responseType: 'blob' })
  },

  async getSetupScript(id) {
    return apiClient.get(`/ssh/cas/${id}/setup-script`, { responseType: 'blob' })
  },

  async importCA(data) {
    return apiClient.post('/ssh/cas/import', data)
  },
}
