/**
 * ACME API Service
 */
import api from './api';

export const acmeApi = {
  /**
   * Get ACME settings
   * Backend returns: { data: { contact_email, enabled, provider } }
   */
  getSettings: async () => {
    const response = await api.get('/api/v2/acme/settings');
    return response.data;
  },

  /**
   * Update ACME settings
   */
  updateSettings: async (data) => {
    const response = await api.patch('/api/v2/acme/settings', data);
    return response.data;
  },

  /**
   * Get ACME stats
   * Backend returns: { data: { active_accounts, total_orders, pending_orders, valid_orders, invalid_orders } }
   * Transform to frontend format
   */
  getStats: async () => {
    const response = await api.get('/api/v2/acme/stats');
    const stats = response.data || {};
    
    // Transform to match what frontend expects
    return {
      accounts: stats.active_accounts || 0,
      activeOrders: stats.pending_orders || 0,
      completedOrders: stats.valid_orders || 0,
      domains: 0, // Backend doesn't provide this yet
      // Keep original data
      _raw: stats,
    };
  },

  /**
   * Get ACME accounts
   * Backend returns: { data: [...], meta: {} }
   * Transform to frontend format
   */
  getAccounts: async (params = {}) => {
    const response = await api.get('/api/v2/acme/accounts', { params });
    
    // Transform backend data to frontend format
    const transformedData = (response.data || []).map(account => ({
      id: account.id,
      email: account.email || account.contact_email || 'N/A',
      status: (account.status || 'ACTIVE').toUpperCase(),
      createdAt: account.created_at ? account.created_at.split('T')[0] : 'N/A',
      orders: account.total_orders || 0,
      // Keep original data
      _raw: account,
    }));
    
    return {
      data: transformedData,
      meta: response.meta || { page: 1, per_page: 20, total: transformedData.length },
    };
  },

  /**
   * Get ACME orders
   * Backend returns: { data: [...], meta: {} }
   * Transform to frontend format
   */
  getOrders: async (params = {}) => {
    const response = await api.get('/api/v2/acme/orders', { params });
    
    // Transform backend data to frontend format
    const transformedData = (response.data || []).map(order => ({
      id: order.id,
      domain: order.domain || order.identifier || 'N/A',
      account: order.account_email || order.account_id || 'N/A',
      status: (order.status || 'PENDING').toUpperCase(),
      createdAt: order.created_at ? order.created_at.split('T')[0] : 'N/A',
      expiresAt: order.expires_at ? order.expires_at.split('T')[0] : 'N/A',
      // Keep original data
      _raw: order,
    }));
    
    return {
      data: transformedData,
      meta: response.meta || { page: 1, per_page: 20, total: transformedData.length },
    };
  },
};
