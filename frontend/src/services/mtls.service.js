/**
 * mTLS Service - Client certificate authentication API
 */
import { apiClient, buildQueryString } from './apiClient'

export const mtlsService = {
  // Settings
  getSettings: () => apiClient.get('/mtls/settings'),
  updateSettings: (data) => apiClient.put('/mtls/settings', data),

  // Certificates
  listCertificates: () => apiClient.get('/mtls/certificates'),
  createCertificate: (data) => apiClient.post('/mtls/certificates', data),
  revokeCertificate: (id) => apiClient.delete(`/mtls/certificates/${id}`),
  downloadCertificate: (id, format = 'pem') =>
    apiClient.get(`/mtls/certificates/${id}/download${buildQueryString({ format })}`),
}
