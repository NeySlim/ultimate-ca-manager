/**
 * Settings API Service
 */
import api from './api';

export const settingsApi = {
  /**
   * Get all settings (uses /general endpoint for now)
   */
  getAll: async () => {
    const response = await api.get('/api/v2/settings/general');
    // Wrap in structure expected by frontend
    return {
      general: response.data,
      security: {},
      email: {},
      backup: {},
    };
  },

  /**
   * Get general settings
   */
  getGeneral: async () => {
    const response = await api.get('/api/v2/settings/general');
    return response.data;
  },

  /**
   * Update general settings
   */
  updateGeneral: async (data) => {
    const response = await api.patch('/api/v2/settings/general', data);
    return response.data;
  },

  /**
   * Get users list (admin only)
   */
  getUsers: async () => {
    const response = await api.get('/api/v2/settings/users');
    return response.data || [];
  },

  /**
   * Create user (admin only)
   */
  createUser: async (data) => {
    const response = await api.post('/api/v2/settings/users', data);
    return response.data;
  },
};
