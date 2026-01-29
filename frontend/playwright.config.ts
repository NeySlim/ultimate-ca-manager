import { defineConfig, devices } from '@playwright/test'

/**
 * UCM E2E Test Configuration
 * 
 * Environment variables:
 *   UCM_BASE_URL - UCM application URL (default: https://localhost:8443)
 *   UCM_PRO - Enable Pro features tests (default: true)
 *   KEYCLOAK_URL - Keycloak SSO URL (default: http://pve:8180)
 *   LDAP_HOST - LDAP server host (default: pve)
 */

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false, // Run sequentially for login state
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: [
    ['html', { open: 'never' }],
    ['list']
  ],
  
  use: {
    baseURL: process.env.UCM_BASE_URL || 'https://localhost:8443',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    ignoreHTTPSErrors: true, // Self-signed certs
    actionTimeout: 10000,
    navigationTimeout: 30000,
  },

  projects: [
    // Setup project - runs first to authenticate
    {
      name: 'setup',
      testMatch: /.*\.setup\.ts/,
    },
    
    // Main tests with authenticated state
    {
      name: 'chromium',
      use: { 
        ...devices['Desktop Chrome'],
        storageState: 'e2e/.auth/user.json',
      },
      dependencies: ['setup'],
    },
    
    // Pro features tests
    {
      name: 'pro-features',
      testMatch: /pro\/.*\.spec\.ts/,
      use: { 
        ...devices['Desktop Chrome'],
        storageState: 'e2e/.auth/user.json',
      },
      dependencies: ['setup'],
    },
  ],

  // Web server - start dev server before tests
  // webServer: {
  //   command: 'npm run dev',
  //   url: 'http://localhost:5173',
  //   reuseExistingServer: !process.env.CI,
  // },
})
