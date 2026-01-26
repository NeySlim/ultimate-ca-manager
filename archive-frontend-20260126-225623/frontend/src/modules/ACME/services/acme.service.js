import { api } from '../../../core/api/client';

export const acmeService = {
  async getStats() {
    return await api.get('/acme/stats');
  },

  async getSettings() {
    return await api.get('/acme/settings');
  },

  async updateSettings(data) {
    return await api.patch('/acme/settings', data);
  },

  async getOrders(params = {}) {
    return await api.get('/acme/orders', { params });
  },

  async getAccounts(params = {}) {
    return await api.get('/acme/accounts', { params });
  },
};
