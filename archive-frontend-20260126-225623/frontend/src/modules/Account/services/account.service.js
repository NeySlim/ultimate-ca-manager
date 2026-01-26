import { api } from '../../../core/api/client';

export const accountService = {
  async getProfile() {
    return await api.get('/account/profile');
  },

  async updateProfile(data) {
    return await api.patch('/account/profile', data);
  },

  async changePassword(data) {
    return await api.post('/account/password', data);
  },

  async getApiKeys() {
    return await api.get('/account/apikeys');
  },

  async createApiKey(data) {
    return await api.post('/account/apikeys', data);
  },

  async deleteApiKey(id) {
    return await api.delete(`/account/apikeys/${id}`);
  },

  async getSessions() {
    return await api.get('/account/sessions');
  },

  async revokeSession(id) {
    return await api.delete(`/account/sessions/${id}`);
  },
};
