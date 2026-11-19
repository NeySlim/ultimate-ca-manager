/**
 * Users Service
 */
import { apiClient, buildQueryString } from './apiClient'

export const usersService = {
  async getAll(filters = {}) {
    return apiClient.get(`/users${buildQueryString(filters)}`)
  },

  async getById(id) {
    return apiClient.get(`/users/${id}`)
  },

  async create(data) {
    return apiClient.post('/users', data)
  },

  async update(id, data) {
    return apiClient.put(`/users/${id}`, data)
  },

  async delete(id) {
    return apiClient.delete(`/users/${id}`)
  },

  // The route reads new_password and refuses 400 without it; it does not
  // generate one, and it returns a message only (no password in the answer).
  async resetPassword(id, newPassword, currentPassword) {
    const body = { new_password: newPassword }
    // Required by the server when the account is the caller's own
    if (currentPassword) body.current_password = currentPassword
    return apiClient.post(`/users/${id}/reset-password`, body)
  },

  async reset2FA(id) {
    return apiClient.post(`/users/${id}/reset-2fa`)
  },

  // Another user's security keys (administrators): lost-key recovery
  async getSecurityKeys(id) {
    return apiClient.get(`/users/${id}/webauthn`)
  },

  async deleteSecurityKey(id, keyId, { confirmLastFactor = false } = {}) {
    return apiClient.delete(`/users/${id}/webauthn/${keyId}${confirmLastFactor ? '?confirm=last_factor' : ''}`)
  },

  async setSecurityKeyEnabled(id, keyId, enabled, { confirmLastFactor = false } = {}) {
    return apiClient.patch(`/users/${id}/webauthn/${keyId}${confirmLastFactor ? '?confirm=last_factor' : ''}`, { enabled })
  },

  async getApiKeys(id) {
    return apiClient.get(`/users/${id}/apikeys`)
  },

  async deleteApiKey(id, keyId) {
    return apiClient.delete(`/users/${id}/apikeys/${keyId}`)
  },

  async getPasswordPolicy() {
    return apiClient.get('/users/password-policy')
  },

  async toggleActive(id) {
    return apiClient.post(`/users/${id}/toggle-active`)
  },

  // One row per provider that opens the account (sso_identities)
  async attachSso(id, { provider_id, remove_password } = {}) {
    return apiClient.post(`/users/${id}/sso-identities`, { provider_id, remove_password })
  },

  async resetSsoIdentity(id, identityId) {
    return apiClient.post(`/users/${id}/sso-identities/${identityId}/reset`)
  },

  async detachSso(id, identityId) {
    return apiClient.delete(`/users/${id}/sso-identities/${identityId}`)
  },

  // Bulk operations
  async bulkDelete(ids) {
    return apiClient.post('/users/bulk/delete', { ids })
  },

  // mTLS certificate management
  async getMtlsCertificates(userId) {
    return apiClient.get(`/users/${userId}/mtls/certificates`)
  },

  async createMtlsCertificate(userId, data) {
    return apiClient.post(`/users/${userId}/mtls/certificates`, data)
  },

  async deleteMtlsCertificate(userId, certId) {
    return apiClient.delete(`/users/${userId}/mtls/certificates/${certId}`)
  },

  async assignMtlsCertificate(data) {
    return apiClient.post('/mtls/assign', data)
  }
}
