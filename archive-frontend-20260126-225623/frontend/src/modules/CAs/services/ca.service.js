import { api } from '../../../core/api/client';

export const caService = {
  async getAll(params = {}) {
    return await api.get('/cas', { params });
  },

  async getTree() {
    return await api.get('/cas/tree');
  },

  async getById(id) {
    return await api.get(`/cas/${id}`);
  },

  async getCertificates(id, params = {}) {
    return await api.get(`/cas/${id}/certificates`, { params });
  },

  async create(data) {
    return await api.post('/cas', data);
  },

  async update(id, data) {
    return await api.patch(`/cas/${id}`, data);
  },

  async delete(id) {
    return await api.delete(`/cas/${id}`);
  },

  async export(id, format = 'pem') {
    return await api.get(`/cas/${id}/export`, { params: { format } });
  },
};
