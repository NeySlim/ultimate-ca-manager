/**
 * Groups Service - API client for group management
 */
import { apiClient as api } from './apiClient'

export const groupsService = {
  /**
   * Get all groups
   */
  getAll: async (params = {}) => {
    return api.get('/groups', { params })
  },

  /**
   * Get group by ID
   */
  getById: async (id) => {
    return api.get(`/groups/${id}`)
  },

  /**
   * Create a new group
   */
  create: async (groupData) => {
    return api.post('/groups', groupData)
  },

  /**
   * Update a group
   */
  update: async (id, groupData) => {
    return api.put(`/groups/${id}`, groupData)
  },

  /**
   * Delete a group
   */
  delete: async (id) => {
    return api.delete(`/groups/${id}`)
  },

  /**
   * Get group members
   */
  getMembers: async (groupId) => {
    return api.get(`/groups/${groupId}/members`)
  },

  /**
   * Add a member to a group
   */
  addMember: async (groupId, userId, role = 'member') => {
    return api.post(`/groups/${groupId}/members`, {
      user_id: userId,
      role
    })
  },

  /**
   * Remove a member from a group
   */
  removeMember: async (groupId, userId) => {
    return api.delete(`/groups/${groupId}/members/${userId}`)
  },

  /**
   * Get groups statistics
   */
  getStats: async () => {
    return api.get('/groups/stats')
  }
}

export default groupsService
