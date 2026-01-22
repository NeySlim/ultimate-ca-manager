/**
 * CAs (Certificate Authorities) API Service
 */
import api from './api';

export const casApi = {
  /**
   * Get all CAs
   * Backend returns: { data: [...], meta: { page, per_page, total } }
   * Transform to frontend format
   */
  getAll: async (params = {}) => {
    const response = await api.get('/api/v2/cas', { params });
    
    // Transform backend data to frontend format
    const transformedData = (response.data || []).map(ca => {
      // Calculate status based on valid_to date
      const expiryDate = new Date(ca.valid_to);
      const now = new Date();
      const isExpired = expiryDate < now;
      
      return {
        id: ca.id,
        name: ca.common_name || 'Unnamed CA',
        type: ca.is_root ? 'Root' : 'Intermediate',
        status: isExpired ? 'EXPIRED' : 'ACTIVE',
        issued: ca.valid_from ? ca.valid_from.split('T')[0] : 'N/A',
        expires: ca.valid_to ? ca.valid_to.split('T')[0] : 'N/A',
        certs: 0, // Not provided by backend
        children: [], // Hierarchy not provided by backend yet
        // Keep original data
        _raw: ca,
      };
    });
    
    return {
      data: transformedData,
      meta: response.meta || { page: 1, per_page: 20, total: transformedData.length },
    };
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
