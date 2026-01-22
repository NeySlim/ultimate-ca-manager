/**
 * ACME API Service
 */
import api from './api';

export const acmeApi = {
  /**
   * Get ACME settings
   */
  getSettings: async () => {
    const response = await api.get('/api/v2/acme/settings');
    return response.data;
  },

  /**
   * Update ACME settings
   */
  updateSettings: async (data) => {
    const response = await api.patch('/api/v2/acme/settings', data);
    return response.data;
  },

  /**
   * Get ACME stats
   */
  getStats: async () => {
    const response = await api.get('/api/v2/acme/stats');
    return response.data;
  },

  /**
   * Get ACME accounts
   */
  getAccounts: async (params = {}) => {
    const response = await api.get('/api/v2/acme/accounts', { params });
    return response.data || [];
  },

  /**
   * Get ACME orders
   */
  getOrders: async (params = {}) => {
    const response = await api.get('/api/v2/acme/orders', { params });
    return response.data || [];
  },
};
