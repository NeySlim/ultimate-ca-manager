import { apiClient } from './apiClient'

const BASE = '/user-certificates'

export const userCertificatesService = {
  getAll: (params = {}) => apiClient.get(BASE, { params }),
  getStats: () => apiClient.get(`${BASE}/stats`),
  getById: (id) => apiClient.get(`${BASE}/${id}`),
  exportCert: (id, format = 'pem', { password, includeKey = true, includeChain = true } = {}) => {
    const params = { format, include_key: includeKey, include_chain: includeChain }
    if (password) params.password = password
    return apiClient.get(`${BASE}/${id}/export`, { params, responseType: 'blob' })
  },
  revoke: (id, reason = 'unspecified') => apiClient.post(`${BASE}/${id}/revoke`, { reason }),
  delete: (id) => apiClient.delete(`${BASE}/${id}`),
}
