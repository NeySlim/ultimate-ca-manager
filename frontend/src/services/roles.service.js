/**
 * Roles & Permissions Service
 */
import { apiClient } from './apiClient'

export const rolesService = {
  /**
   * Get all roles and their permissions
   * @returns {Promise<Object>} Roles data
   */
  async getAll() {
    const response = await apiClient.get('/roles')
    return response.data
  },

  /**
   * Get permissions for specific role
   * @param {string} role - Role name
   * @returns {Promise<Object>} Role data
   */
  async getRole(role) {
    const response = await apiClient.get(`/roles/${role}`)
    return response.data
  },
}
