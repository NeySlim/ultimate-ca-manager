import { api } from '../../../core/api/client';

export const CsrService = {
  getAll: async (params = {}) => {
    const response = await api.get('/csrs', { params });
    return response.data;
  },

  getById: async (id) => {
    const response = await api.get(`/csrs/${id}`);
    return response.data;
  },

  create: async (data) => {
    const response = await api.post('/csrs', data);
    return response.data;
  },

  delete: async (id) => {
    await api.delete(`/csrs/${id}`);
  }
};
