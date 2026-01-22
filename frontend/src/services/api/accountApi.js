/**
 * Account/Profile API Service
 */
import api from './api';

export const accountApi = {
  /**
   * Get user profile
   */
  getProfile: async () => {
    const response = await api.get('/api/v2/account/profile');
    return response.data;
  },

  /**
   * Update profile
   */
  updateProfile: async (data) => {
    const response = await api.patch('/api/v2/account/profile', data);
    return response.data;
  },

  /**
   * Change password
   */
  changePassword: async (currentPassword, newPassword) => {
    const response = await api.post('/api/v2/account/password', {
      current_password: currentPassword,
      new_password: newPassword,
    });
    return response.data;
  },

  /**
   * Get user activity
   */
  getActivity: async (params = {}) => {
    const response = await api.get('/api/v2/account/activity', { params });
    return response.data || [];
  },

  /**
   * Get sessions
   */
  getSessions: async () => {
    const response = await api.get('/api/v2/account/sessions');
    return response.data || [];
  },

  /**
   * Revoke session
   */
  revokeSession: async (sessionId) => {
    const response = await api.delete(`/api/v2/account/sessions/${sessionId}`);
    return response.data;
  },
};
