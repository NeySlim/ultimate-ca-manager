import { apiClient } from './apiClient'

const mscaService = {
  // Connections CRUD
  getAll: () =>
    apiClient.get('/microsoft-cas'),

  getEnabled: () =>
    apiClient.get('/microsoft-cas/enabled'),

  getById: (id) =>
    apiClient.get(`/microsoft-cas/${id}`),

  create: (data) =>
    apiClient.post('/microsoft-cas', data),

  update: (id, data) =>
    apiClient.put(`/microsoft-cas/${id}`, data),

  delete: (id) =>
    apiClient.delete(`/microsoft-cas/${id}`),

  // Test connection
  test: (id) =>
    apiClient.post(`/microsoft-cas/${id}/test`),

  // Templates
  getTemplates: (id) =>
    apiClient.get(`/microsoft-cas/${id}/templates`),

  // Sign CSR via MS CA
  signCSR: (mscaId, csrId, template) =>
    apiClient.post(`/microsoft-cas/${mscaId}/sign/${csrId}`, { template }),

  // Check pending request status
  checkRequest: (mscaId, requestId) =>
    apiClient.get(`/microsoft-cas/${mscaId}/requests/${requestId}`),

  // List pending requests
  getPendingRequests: (mscaId) =>
    apiClient.get(`/microsoft-cas/requests/pending${mscaId ? `?msca_id=${mscaId}` : ''}`),
}

export { mscaService }
