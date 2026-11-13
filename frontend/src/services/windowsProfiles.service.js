/**
 * Windows enrollment profiles: one realm each, served by XCEP, WSTEP and Kerberos.
 * The collection routes only; the shared switches and SPN live under /settings.
 */
import { apiClient, buildQueryString } from './apiClient'

export const windowsProfilesService = {
  // Server-side page and filters: q (name or realm), ca (refid), state
  list: (params = {}) =>
    apiClient.get(`/windows-profiles${buildQueryString(params)}`),

  get: (id) =>
    apiClient.get(`/windows-profiles/${id}`),

  create: (data) =>
    apiClient.post('/windows-profiles', data),

  update: (id, data) =>
    apiClient.put(`/windows-profiles/${id}`, data),

  remove: (id) =>
    apiClient.delete(`/windows-profiles/${id}`),

  // dryRun lists the entries by realm and stores nothing
  uploadKeytab: (id, file, { dryRun = false } = {}) => {
    const formData = new FormData()
    formData.append('file', file)
    if (dryRun) formData.append('dry_run', '1')
    return apiClient.upload(`/windows-profiles/${id}/keytab`, formData)
  },

  getSettings: () =>
    apiClient.get('/windows-profiles/settings'),

  updateSettings: (data) =>
    apiClient.patch('/windows-profiles/settings', data),
}
