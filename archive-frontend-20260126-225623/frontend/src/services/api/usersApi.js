/**
 * Users API Service
 */
import api from './api';

export const usersApi = {
  /**
   * Get all users
   * Backend: GET /api/v2/users
   */
  getUsers: async (params = {}) => {
    const response = await api.get('/api/v2/users', { params });
    return response.data; // { data: [...], meta: {} }
  },

  /**
   * Create user
   * Backend: POST /api/v2/users
   */
  createUser: async (userData) => {
    const response = await api.post('/api/v2/users', userData);
    return response.data;
  },

  /**
   * Update user
   * Backend: PUT /api/v2/users/:id
   */
  updateUser: async ({ id, ...userData }) => {
    const response = await api.put(`/api/v2/users/${id}`, userData);
    return response.data;
  },

  /**
   * Reset user password
   * Backend: POST /api/v2/users/:id/reset-password
   */
  resetPassword: async (id, newPassword) => {
    const response = await api.post(`/api/v2/users/${id}/reset-password`, { new_password: newPassword });
    return response.data;
  },

  /**
   * Toggle user active status
   * Backend: PATCH /api/v2/users/:id/toggle
   */
  toggleStatus: async (id) => {
    const response = await api.patch(`/api/v2/users/${id}/toggle`);
    return response.data;
  },

  /**
   * Delete user (soft delete)
   * Backend: DELETE /api/v2/users/:id
   */
  deleteUser: async (id) => {
    const response = await api.delete(`/api/v2/users/${id}`);
    return response.data;
  },

  /**
   * Import users from CSV
   * Backend: POST /api/v2/users/import
   */
  importUsers: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post('/api/v2/users/import', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    return response.data;
  },
};
