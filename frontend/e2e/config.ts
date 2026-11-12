/**
 * UCM E2E Test Configuration
 */

export const config = {
  // UCM Application
  baseURL: process.env.UCM_BASE_URL || 'https://localhost:8443',
  credentials: {
    username: process.env.UCM_USER || 'admin',
    // UCM has no default password: the one provided to the instance, or its generated one
    password: process.env.UCM_PASSWORD || '',
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
