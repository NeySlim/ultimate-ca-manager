/**
 * Certificate Authorities Service
 */
import { apiClient, buildQueryString } from './apiClient'

export const casService = {
  async getAll() {
    return apiClient.get('/cas')
  },

  async getById(id) {
    return apiClient.get(`/cas/${id}`)
  },

  async create(data) {
    return apiClient.post('/cas', data)
  },

  async update(id, data) {
    return apiClient.patch(`/cas/${id}`, data)
  },

  async delete(id) {
    return apiClient.delete(`/cas/${id}`)
  },

  async import(formData) {
    // FormData for file upload
    return apiClient.upload('/cas/import', formData)
  },

  async export(id, format = 'pem', options = {}) {
    return apiClient.post(`/cas/${id}/export`, {
      format,
      include_key: options.includeKey ?? false,
      include_chain: options.includeChain ?? false,
      password: options.password
    }, { responseType: 'blob' })
  },

  async exportAll(format = 'pem', options = {}) {
    return apiClient.post(`/cas/export`, {
      format,
      include_chain: options.includeChain ?? false,
      password: options.password
    }, { responseType: 'blob' })
  },

  /**
   * Take a CA offline.
   * - mode 'password_protected': returns JSON (CA payload)
   * - mode 'file_exported': returns a Blob (encrypted .key file to save locally)
   */
  async takeOffline(id, { password, mode = 'password_protected' } = {}) {
    if (mode === 'file_exported') {
      return apiClient.post(
        `/cas/${id}/offline`,
        { password, mode },
        { responseType: 'blob' }
      )
    }
    return apiClient.post(`/cas/${id}/offline`, { password, mode })
  },

  /**
   * Restore an offline CA.
   * - password_protected: pass { password }
   * - file_exported: pass { password, keyFile: File }
   */
  async restore(id, { password, keyFile } = {}) {
    if (keyFile) {
      const fd = new FormData()
      fd.append('password', password || '')
      fd.append('key_file', keyFile)
      return apiClient.upload(`/cas/${id}/restore`, fd)
    }
    return apiClient.post(`/cas/${id}/restore`, { password })
  },

  async getCertificates(id, filters = {}) {
    return apiClient.get(`/cas/${id}/certificates${buildQueryString(filters)}`)
  },

  // Bulk operations
  async bulkDelete(ids) {
    return apiClient.post('/cas/bulk/delete', { ids })
  },
  async bulkExport(ids, format = 'pem') {
    return apiClient.post('/cas/bulk/export', { ids, format }, { responseType: 'blob' })
  },

  // Chain repair
  async getChainRepairStatus() {
    return apiClient.get('/system/chain-repair')
  },

  async runChainRepair() {
    return apiClient.post('/system/chain-repair/run')
  }
}
