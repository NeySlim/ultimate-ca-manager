import { api } from '../../../core/api/client';

export const certificateService = {
  async getAll(params = {}) {
    return await api.get('/certificates', { params });
  },

  async getById(id) {
    return await api.get(`/certificates/${id}`);
  },

  async create(data) {
    return await api.post('/certificates', data);
  },

  async revoke(id, reason) {
    return await api.post(`/certificates/${id}/revoke`, { reason });
  },

  async renew(id) {
    return await api.post(`/certificates/${id}/renew`);
  },

  async export(id, format = 'pem', includeChain = false) {
    return await api.get(`/certificates/${id}/export`, { 
      params: { format, include_chain: includeChain } 
    });
  },

  async import(data) {
    return await api.post('/certificates/import', data);
  },
};
