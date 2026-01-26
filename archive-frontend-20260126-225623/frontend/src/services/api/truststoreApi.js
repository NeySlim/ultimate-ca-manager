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
   * Get single trusted certificate details
   * Backend: GET /api/v2/truststore/:id
   */
  getTrustedCertDetails: async (id) => {
    const response = await api.get(`/api/v2/truststore/${id}`);
    return response.data;
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
   * Sync trust store with system
   * Backend: POST /api/v2/truststore/sync
   */
  syncTrustStore: async (source = 'system') => {
    const response = await api.post('/api/v2/truststore/sync', { source });
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
