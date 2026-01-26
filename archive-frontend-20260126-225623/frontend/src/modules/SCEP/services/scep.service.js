import { api } from '../../../core/api/client';

export const scepService = {
  async getStats() {
    return await api.get('/scep/stats');
  },

  async getConfig() {
    return await api.get('/scep/config');
  },

  async updateConfig(data) {
    return await api.patch('/scep/config', data);
  },

  async getRequests(params = {}) {
    return await api.get('/scep/requests', { params });
  },

  async approveRequest(id) {
    return await api.post(`/scep/${id}/approve`);
  },

  async rejectRequest(id, reason) {
    return await api.post(`/scep/${id}/reject`, { reason });
  },
};
