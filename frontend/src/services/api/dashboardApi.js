/**
 * Dashboard API Service
 * Handles all dashboard-related API calls
 */
import api from './api';

export const dashboardApi = {
  /**
   * Get public overview stats (no auth required)
   * Backend returns: { data: { total_cas, total_certs, acme_accounts, active_users } }
   * Frontend needs: array of { label, value, subtext }
   */
  getOverview: async () => {
    const response = await api.get('/api/v2/stats/overview');
    const data = response.data;
    
    // Transform to array format for UI
    return [
      {
        label: 'Certificate Authorities',
        value: String(data.total_cas || 0),
        subtext: 'Root & Intermediate',
      },
      {
        label: 'Issued Certificates',
        value: String(data.total_certs || 0),
        subtext: 'Active certificates',
      },
      {
        label: 'ACME Accounts',
        value: String(data.acme_accounts || 0),
        subtext: 'Registered accounts',
      },
      {
        label: 'Active Users',
        value: String(data.active_users || 0),
        subtext: 'System users',
      },
    ];
  },

  /**
   * Get dashboard statistics (requires auth)
   * Backend returns: { data: { total_cas, total_certificates, expiring_soon, revoked } }
   * Frontend needs: { activeCertificates, expiringSoon, pendingRequests, acmeRenewals }
   */
  getStats: async () => {
    const response = await api.get('/api/v2/dashboard/stats');
    const data = response.data;
    
    // Transform to frontend format
    return {
      activeCertificates: String(data.total_certificates || 0),
      expiringSoon: String(data.expiring_soon || 0),
      pendingRequests: '0', // Not provided by backend yet
      acmeRenewals: '0', // Not provided by backend yet
      totalCAs: String(data.total_cas || 0),
      revoked: String(data.revoked || 0),
    };
  },

  /**
   * Get recent activity (requires auth)
   * Backend returns: { data: [] }
   */
  getActivity: async (limit = 20) => {
    const response = await api.get(`/api/v2/dashboard/activity?limit=${limit}`);
    return response.data || [];
  },

  /**
   * Get expiring certificates (requires auth)
   * Backend returns: { data: [{ id, subject, valid_to, descr, refid }] }
   * Frontend needs: [{ name, type, issuer, expiresIn, daysLeft, fingerprint }]
   */
  getExpiringCerts: async (limit = 10) => {
    const response = await api.get(`/api/v2/dashboard/expiring-certs?limit=${limit}`);
    const certs = response.data || [];
    
    // Transform backend format to frontend format
    return certs.map(cert => {
      const validTo = new Date(cert.valid_to);
      const now = new Date();
      const daysLeft = Math.ceil((validTo - now) / (1000 * 60 * 60 * 24));
      
      // Extract CN from subject
      const cnMatch = cert.subject.match(/CN=([^,]+)/);
      const name = cnMatch ? cnMatch[1] : cert.descr || 'Unknown';
      
      // Determine type based on subject or description
      let type = 'Server';
      if (cert.descr && cert.descr.toLowerCase().includes('acme')) {
        type = 'ACME';
      } else if (cert.subject.includes('CN=Users')) {
        type = 'User';
      } else if (cert.descr && cert.descr.toLowerCase().includes('ca')) {
        type = 'CA';
      }
      
      // Extract issuer (simplified)
      const issuerMatch = cert.subject.match(/O=([^,]+)/);
      const issuer = issuerMatch ? issuerMatch[1] : 'Self-signed';
      
      return {
        id: cert.id,
        name: name,
        type: type,
        issuer: issuer,
        expiresIn: daysLeft > 0 ? `${daysLeft} days` : 'Expired',
        daysLeft: daysLeft,
        fingerprint: cert.refid || '',
        validTo: cert.valid_to,
      };
    });
  },
};
