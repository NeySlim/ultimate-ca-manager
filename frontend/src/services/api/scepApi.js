/**
 * SCEP API Service
 */
import api from './api';

export const scepApi = {
  /**
   * Get SCEP settings (uses /config endpoint)
   */
  getSettings: async () => {
    const response = await api.get('/api/v2/scep/config');
    return response.data;
  },

  /**
   * Update SCEP settings
   */
  updateSettings: async (data) => {
    const response = await api.patch('/api/v2/scep/config', data);
    return response.data;
  },

  /**
   * Get SCEP stats (mock for now, backend doesn't have this endpoint yet)
   */
  getStats: async () => {
    const response = await api.get('/api/v2/scep/requests');
    const requests = response.data || [];
    
    // Calculate stats from requests
    const pending = requests.filter(r => r.status === 'pending').length;
    const approved = requests.filter(r => r.status === 'approved').length;
    const rejected = requests.filter(r => r.status === 'rejected').length;
    
    return {
      total_requests: requests.length,
      pending,
      approved,
      rejected,
      total_enrollments: approved,
    };
  },

  /**
   * Get SCEP requests
   */
  getRequests: async (params = {}) => {
    const response = await api.get('/api/v2/scep/requests', { params });
    return response.data || [];
  },

  /**
   * Approve SCEP enrollment request
   */
  approveRequest: async (requestId) => {
    const response = await api.post(`/api/v2/scep/${requestId}/approve`);
    return response.data;
  },

  /**
   * Reject SCEP enrollment request
   */
  rejectRequest: async (requestId) => {
    const response = await api.post(`/api/v2/scep/${requestId}/reject`);
    return response.data;
  },
};
