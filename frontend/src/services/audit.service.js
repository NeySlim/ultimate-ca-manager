/**
 * Audit Logs Service
 * View and manage audit logs
 */
import { apiClient } from './apiClient';

const auditService = {
  /**
   * Get audit logs with filtering and pagination
   * @param {Object} params - Query parameters
   * @returns {Promise<{data: Array, meta: Object}>}
   */
  getLogs: async (params = {}) => {
    const query = new URLSearchParams();
    
    if (params.page) query.set('page', params.page);
    if (params.per_page) query.set('per_page', params.per_page);
    if (params.username) query.set('username', params.username);
    if (params.action) query.set('action', params.action);
    if (params.category) query.set('category', params.category);
    if (params.resource_type) query.set('resource_type', params.resource_type);
    if (params.success !== undefined && params.success !== null) {
      query.set('success', params.success);
    }
    if (params.date_from) query.set('date_from', params.date_from);
    if (params.date_to) query.set('date_to', params.date_to);
    if (params.search) query.set('search', params.search);
    
    const url = `/audit/logs${query.toString() ? '?' + query.toString() : ''}`;
    return apiClient.get(url);
  },

  /**
   * Get single audit log by ID
   * @param {number} id - Log ID
   */
  getLog: async (id) => {
    return apiClient.get(`/audit/logs/${id}`);
  },

  /**
   * Get audit statistics
   * @param {number} days - Number of days to analyze (default: 30)
   */
  getStats: async (days = 30) => {
    return apiClient.get(`/audit/stats?days=${days}`);
  },

  /**
   * Get available action types and categories
   */
  getActions: async () => {
    return apiClient.get('/audit/actions');
  },

  /**
   * Export audit logs
   * @param {Object} params - Export parameters
   */
  exportLogs: async (params = {}) => {
    const query = new URLSearchParams();
    if (params.format) query.set('format', params.format);
    if (params.date_from) query.set('date_from', params.date_from);
    if (params.date_to) query.set('date_to', params.date_to);
    if (params.limit) query.set('limit', params.limit);
    
    const url = `/audit/export${query.toString() ? '?' + query.toString() : ''}`;
    return apiClient.get(url);
  },

  /**
   * Cleanup old audit logs
   * @param {number} retention_days - Days to keep (min: 30)
   */
  cleanupLogs: async (retention_days = 90) => {
    return apiClient.post('/audit/cleanup', { retention_days });
  }
};

export default auditService;
