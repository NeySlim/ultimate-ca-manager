import { api } from '../../../core/api/client';

// Mock Data as fallback
const MOCK_CERTS = [
  { id: 1, name: 'api.example.com', modified: '2025-05-15', algo: 'RSA 2048', expiresIn: '245 days', status: 'Valid', icon: 'cert' },
  { id: 2, name: 'web.app.com', modified: '2025-01-20', algo: 'RSA 2048', expiresIn: '45 days', status: 'Warning', icon: 'cert' },
  { id: 3, name: 'mail.srv.com', modified: '2025-08-10', algo: 'RSA 4096', expiresIn: '320 days', status: 'Valid', icon: 'cert' },
  { id: 4, name: 'vpn.gateway.lan', modified: '2024-12-01', algo: 'EC P-256', expiresIn: '-5 days', status: 'Error', icon: 'lock' },
  { id: 5, name: 'ldap.corp.internal', modified: '2025-03-01', algo: 'RSA 2048', expiresIn: '180 days', status: 'Valid', icon: 'cert' },
];

export const CertificateService = {
  getAll: async () => {
    try {
      return await api.get('/certificates');
    } catch (e) {
      console.warn('API fetch failed, using mock data');
      return MOCK_CERTS;
    }
  },

  getStats: async () => {
      // Mock stats
      return {
          total: 1248,
          expiring: 5,
          revoked: 2
      };
  }
};
