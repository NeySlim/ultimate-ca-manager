import { apiClient, buildQueryString } from './apiClient'

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

  // Test connection inline (before save)
  testInline: (data) =>
    apiClient.post('/microsoft-cas/test', data),

  // CRL revocation sync (one-way CA → UCM)
  syncCrl: (id) =>
    apiClient.post(`/microsoft-cas/${id}/sync-crl`),

  // WinRM admin channel
  testAdminChannel: (id) =>
    apiClient.post(`/microsoft-cas/${id}/admin-channel/test`),

  publishCrl: (id) =>
    apiClient.post(`/microsoft-cas/${id}/publish-crl`),

  // CA inventory sync + reconciliation
  inventorySync: (id, full = false) =>
    apiClient.post(`/microsoft-cas/${id}/inventory-sync`, { full }),

  reconciliation: (id) =>
    apiClient.get(`/microsoft-cas/${id}/reconciliation`),

  // CA control: health + pending request management
  caHealth: (id) =>
    apiClient.get(`/microsoft-cas/${id}/ca/health`),

  caPending: (id) =>
    apiClient.get(`/microsoft-cas/${id}/ca/pending`),

  approveRequest: (id, requestId) =>
    apiClient.post(`/microsoft-cas/${id}/ca/pending/${requestId}/approve`),

  denyRequest: (id, requestId) =>
    apiClient.post(`/microsoft-cas/${id}/ca/pending/${requestId}/deny`),

  // Templates
  getTemplates: (id) =>
    apiClient.get(`/microsoft-cas/${id}/templates`),

  // Sign CSR via MS CA
  signCSR: (mscaId, csrId, data) =>
    apiClient.post(`/microsoft-cas/${mscaId}/sign/${csrId}`, data),

  // Check pending request status
  checkRequest: (mscaId, requestId) =>
    apiClient.get(`/microsoft-cas/${mscaId}/requests/${requestId}`),

  // List pending requests
  getPendingRequests: (mscaId) =>
    apiClient.get(`/microsoft-cas/requests/pending${buildQueryString(mscaId ? { msca_id: mscaId } : {})}`),
}

export { mscaService }
