/**
 * Extended Key Usage (EKU) Service
 */
import { apiClient } from './apiClient'

export const ekuService = {
  /** Return the catalog of well-known EKU OIDs / labels. */
  async getKnown() {
    return apiClient.get('/eku/known')
  },
}
