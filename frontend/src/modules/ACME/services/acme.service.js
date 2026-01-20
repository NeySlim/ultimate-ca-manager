import { api } from '../../../core/api/client';

export const AcmeService = {
  getStats: async () => {
    const response = await api.get('/acme/stats');
    return response.data;
  },

  getOrders: async (params = {}) => {
    const response = await api.get('/acme/orders', { params });
    return response.data;
  },

  getAccounts: async () => {
    const response = await api.get('/acme/accounts');
    return response.data;
  },
  
  getSettings: async () => {
    const response = await api.get('/acme/settings');
    return response.data;
  },

  updateSettings: async (data) => {
    const response = await api.patch('/acme/settings', data);
    return response.data;
  }
};
