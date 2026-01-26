import { api } from '../../../core/api/client';

export const csrService = {
  async getAll(params = {}) {
    return await api.get('/csrs', { params });
  },

  async getById(id) {
    return await api.get(`/csrs/${id}`);
  },

  async create(data) {
    return await api.post('/csrs', data);
  },

  async delete(id) {
    return await api.delete(`/csrs/${id}`);
  },
};
