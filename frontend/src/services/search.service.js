/**
 * Search Service - Global search across all entities
 */
import { apiClient, buildQueryString } from './apiClient'

export const searchService = {
  /**
   * Global search across certificates, CAs, users, templates, CSRs
   * @param {string} query - Search query (min 2 chars)
   * @param {number} limit - Max results per category (default 5)
   * @returns {Promise<{certificates: [], cas: [], users: [], templates: [], csrs: []}>}
   */
  async globalSearch(query, limit = 5) {
    if (!query || query.length < 2) {
      return {
        certificates: [],
        cas: [],
        users: [],
        templates: [],
        csrs: []
      }
    }
    
    return apiClient.get(`/search${buildQueryString({ q: query, limit })}`)
  }
}
