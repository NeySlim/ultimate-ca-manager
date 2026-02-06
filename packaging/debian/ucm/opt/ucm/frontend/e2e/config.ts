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
  
  // Keycloak SSO
  keycloak: {
    url: process.env.KEYCLOAK_URL || 'http://pve:8180',
    realm: 'ucm',
    clientId: 'ucm-app',
    clientSecret: 'ucm-secret-key-2024',
    testUsers: {
      alice: { username: 'alice', password: 'alice123', role: 'admin' },
      bob: { username: 'bob', password: 'bob123', role: 'operator' },
      charlie: { username: 'charlie', password: 'charlie123', role: 'auditor' },
    },
  },
  
  // LDAP
  ldap: {
    host: process.env.LDAP_HOST || 'pve',
    port: 389,
    baseDN: 'dc=ucm,dc=test',
    bindDN: 'cn=admin,dc=ucm,dc=test',
    bindPassword: 'admin123',
    testUsers: ['alice', 'bob', 'charlie', 'david', 'eve'],
    testGroups: ['admins', 'operators', 'auditors', 'developers', 'external'],
  },
  
  // SoftHSM
  hsm: {
    module: '/usr/lib/softhsm/libsofthsm2.so',
    tokenLabel: 'UCM-Test',
    pin: '87654321',
    soPin: '12345678',
    testKeys: ['ucm-ca-key', 'ucm-root-key'],
  },
  
  // Timeouts
  timeouts: {
    short: 5000,
    medium: 10000,
    long: 30000,
  },
}

export type TestConfig = typeof config
