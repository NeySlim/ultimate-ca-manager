/**
 * Audit Logs Service
 * View and manage audit logs
 */
import { apiClient, buildQueryString } from './apiClient';

const auditService = {
  /**
   * Get audit logs with filtering and pagination
   * @param {Object} params - Query parameters
   * @returns {Promise<{data: Array, meta: Object}>}
   */
  getLogs: async (params = {}) => {
    return apiClient.get(`/audit/logs${buildQueryString(params)}`);
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
    return apiClient.get(`/audit/export${buildQueryString(params)}`);
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
