import { apiClient } from './apiClient'

const ssoService = {
  getProviders: () =>
    apiClient.get('/sso/providers'),

  getProvider: (id) =>
    apiClient.get(`/sso/providers/${id}`),

  createProvider: (data) =>
    apiClient.post('/sso/providers', data),

  updateProvider: (id, data) =>
    apiClient.put(`/sso/providers/${id}`, data),

  deleteProvider: (id) =>
    apiClient.delete(`/sso/providers/${id}`),

  toggleProvider: (id) =>
    apiClient.post(`/sso/providers/${id}/toggle`),

  testProvider: (id) =>
    apiClient.post(`/sso/providers/${id}/test`),

  testMapping: (id, username) =>
    apiClient.post(`/sso/providers/${id}/test-mapping`, { username }),

  fetchIdpMetadata: (metadataUrl, sslOptions = {}) =>
    apiClient.post('/sso/saml/metadata/fetch', { metadata_url: metadataUrl, ...sslOptions }),

  getSessions: () =>
    apiClient.get('/sso/sessions'),

  getSamlCertificates: () =>
    apiClient.get('/sso/saml/certificates'),

  getSamlSpInfo: () =>
    apiClient.get('/sso/saml/sp-info'),
}

export { ssoService }
