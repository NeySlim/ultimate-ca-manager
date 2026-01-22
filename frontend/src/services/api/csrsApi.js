/**
 * CSRs (Certificate Signing Requests) API Service
 */
import api from './api';

export const csrsApi = {
  /**
   * Get all CSRs with pagination and filters
   */
  getAll: async (params = {}) => {
    const response = await api.get('/api/v2/csrs', { params });
    return response;
  },

  /**
   * Get single CSR
   */
  getById: async (id) => {
    const response = await api.get(`/api/v2/csrs/${id}`);
    return response.data;
  },

  /**
   * Approve CSR
   */
  approve: async (id, caId) => {
    const response = await api.post(`/api/v2/csrs/${id}/approve`, { ca_id: caId });
    return response.data;
  },

  /**
   * Reject CSR
   */
  reject: async (id, reason) => {
    const response = await api.post(`/api/v2/csrs/${id}/reject`, { reason });
    return response.data;
  },

  /**
   * Delete CSR
   */
  delete: async (id) => {
    const response = await api.delete(`/api/v2/csrs/${id}`);
    return response.data;
  },
};
