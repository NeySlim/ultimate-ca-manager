/**
 * UCM E2E Test Configuration
 */

export const config = {
  // UCM Application
  baseURL: process.env.UCM_BASE_URL || 'https://localhost:8443',
  credentials: {
    username: process.env.UCM_USER || 'admin',
    password: process.env.UCM_PASSWORD || 'changeme123',
  },
  
  // Pro features enabled
  isPro: process.env.UCM_PRO !== 'false',
  
  // Timeouts
  timeouts: {
    short: 5000,
    medium: 10000,
    long: 30000,
  },
}

export type TestConfig = typeof config
