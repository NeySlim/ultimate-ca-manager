import { api } from '../../../core/api/client';

export const ScepService = {
  getStats: async () => {
    const response = await api.get('/scep/stats');
    return response.data;
  },

  getConfig: async () => {
    const response = await api.get('/scep/config');
    return response.data;
  },
  
  updateConfig: async (data) => {
    const response = await api.patch('/scep/config', data);
    return response.data;
  },
  
  getRequests: async (params = {}) => {
    const response = await api.get('/scep/requests', { params });
    return response.data;
  },
  
  approveRequest: async (id) => {
    const response = await api.post(`/scep/${id}/approve`);
    return response.data;
  },
  
  rejectRequest: async (id, reason) => {
    const response = await api.post(`/scep/${id}/reject`, { reason });
    return response.data;
  }
};
