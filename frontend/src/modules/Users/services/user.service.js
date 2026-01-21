import { api } from '../../../core/api/client';

export const userService = {
  async getAll(params = {}) {
    return await api.get('/settings/users', { params });
  },

  async getById(id) {
    return await api.get(`/settings/users/${id}`);
  },

  async create(data) {
    return await api.post('/settings/users', data);
  },

  async update(id, data) {
    return await api.patch(`/settings/users/${id}`, data);
  },

  async delete(id) {
    return await api.delete(`/settings/users/${id}`);
  },
};
