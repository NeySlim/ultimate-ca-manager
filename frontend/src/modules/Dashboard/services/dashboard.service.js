import { api } from '../../../core/api/client';

export const dashboardService = {
  async getStats() {
    return await api.get('/dashboard/stats');
  },

  async getRecentActivity(params = {}) {
    return await api.get('/dashboard/activity', { params });
  },

  async getExpiringCerts(days = 30) {
    return await api.get('/dashboard/expiring-certs', { params: { days } });
  },

  async getRecentCAs(limit = 5) {
    return await api.get('/dashboard/recent-cas', { params: { limit } });
  },
};
