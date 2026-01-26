import { api } from '../../../core/api/client';

export const settingsService = {
  async getGeneral() {
    return await api.get('/settings/general');
  },

  async updateGeneral(data) {
    return await api.patch('/settings/general', data);
  },

  async getDbStats() {
    return await api.get('/system/db/stats');
  },

  async optimizeDb() {
    return await api.post('/system/db/optimize');
  },

  async integrityCheck() {
    return await api.post('/system/db/integrity-check');
  },

  async getBackupList() {
    return await api.get('/system/backup/list');
  },

  async createBackup(password) {
    return await api.post('/system/backup/create', { password });
  },

  async restoreBackup(filename) {
    return await api.post('/system/backup/restore', { filename });
  },
};
