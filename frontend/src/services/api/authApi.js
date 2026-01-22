/**
 * Auth API Service
 */
import api from './api';

export const authApi = {
  /**
   * Login
   */
  login: async (username, password) => {
    const response = await api.post('/api/v2/auth/login', {
      username,
      password,
    });
    return response;
  },

  /**
   * Logout
   */
  logout: async () => {
    const response = await api.post('/api/v2/auth/logout');
    return response;
  },

  /**
   * Verify session
   */
  verify: async () => {
    const response = await api.get('/api/v2/auth/verify');
    return response;
  },
};
