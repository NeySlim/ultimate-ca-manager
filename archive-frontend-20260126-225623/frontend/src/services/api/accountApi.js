/**
 * Account/Profile API Service
 */
import api from './api';

export const accountApi = {
  /**
   * Get user profile
   * Backend returns: { data: { id, username, email, created_at } }
   * Note: Backend might not provide all fields, frontend will use defaults
   */
  getProfile: async () => {
    const response = await api.get('/api/v2/account/profile');
    const profile = response.data || {};
    
    // Return as-is, page will handle defaults
    return profile;
  },

  /**
   * Update profile
   */
  updateProfile: async (data) => {
    const response = await api.patch('/api/v2/account/profile', data);
    return response.data;
  },

  /**
   * Change password
   */
  changePassword: async (currentPassword, newPassword) => {
    const response = await api.post('/api/v2/account/password', {
      current_password: currentPassword,
      new_password: newPassword,
    });
    return response.data;
  },

  /**
   * Get user activity
   * Backend returns: { data: [...] }
   * Transform to frontend format
   */
  getActivity: async (params = {}) => {
    const response = await api.get('/api/v2/account/activity', { params });
    
    // Transform backend data to frontend format
    const transformedData = (response.data || []).map(activity => {
      // Determine category and type based on action or existing fields
      const action = activity.action || activity.event || '';
      const category = activity.category || (
        action.includes('certificate') || action.includes('ca') || action.includes('csr') 
          ? 'pki' 
          : 'app'
      );
      
      const type = activity.type || activity.severity || (
        action.includes('error') || action.includes('failed') 
          ? 'error' 
          : action.includes('warn') 
            ? 'warning' 
            : 'info'
      );
      
      const icon = activity.icon || (
        type === 'error' ? 'ph-x-circle' 
          : type === 'warning' ? 'ph-warning' 
            : type === 'success' ? 'ph-check-circle' 
              : 'ph-info'
      );
      
      return {
        id: activity.id,
        category: category,
        type: type,
        icon: icon,
        text: activity.message || activity.description || action,
        time: activity.timestamp || activity.created_at || 'N/A',
        user: activity.user || activity.username || 'System',
        // Keep original data
        _raw: activity,
      };
    });
    
    return {
      data: transformedData,
      meta: response.meta || { page: 1, per_page: 50, total: transformedData.length },
    };
  },

  /**
   * Get sessions
   */
  getSessions: async () => {
    const response = await api.get('/api/v2/account/sessions');
    return response.data || [];
  },

  /**
   * Revoke session
   */
  revokeSession: async (sessionId) => {
    const response = await api.delete(`/api/v2/account/sessions/${sessionId}`);
    return response.data;
  },

  /**
   * Revoke all sessions
   */
  revokeAllSessions: async () => {
    const response = await api.delete('/api/v2/account/sessions');
    return response.data;
  },
};
