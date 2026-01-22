/**
 * CAs (Certificate Authorities) API Service
 */
import api from './api';

export const casApi = {
  /**
   * Get all CAs
   * Backend returns: { data: [...], meta: { page, per_page, total } }
   */
  getAll: async (params = {}) => {
    const response = await api.get('/api/v2/cas', { params });
    return response;
  },

  /**
   * Get single CA by ID
   */
  getById: async (id) => {
    const response = await api.get(`/api/v2/cas/${id}`);
    return response.data;
  },

  /**
   * Create new CA
   */
  create: async (data) => {
    const response = await api.post('/api/v2/cas', data);
    return response.data;
  },

  /**
   * Update CA
   */
  update: async (id, data) => {
    const response = await api.patch(`/api/v2/cas/${id}`, data);
    return response.data;
  },

  /**
   * Delete CA
   */
  delete: async (id) => {
    const response = await api.delete(`/api/v2/cas/${id}`);
    return response.data;
  },
};
