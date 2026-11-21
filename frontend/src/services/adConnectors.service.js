/**
 * Active Directory connectors: one stored LDAP connection per directory.
 */
import { apiClient } from './apiClient'

export const adConnectorsService = {
  list: () =>
    apiClient.get('/ad-connectors'),

  get: (id) =>
    apiClient.get(`/ad-connectors/${id}`),

  create: (data) =>
    apiClient.post('/ad-connectors', data),

  update: (id, data) =>
    apiClient.put(`/ad-connectors/${id}`, data),

  remove: (id) =>
    apiClient.delete(`/ad-connectors/${id}`),

  // Test the saved connector; records the verdict and the domain SID on its row
  testSaved: (id) =>
    apiClient.post(`/ad-connectors/${id}/test`),

  // Test form values; `id` lets a blank password fall back to the saved one for the same target
  test: (data) =>
    apiClient.post('/ad-connectors/test', data),
}
