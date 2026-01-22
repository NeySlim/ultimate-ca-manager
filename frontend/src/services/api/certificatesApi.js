/**
 * Certificates API Service
 */
import api from './api';

export const certificatesApi = {
  /**
   * Get all certificates with pagination and filters
   */
  getAll: async (params = {}) => {
    const response = await api.get('/api/v2/certificates', { params });
    return response;
  },

  /**
   * Get single certificate
   */
  getById: async (id) => {
    const response = await api.get(`/api/v2/certificates/${id}`);
    return response.data;
  },

  /**
   * Revoke certificate
   */
  revoke: async (id, reason) => {
    const response = await api.post(`/api/v2/certificates/${id}/revoke`, { reason });
    return response.data;
  },

  /**
   * Renew certificate
   */
  renew: async (id) => {
    const response = await api.post(`/api/v2/certificates/${id}/renew`);
    return response.data;
  },

  /**
   * Download certificate
   */
  download: async (id, format = 'pem') => {
    const response = await api.get(`/api/v2/certificates/${id}/download`, {
      params: { format },
      responseType: 'blob',
    });
    return response;
  },
};
