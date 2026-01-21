/**
 * Mock Data Services
 * Provides realistic data for UI development and testing
 */

/**
 * Dashboard Statistics
 */
export function getDashboardStats() {
  return {
    cas: {
      value: 12,
      label: 'Certificate Authorities',
      icon: 'tree-structure',
      trend: '+2',
    },
    certificates: {
      value: 247,
      label: 'Active Certificates',
      icon: 'certificate',
      trend: '+15',
    },
    acmeOrders: {
      value: 38,
      label: 'ACME Orders',
      icon: 'globe',
      trend: '-3',
    },
    users: {
      value: 8,
      label: 'Users',
      icon: 'users',
      trend: '+1',
    },
  };
}

/**
 * Recent Activity (Dashboard)
 */
export function getRecentActivity() {
  return [
    { icon: 'certificate', text: 'Certificate issued for api.acme.com', time: '2 minutes ago', user: 'admin', gradient: true },
    { icon: 'user-plus', text: 'New user account created: john.doe', time: '5 minutes ago', user: 'admin', variant: 'success' },
    { icon: 'seal-check', text: 'CA "ACME Intermediate CA" created', time: '12 minutes ago', user: 'admin', gradient: true },
    { icon: 'file-text', text: 'CSR approved for mail.acme.com', time: '18 minutes ago', user: 'operator', gradient: true },
    { icon: 'warning', text: 'Certificate expiring soon: old.acme.com', time: '25 minutes ago', variant: 'warning' },
    { icon: 'globe', text: 'ACME order completed for *.staging.acme.com', time: '32 minutes ago', user: 'acme-bot', gradient: true },
    { icon: 'shield-check', text: 'Trust store synchronized with Mozilla', time: '45 minutes ago', user: 'system', variant: 'success' },
    { icon: 'certificate', text: 'Certificate renewed for vpn.acme.com', time: '1 hour ago', user: 'admin', gradient: true },
    { icon: 'x-circle', text: 'Certificate revoked: compromised.acme.com', time: '1 hour ago', user: 'security', variant: 'danger' },
    { icon: 'device-mobile', text: 'SCEP enrollment request from iPhone-12345', time: '2 hours ago', user: 'scep-service', gradient: true },
    { icon: 'user', text: 'User login: operator', time: '2 hours ago', variant: 'info' },
    { icon: 'gear', text: 'System settings updated', time: '3 hours ago', user: 'admin', variant: 'info' },
    { icon: 'certificate', text: 'Certificate issued for db.acme.com', time: '3 hours ago', user: 'admin', gradient: true },
    { icon: 'files', text: 'Certificate template "Web Server" updated', time: '4 hours ago', user: 'admin', variant: 'info' },
    { icon: 'list-checks', text: 'CRL regenerated for ACME Root CA', time: '5 hours ago', user: 'system', gradient: true },
    { icon: 'upload', text: 'CA imported from OPNsense', time: '6 hours ago', user: 'admin', gradient: true },
    { icon: 'certificate', text: 'Certificate issued for smtp.acme.com', time: '7 hours ago', user: 'admin', gradient: true },
    { icon: 'check-circle', text: 'Database integrity check passed', time: '8 hours ago', user: 'system', variant: 'success' },
    { icon: 'database', text: 'Database backup completed', time: '10 hours ago', user: 'system', variant: 'success' },
    { icon: 'sign-out', text: 'User logout: operator', time: '12 hours ago', variant: 'info' },
  ];
}

/**
 * Expiring Certificates
 */
export function getExpiringCertificates() {
  return [
    { id: 1, name: 'old.acme.com', ca: 'ACME Root CA', expires: '2026-02-15', status: 'expiring', daysLeft: 25 },
    { id: 2, name: 'legacy-api.acme.com', ca: 'ACME Intermediate CA', expires: '2026-02-20', status: 'expiring', daysLeft: 30 },
    { id: 3, name: 'test.acme.com', ca: 'ACME Root CA', expires: '2026-02-10', status: 'expiring', daysLeft: 20 },
    { id: 4, name: 'staging.acme.com', ca: 'ACME Intermediate CA', expires: '2026-02-25', status: 'expiring', daysLeft: 35 },
    { id: 5, name: 'dev-vpn.acme.com', ca: 'ACME Root CA', expires: '2026-02-12', status: 'expiring', daysLeft: 22 },
  ];
}

/**
 * Application Logs
 */
export function getApplicationLogs() {
  return [
    { icon: 'user', text: 'User login: admin', time: '5 minutes ago', variant: 'success' },
    { icon: 'gear', text: 'SMTP settings updated', time: '15 minutes ago', user: 'admin', variant: 'info' },
    { icon: 'user-plus', text: 'New user created: jane.smith', time: '30 minutes ago', user: 'admin', variant: 'success' },
    { icon: 'warning', text: 'Failed login attempt from 192.168.1.50', time: '45 minutes ago', variant: 'warning' },
    { icon: 'shield-check', text: 'Two-factor authentication enabled', time: '1 hour ago', user: 'operator', variant: 'success' },
    { icon: 'database', text: 'Database backup completed successfully', time: '2 hours ago', user: 'system', variant: 'success' },
    { icon: 'sign-out', text: 'User logout: operator', time: '3 hours ago', variant: 'info' },
    { icon: 'gear', text: 'Email notification settings updated', time: '4 hours ago', user: 'admin', variant: 'info' },
    { icon: 'key', text: 'API key generated for monitoring service', time: '5 hours ago', user: 'admin', variant: 'info' },
    { icon: 'user', text: 'Password changed for user: john.doe', time: '6 hours ago', user: 'john.doe', variant: 'info' },
    { icon: 'x-circle', text: 'User account locked: suspicious.user', time: '8 hours ago', user: 'security', variant: 'danger' },
    { icon: 'database', text: 'Database optimization completed', time: '10 hours ago', user: 'system', variant: 'success' },
    { icon: 'user', text: 'User login: operator', time: '12 hours ago', variant: 'success' },
    { icon: 'gear', text: 'LDAP integration configured', time: '1 day ago', user: 'admin', variant: 'info' },
    { icon: 'check-circle', text: 'System health check passed', time: '1 day ago', user: 'system', variant: 'success' },
    { icon: 'user-minus', text: 'User account deleted: old.account', time: '2 days ago', user: 'admin', variant: 'warning' },
    { icon: 'database', text: 'Database restored from backup', time: '2 days ago', user: 'admin', variant: 'warning' },
    { icon: 'gear', text: 'Webhook endpoint configured', time: '3 days ago', user: 'admin', variant: 'info' },
    { icon: 'sign-out', text: 'User logout: admin', time: '3 days ago', variant: 'info' },
    { icon: 'user', text: 'User login: admin', time: '3 days ago', variant: 'success' },
  ];
}

/**
 * PKI Operations
 */
export function getPKIOperations() {
  return [
    { icon: 'certificate', text: 'Certificate issued for api.acme.com', time: '2 minutes ago', user: 'admin', gradient: true },
    { icon: 'seal-check', text: 'CA "Production Intermediate CA" created', time: '10 minutes ago', user: 'admin', gradient: true },
    { icon: 'file-text', text: 'CSR approved for mail.acme.com', time: '20 minutes ago', user: 'operator', gradient: true },
    { icon: 'globe', text: 'ACME order completed for *.staging.acme.com', time: '35 minutes ago', user: 'acme-bot', gradient: true },
    { icon: 'certificate', text: 'Certificate renewed for vpn.acme.com', time: '1 hour ago', user: 'admin', gradient: true },
    { icon: 'x-circle', text: 'Certificate revoked: compromised.acme.com', time: '1 hour ago', user: 'security', gradient: true },
    { icon: 'device-mobile', text: 'SCEP enrollment completed for iPhone-12345', time: '2 hours ago', user: 'scep-service', gradient: true },
    { icon: 'certificate', text: 'Certificate issued for db.acme.com', time: '3 hours ago', user: 'admin', gradient: true },
    { icon: 'files', text: 'Certificate template "Web Server" applied', time: '4 hours ago', user: 'admin', gradient: true },
    { icon: 'list-checks', text: 'CRL regenerated for ACME Root CA', time: '5 hours ago', user: 'system', gradient: true },
    { icon: 'upload', text: 'CA imported from OPNsense firewall', time: '6 hours ago', user: 'admin', gradient: true },
    { icon: 'certificate', text: 'Certificate issued for smtp.acme.com', time: '7 hours ago', user: 'admin', gradient: true },
    { icon: 'file-text', text: 'CSR rejected: invalid common name', time: '8 hours ago', user: 'security', gradient: true },
    { icon: 'globe', text: 'ACME authorization validated for domain.acme.com', time: '10 hours ago', user: 'acme-bot', gradient: true },
    { icon: 'seal-check', text: 'Root CA "ACME Root CA v2" created', time: '12 hours ago', user: 'admin', gradient: true },
    { icon: 'certificate', text: 'Certificate issued for ldap.acme.com', time: '1 day ago', user: 'admin', gradient: true },
    { icon: 'shield-check', text: 'Trust anchor added to trust store', time: '1 day ago', user: 'admin', gradient: true },
    { icon: 'device-mobile', text: 'SCEP enrollment request from Android-67890', time: '2 days ago', user: 'scep-service', gradient: true },
    { icon: 'certificate', text: 'Certificate issued for monitoring.acme.com', time: '2 days ago', user: 'admin', gradient: true },
    { icon: 'list-checks', text: 'OCSP responder status updated', time: '3 days ago', user: 'system', gradient: true },
  ];
}
