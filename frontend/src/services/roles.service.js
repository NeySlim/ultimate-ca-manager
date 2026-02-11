/**
 * Roles & Permissions Service
 */
import { apiClient } from './apiClient'

export const rolesService = {
  /**
   * Get all roles and their permissions
   * @returns {Promise<Object>} Roles data keyed by role id
   */
  async getAll() {
    const response = await apiClient.get('/rbac/roles')
    const roles = response.data || []
    const rolesMap = {}
    for (const role of roles) {
      rolesMap[role.id] = role
    }
    return rolesMap
  },

  /**
   * Get permissions for specific role
   * @param {string} role - Role name
   * @returns {Promise<Object>} Role data
   */
  async getRole(role) {
    const response = await apiClient.get(`/rbac/roles/${role}`)
    return response.data
  },
}
