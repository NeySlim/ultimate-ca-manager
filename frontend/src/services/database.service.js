/**
 * Database Admin Service
 * Manage backend (SQLite ↔ PostgreSQL): status, test, switch, migrate.
 */
import { apiClient } from './apiClient'

export const databaseService = {
  async getStatus() {
    return apiClient.get('/database/status')
  },

  async testConnection(databaseUrl) {
    return apiClient.post('/database/test', { database_url: databaseUrl })
  },

  async switchBackend(databaseUrl) {
    return apiClient.post('/database/switch', { database_url: databaseUrl })
  },

  async migrateData(databaseUrl) {
    return apiClient.post('/database/migrate', { database_url: databaseUrl })
  },
}
