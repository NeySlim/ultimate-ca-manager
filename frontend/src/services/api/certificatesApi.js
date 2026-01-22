/**
 * Certificates API Service
 */
import api from './api';

export const certificatesApi = {
  /**
   * Get all certificates with pagination and filters
   * Backend returns: { data: [...], meta: { page, per_page, total } }
   * Backend fields: id, serial, subject, issuer, valid_from, valid_to, revoked, revoked_at
   * Transform to frontend format
   */
  getAll: async (params = {}) => {
    const response = await api.get('/api/v2/certificates', { params });
    
    // Transform backend data to frontend format
    const transformedData = (response.data || []).map(cert => {
      // Calculate expiry status
      const expiryDate = new Date(cert.valid_to);
      const now = new Date();
      const daysLeft = Math.ceil((expiryDate - now) / (1000 * 60 * 60 * 24));
      
      // Determine status
      let status = 'ACTIVE';
      if (cert.revoked) {
        status = 'REVOKED';
      } else if (daysLeft < 0) {
        status = 'EXPIRED';
      } else if (daysLeft <= 7) {
        status = 'CRITICAL';
      } else if (daysLeft <= 30) {
        status = 'EXPIRING SOON';
      }
      
      // Extract CN from subject for name
      const cnMatch = cert.subject?.match(/CN=([^,]+)/);
      const name = cnMatch ? cnMatch[1] : cert.subject || 'Unnamed Certificate';
      
      // Determine certificate type (simplified - backend might need to provide this)
      const type = cert.subject?.includes('Server') ? 'Server' : 'Client';
      
      return {
        id: cert.id,
        name: name,
        serial: cert.serial || 'N/A',
        type: type,
        issuer: cert.issuer || 'Unknown',
        status: status,
        issued: cert.valid_from ? cert.valid_from.split('T')[0] : 'N/A',
        expires: cert.valid_to ? cert.valid_to.split('T')[0] : 'N/A',
        daysLeft: daysLeft > 0 ? daysLeft : 0,
        // Keep original data
        _raw: cert,
      };
    });
    
    return {
      data: transformedData,
      meta: response.meta || { page: 1, per_page: 20, total: transformedData.length },
    };
  },

  /**
   * Get single certificate
   */
  getById: async (id) => {
    const response = await api.get(`/api/v2/certificates/${id}`);
    return response.data;
  },

  /**
   * Revoke certificate
   */
  revoke: async (id, reason) => {
    const response = await api.post(`/api/v2/certificates/${id}/revoke`, { reason });
    return response.data;
  },

  /**
   * Renew certificate
   */
  renew: async (id) => {
    const response = await api.post(`/api/v2/certificates/${id}/renew`);
    return response.data;
  },

  /**
   * Download certificate
   */
  download: async (id, format = 'pem') => {
    const response = await api.get(`/api/v2/certificates/${id}/download`, {
      params: { format },
      responseType: 'blob',
    });
    return response;
  },
};
