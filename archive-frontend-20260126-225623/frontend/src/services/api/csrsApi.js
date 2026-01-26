/**
 * CSRs (Certificate Signing Requests) API Service
 */
import api from './api';

export const csrsApi = {
  /**
   * Get all CSRs with pagination and filters
   * Backend returns: { data: [...], meta: { page, per_page, total } }
   * Backend fields: id, subject, key_size, key_type, status, created_at, requester
   * Transform to frontend format
   */
  getAll: async (params = {}) => {
    const response = await api.get('/api/v2/csrs', { params });
    
    // Transform backend data to frontend format
    const transformedData = (response.data || []).map(csr => {
      // Extract CN from subject
      const cnMatch = csr.subject?.match(/CN=([^,]+)/);
      const subject = cnMatch ? cnMatch[1] : csr.subject || 'Unnamed CSR';
      
      // Format key info
      const key = csr.key_type && csr.key_size 
        ? `${csr.key_type.toUpperCase()} ${csr.key_size}`
        : 'Unknown';
      
      // Format dates
      const submitted = csr.created_at ? csr.created_at.split('T')[0] : 'N/A';
      
      // Determine priority (simplified - backend might provide this)
      const priority = csr.priority || 'NORMAL';
      
      return {
        id: csr.id,
        subject: subject,
        key: key,
        status: (csr.status || 'PENDING').toUpperCase(),
        submitted: submitted,
        requester: csr.requester || 'Unknown',
        priority: priority,
        // Keep original data
        _raw: csr,
      };
    });
    
    return {
      data: transformedData,
      meta: response.meta || { page: 1, per_page: 20, total: transformedData.length },
    };
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
