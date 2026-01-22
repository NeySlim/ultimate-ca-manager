/**
 * TrustStore API Service
 */
import api from './api';

export const truststoreApi = {
  /**
   * Get all trusted certificates
   * Backend: GET /api/v2/truststore
   */
  getTrustedCerts: async (params = {}) => {
    const response = await api.get('/api/v2/truststore', { params });
    return response.data; // { data: [...], meta: {} }
  },

  /**
   * Add trusted certificate
   * Backend: POST /api/v2/truststore
   */
  addTrustedCert: async (certData) => {
    const response = await api.post('/api/v2/truststore', certData);
    return response.data;
  },

  /**
   * Remove trusted certificate
   * Backend: DELETE /api/v2/truststore/:id
   */
  removeTrustedCert: async (id) => {
    const response = await api.delete(`/api/v2/truststore/${id}`);
    return response.data;
  },
};
