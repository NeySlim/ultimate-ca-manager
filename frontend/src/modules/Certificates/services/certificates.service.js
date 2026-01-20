import { api } from '../../../core/api/client';

// Extended Mock Data with detailed certificate information
const MOCK_CERTS = [
  {
    id: 1,
    name: 'api.example.com',
    commonName: 'api.example.com',
    serial: 'A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0',
    issuer: 'Example Root CA',
    issuedDate: '2024-05-15',
    expiryDate: '2025-05-15',
    modified: '2025-05-15',
    algorithm: 'RSA 2048',
    keySize: 2048,
    version: 'v3',
    ca: 'Example Root CA',
    status: 'Valid',
    icon: 'cert',
    thumbprint: 'A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0',
    subject: {
      commonName: 'api.example.com',
      organization: 'Example Corp',
      unit: 'IT Department',
      country: 'US',
      state: 'California',
      locality: 'San Francisco',
      altNames: ['api.example.com', 'api-v2.example.com'],
    },
    issuerDetails: {
      commonName: 'Example Root CA',
      organization: 'Example Corp',
      country: 'US',
    },
    extensions: [
      { name: 'Basic Constraints', value: 'CA:FALSE', critical: true },
      { name: 'Key Usage', value: 'digitalSignature, keyEncipherment', critical: true },
      { name: 'Extended Key Usage', value: 'serverAuth, clientAuth', critical: false },
      { name: 'Subject Key Identifier', value: 'A1:B2:C3:D4:E5:F6:G7:H8', critical: false },
    ],
    pem: `-----BEGIN CERTIFICATE-----
MIID7TCCAtSgAwIBAgIJAKsXK1F8L9ZCMA0GCSqGSIb3DQEBCwUAMH8xCzAJBgNV
BAYTAlVTMQswCQYDVQQIDAJDQTESMBAGA1UEBwwJU2FuIEZyYW5jMRYwFAYDVQQK
DA1FeGFtcGxlIENvcnAuMRYwFAYDVQQLDA1JVCBEZXBHCBFDHAQGA1UEAwwVRXhh
bXBsZSBSb290IENBIHYyLjAgMB4XDTE5MDkxNDEzNTIxNloXDTI0MDkxMzEzNTIx
NlowYjELMAkGA1UEBhMCVVMxCzAJBgNVBAgMAkNBMRIwEAYDVQQHDAlTYW4gRnJh
bmNpc2NvMRYwFAYDVQQKDA1FeGFtcGxlIENvcnAuMRswGQYDVQQDDBJhcGkuZXhh
bXBsZS5jb20wggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQDUH5/dU1Nz
-----END CERTIFICATE-----`,
  },
  {
    id: 2,
    name: 'web.app.com',
    commonName: 'web.app.com',
    serial: 'B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0A1',
    issuer: 'LetsEncrypt CA',
    issuedDate: '2024-01-20',
    expiryDate: '2025-01-20',
    modified: '2025-01-20',
    algorithm: 'RSA 2048',
    keySize: 2048,
    version: 'v3',
    ca: 'LetsEncrypt CA',
    status: 'Warning',
    icon: 'cert',
    thumbprint: 'B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0A1',
    subject: {
      commonName: 'web.app.com',
      organization: 'Web App Inc',
      unit: 'Security',
      country: 'US',
      state: 'New York',
      locality: 'New York',
      altNames: ['web.app.com', 'www.web.app.com'],
    },
    issuerDetails: {
      commonName: 'LetsEncrypt CA',
      organization: 'LetsEncrypt',
      country: 'US',
    },
    extensions: [
      { name: 'Basic Constraints', value: 'CA:FALSE', critical: true },
      { name: 'Key Usage', value: 'digitalSignature, keyEncipherment', critical: true },
      { name: 'Extended Key Usage', value: 'serverAuth', critical: false },
    ],
    pem: `-----BEGIN CERTIFICATE-----
MIIDpTCCAY2gAwIBAgIULvJq5aZ7ZpZL5XZ6S0JrHvkwggEiMA0GCSqGSIb3DQEB
-----END CERTIFICATE-----`,
  },
  {
    id: 3,
    name: 'mail.srv.com',
    commonName: 'mail.srv.com',
    serial: 'C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0A1B2',
    issuer: 'Internal CA',
    issuedDate: '2024-08-10',
    expiryDate: '2025-08-10',
    modified: '2025-08-10',
    algorithm: 'RSA 4096',
    keySize: 4096,
    version: 'v3',
    ca: 'Internal CA',
    status: 'Valid',
    icon: 'cert',
    thumbprint: 'C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0A1B2',
    subject: {
      commonName: 'mail.srv.com',
      organization: 'Mail Services',
      unit: 'Operations',
      country: 'US',
      state: 'Texas',
      locality: 'Austin',
      altNames: ['mail.srv.com', 'smtp.srv.com', 'imap.srv.com'],
    },
    issuerDetails: {
      commonName: 'Internal CA',
      organization: 'Internal CA Org',
      country: 'US',
    },
    extensions: [
      { name: 'Basic Constraints', value: 'CA:FALSE', critical: true },
      { name: 'Key Usage', value: 'digitalSignature, keyEncipherment', critical: true },
    ],
    pem: `-----BEGIN CERTIFICATE-----
MIIE7TCCAlagAwIBAgIJAKsXK1F8L9PoMA0GCSqGSIb3DQEBCwUAMH8xCzAJBgNV
-----END CERTIFICATE-----`,
  },
  {
    id: 4,
    name: 'vpn.gateway.lan',
    commonName: 'vpn.gateway.lan',
    serial: 'D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0A1B2C3',
    issuer: 'Internal CA',
    issuedDate: '2023-12-01',
    expiryDate: '2024-12-01',
    modified: '2024-12-01',
    algorithm: 'EC P-256',
    keySize: 256,
    version: 'v3',
    ca: 'Internal CA',
    status: 'Expired',
    icon: 'lock',
    thumbprint: 'D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0A1B2C3',
    subject: {
      commonName: 'vpn.gateway.lan',
      organization: 'VPN Services',
      unit: 'Network',
      country: 'US',
      state: 'Florida',
      locality: 'Miami',
    },
    issuerDetails: {
      commonName: 'Internal CA',
      organization: 'Internal CA Org',
      country: 'US',
    },
    extensions: [
      { name: 'Basic Constraints', value: 'CA:FALSE', critical: true },
      { name: 'Key Usage', value: 'digitalSignature, keyEncipherment', critical: true },
    ],
    pem: `-----BEGIN CERTIFICATE-----
MIIB8TCCAZgCCQC6V7Y9h5Y3qjAKBggqhkjOPQQDAjB+MQswCQYDVQQGEwJVUzEL
-----END CERTIFICATE-----`,
  },
  {
    id: 5,
    name: 'ldap.corp.internal',
    commonName: 'ldap.corp.internal',
    serial: 'E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0A1B2C3D4',
    issuer: 'Corporate CA',
    issuedDate: '2025-03-01',
    expiryDate: '2025-09-01',
    modified: '2025-03-01',
    algorithm: 'RSA 2048',
    keySize: 2048,
    version: 'v3',
    ca: 'Corporate CA',
    status: 'Valid',
    icon: 'cert',
    thumbprint: 'E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0A1B2C3D4',
    subject: {
      commonName: 'ldap.corp.internal',
      organization: 'Corporate',
      unit: 'Infrastructure',
      country: 'US',
      state: 'Illinois',
      locality: 'Chicago',
    },
    issuerDetails: {
      commonName: 'Corporate CA',
      organization: 'Corporate',
      country: 'US',
    },
    extensions: [
      { name: 'Basic Constraints', value: 'CA:FALSE', critical: true },
      { name: 'Key Usage', value: 'digitalSignature, keyEncipherment', critical: true },
    ],
    pem: `-----BEGIN CERTIFICATE-----
MIIDXTCCAkWgAwIBAgIJAKsXK1F8L9P+MA0GCSqGSIb3DQEBCwUAMEUxCzAJBgNV
-----END CERTIFICATE-----`,
  },
];

export const CertificateService = {
  getAll: async () => {
    try {
      const response = await api.get('/certificates');
      // If API returns empty list (Phase 1 backend stub), use mock data for demo
      if (Array.isArray(response) && response.length === 0) {
          return MOCK_CERTS;
      }
      if (response && response.data && Array.isArray(response.data) && response.data.length === 0) {
          return MOCK_CERTS;
      }
      return response.data || response;
    } catch (e) {
      console.warn('API fetch failed, using mock data');
      return MOCK_CERTS;
    }
  },

  getById: async (id) => {
    try {
      return await api.get(`/certificates/${id}`);
    } catch (e) {
      console.warn('API fetch failed, using mock data');
      const cert = MOCK_CERTS.find(c => c.id === parseInt(id));
      if (!cert) throw new Error('Certificate not found');
      return cert;
    }
  },

  getStats: async () => {
    // Mock stats
    return {
      total: 1248,
      expiring: 5,
      revoked: 2,
    };
  },

  revoke: async (id) => {
    try {
      return await api.post(`/certificates/${id}/revoke`);
    } catch (e) {
      console.error('Failed to revoke certificate', e);
      throw e;
    }
  },

  renew: async (id) => {
    try {
      return await api.post(`/certificates/${id}/renew`);
    } catch (e) {
      console.error('Failed to renew certificate', e);
      throw e;
    }
  },

  download: async (id) => {
    try {
      return await api.get(`/certificates/${id}/download`);
    } catch (e) {
      console.error('Failed to download certificate', e);
      throw e;
    }
  },
};
