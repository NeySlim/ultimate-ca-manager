/**
 * Page component of each registry module, lazy so the registry stays light.
 * A key here without a registry entry, or the reverse, fails the registry test.
 */
import { lazy } from 'react'

// Auto-reload on chunk load failure (stale cache after update)
export function lazyWithRetry(importFn) {
  return lazy(() => importFn().catch(() => {
    // Chunk failed to load (likely 404 after update): reload once
    const key = 'chunk_reload'
    if (!sessionStorage.getItem(key)) {
      sessionStorage.setItem(key, '1')
      window.location.reload()
    }
    sessionStorage.removeItem(key)
    return importFn()
  }))
}

export const pages = {
  dashboard: lazyWithRetry(() => import('../pages/DashboardPage')),
  certificates: lazyWithRetry(() => import('../pages/CertificatesPage')),
  'user-certificates': lazyWithRetry(() => import('../pages/UserCertificatesPage')),
  cas: lazyWithRetry(() => import('../pages/CAsPage')),
  csrs: lazyWithRetry(() => import('../pages/CSRsPage')),
  templates: lazyWithRetry(() => import('../pages/TemplatesPage')),
  users: lazyWithRetry(() => import('../pages/UsersGroupsPage')),
  acme: lazyWithRetry(() => import('../pages/ACMEPage')),
  scep: lazyWithRetry(() => import('../pages/SCEPPage')),
  est: lazyWithRetry(() => import('../pages/ESTPage')),
  tsa: lazyWithRetry(() => import('../pages/TSAPage')),
  settings: lazyWithRetry(() => import('../pages/SettingsPage')),
  audit: lazyWithRetry(() => import('../pages/AuditLogsPage')),
  logs: lazyWithRetry(() => import('../pages/SystemLogsPage')),
  operations: lazyWithRetry(() => import('../pages/OperationsPage')),
  tools: lazyWithRetry(() => import('../pages/CertificateToolsPage')),
  account: lazyWithRetry(() => import('../pages/AccountPage')),
  'crl-ocsp': lazyWithRetry(() => import('../pages/CRLOCSPPage')),
  truststore: lazyWithRetry(() => import('../pages/TrustStorePage')),
  rbac: lazyWithRetry(() => import('../pages/RBACPage')),
  hsm: lazyWithRetry(() => import('../pages/HSMPage')),
  policies: lazyWithRetry(() => import('../pages/PoliciesPage')),
  approvals: lazyWithRetry(() => import('../pages/ApprovalsPage')),
  keyRecovery: lazyWithRetry(() => import('../pages/KeyRecoveryPage')),
  reports: lazyWithRetry(() => import('../pages/ReportsPage')),
  discovery: lazyWithRetry(() => import('../pages/DiscoveryPage')),
  'ssh-cas': lazyWithRetry(() => import('../pages/SSHCAsPage')),
  'ssh-certificates': lazyWithRetry(() => import('../pages/SSHCertificatesPage')),
}
