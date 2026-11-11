/**
 * Deploy Hooks Service (#299) — admin-only
 * Reusable SSH/SFTP targets plus certificate- and CRL-specific deployments.
 */
import { apiClient, buildQueryString } from './apiClient'

export const deployService = {
  // Targets
  async getTargets() {
    return apiClient.get('/deploy/targets')
  },
  async getTarget(id) {
    return apiClient.get(`/deploy/targets/${id}`)
  },
  async createTarget(data) {
    return apiClient.post('/deploy/targets', data)
  },
  async updateTarget(id, data) {
    return apiClient.patch(`/deploy/targets/${id}`, data)
  },
  async deleteTarget(id) {
    return apiClient.delete(`/deploy/targets/${id}`)
  },
  async testTarget(id) {
    return apiClient.post(`/deploy/targets/${id}/test`)
  },

  // Bindings
  async getBindings(params = {}) {
    return apiClient.get(`/deploy/bindings${buildQueryString(params)}`)
  },
  async createBinding(data) {
    return apiClient.post('/deploy/bindings', data)
  },
  async updateBinding(id, data) {
    return apiClient.patch(`/deploy/bindings/${id}`, data)
  },
  async deleteBinding(id) {
    return apiClient.delete(`/deploy/bindings/${id}`)
  },
  async deployNow(bindingId) {
    return apiClient.post(`/deploy/bindings/${bindingId}/deploy`)
  },
  // A binding a renewal left on the previous certificate moves onto the renewed one
  async reattachBinding(bindingId) {
    return apiClient.post(`/deploy/bindings/${bindingId}/reattach`)
  },

  // CRL bindings
  async getCRLBindings(params = {}) {
    return apiClient.get(`/deploy/crl-bindings${buildQueryString(params)}`)
  },
  async createCRLBinding(data) {
    return apiClient.post('/deploy/crl-bindings', data)
  },
  async updateCRLBinding(id, data) {
    return apiClient.patch(`/deploy/crl-bindings/${id}`, data)
  },
  async deleteCRLBinding(id) {
    return apiClient.delete(`/deploy/crl-bindings/${id}`)
  },
  async deployCRLNow(bindingId) {
    return apiClient.post(`/deploy/crl-bindings/${bindingId}/deploy`)
  },

  // Deliveries
  async getDeliveries(params = {}) {
    return apiClient.get(`/deploy/deliveries${buildQueryString(params)}`)
  },
  async retryDelivery(id) {
    return apiClient.post(`/deploy/deliveries/${id}/retry`)
  },
}
