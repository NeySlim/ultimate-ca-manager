import { apiClient, buildQueryString } from './apiClient'

const BASE = '/user-certificates'

export const userCertificatesService = {
  getAll: (params = {}) => apiClient.get(`${BASE}${buildQueryString(params)}`),
  getStats: () => apiClient.get(`${BASE}/stats`),
  getById: (id) => apiClient.get(`${BASE}/${id}`),
  exportCert: (id, format = 'pem', { password, includeKey = true, includeChain = true } = {}) => {
    return apiClient.get(`${BASE}/${id}/export${buildQueryString({
      format,
      include_key: includeKey,
      include_chain: includeChain,
      password
    })}`, { responseType: 'blob' })
  },
  revoke: (id, reason = 'unspecified') => apiClient.post(`${BASE}/${id}/revoke`, { reason }),
  delete: (id) => apiClient.delete(`${BASE}/${id}`),
}
