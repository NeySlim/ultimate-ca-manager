/**
 * Certificates Service
 */
import { apiClient } from './apiClient'

export const certificatesService = {
  async getAll(filters = {}) {
    const params = new URLSearchParams()
    if (filters.status) params.append('status', filters.status)
    if (filters.issuer) params.append('issuer', filters.issuer)
    if (filters.search) params.append('search', filters.search)
    if (filters.page) params.append('page', filters.page)
    if (filters.per_page) params.append('per_page', filters.per_page)
    
    const query = params.toString() ? `?${params.toString()}` : ''
    return apiClient.get(`/certificates${query}`)
  },

  async getById(id) {
    return apiClient.get(`/certificates/${id}`)
  },

  async create(data) {
    return apiClient.post('/certificates', data)
  },

  async revoke(id, reason) {
    return apiClient.post(`/certificates/${id}/revoke`, { reason })
  },

  async renew(id) {
    return apiClient.post(`/certificates/${id}/renew`)
  },

  async export(id, format = 'pem', options = {}) {
    const params = new URLSearchParams()
    params.append('format', format)
    if (options.includeKey) params.append('include_key', 'true')
    if (options.includeChain) params.append('include_chain', 'true')
    if (options.password) params.append('password', options.password)
    
    return apiClient.get(`/certificates/${id}/export?${params.toString()}`, {
      responseType: 'blob'
    })
  },

  async delete(id) {
    return apiClient.delete(`/certificates/${id}`)
  },

  async import(formData) {
    // FormData for file upload - don't JSON stringify
    return fetch('/api/v2/certificates/import', {
      method: 'POST',
      body: formData,
      credentials: 'include'
    }).then(async res => {
      const data = await res.json()
      if (!res.ok) throw new Error(data.message || data.error || 'Import failed')
      return data
    })
  }
}
