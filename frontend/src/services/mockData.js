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

/**
 * Certificate Authorities
 */
export function getCAs() {
  return [
    // Root CAs
    { id: 1, name: 'ACME Root CA', type: 'root', status: 'active', validUntil: '2036-01-15', certificates: 3, parent: null },
    { id: 2, name: 'ACME Root CA v2', type: 'root', status: 'active', validUntil: '2038-06-20', certificates: 2, parent: null },
    { id: 3, name: 'Legacy Root CA', type: 'root', status: 'expired', validUntil: '2020-12-31', certificates: 0, parent: null },
    
    // Intermediate CAs (ACME Root CA children)
    { id: 4, name: 'ACME Intermediate CA', type: 'intermediate', status: 'active', validUntil: '2031-01-15', certificates: 85, parent: 1 },
    { id: 5, name: 'Production Intermediate CA', type: 'intermediate', status: 'active', validUntil: '2032-03-20', certificates: 124, parent: 1 },
    { id: 6, name: 'Staging Intermediate CA', type: 'intermediate', status: 'active', validUntil: '2030-11-10', certificates: 38, parent: 1 },
    
    // Intermediate CAs (ACME Root CA v2 children)
    { id: 7, name: 'Development CA', type: 'intermediate', status: 'active', validUntil: '2033-06-20', certificates: 45, parent: 2 },
    { id: 8, name: 'Testing CA', type: 'intermediate', status: 'active', validUntil: '2033-06-20', certificates: 22, parent: 2 },
    
    // Sub-intermediate CAs
    { id: 9, name: 'Web Server CA', type: 'intermediate', status: 'active', validUntil: '2029-01-15', certificates: 62, parent: 4 },
    { id: 10, name: 'Email CA', type: 'intermediate', status: 'active', validUntil: '2029-01-15', certificates: 18, parent: 4 },
    { id: 11, name: 'Code Signing CA', type: 'intermediate', status: 'active', validUntil: '2028-03-20', certificates: 5, parent: 5 },
    { id: 12, name: 'VPN CA', type: 'intermediate', status: 'active', validUntil: '2028-11-10', certificates: 12, parent: 6 },
  ];
}

/**
 * Certificates
 */
export function getCertificates() {
  const cas = ['ACME Intermediate CA', 'Production Intermediate CA', 'Web Server CA', 'Email CA', 'VPN CA'];
  const statuses = ['valid', 'valid', 'valid', 'expiring', 'expired', 'revoked'];
  const keySizes = ['2048', '4096'];
  const algorithms = ['RSA', 'ECDSA'];
  
  const certs = [];
  const domains = [
    'api.acme.com', 'www.acme.com', 'mail.acme.com', 'vpn.acme.com', 'db.acme.com',
    'staging.acme.com', 'dev.acme.com', 'test.acme.com', 'admin.acme.com', 'portal.acme.com',
    'smtp.acme.com', 'imap.acme.com', 'ldap.acme.com', 'monitoring.acme.com', 'backup.acme.com',
    '*.prod.acme.com', '*.staging.acme.com', '*.dev.acme.com', 'old.acme.com', 'legacy.acme.com',
  ];
  
  for (let i = 0; i < 50; i++) {
    const validFrom = new Date(2024, Math.floor(Math.random() * 12), Math.floor(Math.random() * 28) + 1);
    const validUntil = new Date(validFrom);
    validUntil.setFullYear(validUntil.getFullYear() + 2);
    
    certs.push({
      id: i + 1,
      commonName: i < domains.length ? domains[i] : `server${i}.acme.com`,
      ca: cas[Math.floor(Math.random() * cas.length)],
      validFrom: validFrom.toISOString().split('T')[0],
      validUntil: validUntil.toISOString().split('T')[0],
      status: statuses[Math.floor(Math.random() * statuses.length)],
      keySize: keySizes[Math.floor(Math.random() * keySizes.length)],
      algorithm: algorithms[Math.floor(Math.random() * algorithms.length)],
      serialNumber: Math.random().toString(16).substring(2, 18).toUpperCase(),
    });
  }
  
  return certs;
}

/**
 * Certificate Signing Requests
 */
export function getCSRs() {
  return {
    pending: [
      { id: 1, commonName: 'newapi.acme.com', requestedBy: 'operator', requestedAt: '2026-01-20 14:30', keySize: '4096', status: 'pending' },
      { id: 2, commonName: 'app.acme.com', requestedBy: 'developer', requestedAt: '2026-01-20 10:15', keySize: '2048', status: 'pending' },
      { id: 3, commonName: 'secure.acme.com', requestedBy: 'admin', requestedAt: '2026-01-19 16:45', keySize: '4096', status: 'pending' },
      { id: 4, commonName: 'internal.acme.com', requestedBy: 'operator', requestedAt: '2026-01-19 09:20', keySize: '2048', status: 'pending' },
      { id: 5, commonName: 'gateway.acme.com', requestedBy: 'netadmin', requestedAt: '2026-01-18 15:10', keySize: '4096', status: 'pending' },
      { id: 6, commonName: 'proxy.acme.com', requestedBy: 'operator', requestedAt: '2026-01-18 11:30', keySize: '2048', status: 'pending' },
      { id: 7, commonName: 'cdn.acme.com', requestedBy: 'developer', requestedAt: '2026-01-17 14:20', keySize: '2048', status: 'pending' },
      { id: 8, commonName: 'cache.acme.com', requestedBy: 'operator', requestedAt: '2026-01-17 08:40', keySize: '4096', status: 'pending' },
      { id: 9, commonName: 'queue.acme.com', requestedBy: 'developer', requestedAt: '2026-01-16 13:15', keySize: '2048', status: 'pending' },
      { id: 10, commonName: 'worker.acme.com', requestedBy: 'operator', requestedAt: '2026-01-16 10:05', keySize: '4096', status: 'pending' },
    ],
    approved: [
      { id: 11, commonName: 'api.acme.com', requestedBy: 'admin', requestedAt: '2026-01-15 12:00', keySize: '4096', status: 'approved', approvedBy: 'admin', approvedAt: '2026-01-15 12:30' },
      { id: 12, commonName: 'mail.acme.com', requestedBy: 'operator', requestedAt: '2026-01-14 10:30', keySize: '2048', status: 'approved', approvedBy: 'admin', approvedAt: '2026-01-14 11:00' },
      { id: 13, commonName: 'vpn.acme.com', requestedBy: 'netadmin', requestedAt: '2026-01-13 15:20', keySize: '4096', status: 'approved', approvedBy: 'admin', approvedAt: '2026-01-13 16:00' },
      { id: 14, commonName: 'db.acme.com', requestedBy: 'dba', requestedAt: '2026-01-12 09:15', keySize: '4096', status: 'approved', approvedBy: 'security', approvedAt: '2026-01-12 10:00' },
      { id: 15, commonName: 'smtp.acme.com', requestedBy: 'operator', requestedAt: '2026-01-11 14:45', keySize: '2048', status: 'approved', approvedBy: 'admin', approvedAt: '2026-01-11 15:00' },
      { id: 16, commonName: 'ldap.acme.com', requestedBy: 'admin', requestedAt: '2026-01-10 11:20', keySize: '4096', status: 'approved', approvedBy: 'security', approvedAt: '2026-01-10 12:00' },
      { id: 17, commonName: 'monitoring.acme.com', requestedBy: 'operator', requestedAt: '2026-01-09 16:30', keySize: '2048', status: 'approved', approvedBy: 'admin', approvedAt: '2026-01-09 17:00' },
      { id: 18, commonName: 'backup.acme.com', requestedBy: 'admin', requestedAt: '2026-01-08 13:10', keySize: '4096', status: 'approved', approvedBy: 'admin', approvedAt: '2026-01-08 14:00' },
      { id: 19, commonName: 'storage.acme.com', requestedBy: 'operator', requestedAt: '2026-01-07 10:40', keySize: '2048', status: 'approved', approvedBy: 'security', approvedAt: '2026-01-07 11:00' },
      { id: 20, commonName: 'files.acme.com', requestedBy: 'developer', requestedAt: '2026-01-06 15:25', keySize: '2048', status: 'approved', approvedBy: 'admin', approvedAt: '2026-01-06 16:00' },
      { id: 21, commonName: 'share.acme.com', requestedBy: 'operator', requestedAt: '2026-01-05 12:50', keySize: '4096', status: 'approved', approvedBy: 'admin', approvedAt: '2026-01-05 13:00' },
      { id: 22, commonName: 'wiki.acme.com', requestedBy: 'developer', requestedAt: '2026-01-04 09:35', keySize: '2048', status: 'approved', approvedBy: 'security', approvedAt: '2026-01-04 10:00' },
      { id: 23, commonName: 'docs.acme.com', requestedBy: 'operator', requestedAt: '2026-01-03 14:15', keySize: '2048', status: 'approved', approvedBy: 'admin', approvedAt: '2026-01-03 15:00' },
      { id: 24, commonName: 'blog.acme.com', requestedBy: 'marketing', requestedAt: '2026-01-02 11:05', keySize: '2048', status: 'approved', approvedBy: 'admin', approvedAt: '2026-01-02 12:00' },
      { id: 25, commonName: 'shop.acme.com', requestedBy: 'ecommerce', requestedAt: '2026-01-01 16:40', keySize: '4096', status: 'approved', approvedBy: 'security', approvedAt: '2026-01-01 17:00' },
    ],
    rejected: [
      { id: 26, commonName: 'invalid-cn', requestedBy: 'test-user', requestedAt: '2025-12-30 10:20', keySize: '1024', status: 'rejected', rejectedBy: 'security', rejectedAt: '2025-12-30 11:00', reason: 'Invalid common name format' },
      { id: 27, commonName: 'weak.acme.com', requestedBy: 'developer', requestedAt: '2025-12-28 14:30', keySize: '1024', status: 'rejected', rejectedBy: 'security', rejectedAt: '2025-12-28 15:00', reason: 'Key size too small (minimum 2048)' },
      { id: 28, commonName: 'external.example.com', requestedBy: 'operator', requestedAt: '2025-12-25 09:15', keySize: '2048', status: 'rejected', rejectedBy: 'admin', rejectedAt: '2025-12-25 10:00', reason: 'Domain not authorized' },
      { id: 29, commonName: 'duplicate.acme.com', requestedBy: 'developer', requestedAt: '2025-12-20 13:45', keySize: '2048', status: 'rejected', rejectedBy: 'admin', rejectedAt: '2025-12-20 14:00', reason: 'Certificate already exists' },
      { id: 30, commonName: 'test123.acme.com', requestedBy: 'test-user', requestedAt: '2025-12-15 11:30', keySize: '2048', status: 'rejected', rejectedBy: 'security', rejectedAt: '2025-12-15 12:00', reason: 'Insufficient permissions' },
    ],
  };
}

/**
 * Certificate Templates
 */
export function getTemplates() {
  return [
    {
      id: 1,
      name: 'Web Server',
      icon: 'globe',
      type: 'webserver',
      description: 'TLS certificates for web servers (HTTPS)',
      keyUsage: ['Digital Signature', 'Key Encipherment'],
      extKeyUsage: ['Server Authentication'],
      certificatesIssued: 124,
      defaultValidity: 825, // days
    },
    {
      id: 2,
      name: 'Email Protection',
      icon: 'envelope',
      type: 'email',
      description: 'S/MIME certificates for email encryption and signing',
      keyUsage: ['Digital Signature', 'Key Encipherment'],
      extKeyUsage: ['Email Protection'],
      certificatesIssued: 32,
      defaultValidity: 730,
    },
    {
      id: 3,
      name: 'Code Signing',
      icon: 'code',
      type: 'codesigning',
      description: 'Certificates for signing software and scripts',
      keyUsage: ['Digital Signature'],
      extKeyUsage: ['Code Signing'],
      certificatesIssued: 8,
      defaultValidity: 1095,
    },
    {
      id: 4,
      name: 'VPN Client',
      icon: 'shield-check',
      type: 'vpn',
      description: 'Client certificates for VPN authentication',
      keyUsage: ['Digital Signature', 'Key Agreement'],
      extKeyUsage: ['Client Authentication'],
      certificatesIssued: 45,
      defaultValidity: 365,
    },
    {
      id: 5,
      name: 'User Authentication',
      icon: 'user-circle',
      type: 'user',
      description: 'Personal certificates for user authentication',
      keyUsage: ['Digital Signature'],
      extKeyUsage: ['Client Authentication'],
      certificatesIssued: 28,
      defaultValidity: 365,
    },
    {
      id: 6,
      name: 'OCSP Signing',
      icon: 'seal-check',
      type: 'ocsp',
      description: 'Certificates for OCSP responder signing',
      keyUsage: ['Digital Signature'],
      extKeyUsage: ['OCSP Signing'],
      certificatesIssued: 3,
      defaultValidity: 365,
    },
    {
      id: 7,
      name: 'Document Signing',
      icon: 'file-text',
      type: 'document',
      description: 'Certificates for PDF and document signing',
      keyUsage: ['Digital Signature', 'Non Repudiation'],
      extKeyUsage: ['Document Signing'],
      certificatesIssued: 12,
      defaultValidity: 730,
    },
    {
      id: 8,
      name: 'Time Stamping',
      icon: 'clock',
      type: 'timestamp',
      description: 'Certificates for trusted timestamping services',
      keyUsage: ['Digital Signature'],
      extKeyUsage: ['Time Stamping'],
      certificatesIssued: 2,
      defaultValidity: 1095,
    },
  ];
}

/**
 * CRL Statistics
 */
export function getCRLStats() {
  return {
    totalCRLs: 12,
    totalRevocations: 47,
    lastGenerated: '2026-01-21 06:00:00',
    cas: [
      { id: 1, name: 'ACME Root CA', crlSize: '2.3 KB', revocations: 0, lastGenerated: '2026-01-21 06:00', nextUpdate: '2026-02-21 06:00' },
      { id: 4, name: 'ACME Intermediate CA', crlSize: '8.7 KB', revocations: 12, lastGenerated: '2026-01-21 06:00', nextUpdate: '2026-02-21 06:00' },
      { id: 5, name: 'Production Intermediate CA', crlSize: '15.2 KB', revocations: 23, lastGenerated: '2026-01-21 06:00', nextUpdate: '2026-02-21 06:00' },
      { id: 9, name: 'Web Server CA', crlSize: '6.1 KB', revocations: 8, lastGenerated: '2026-01-21 06:00', nextUpdate: '2026-02-21 06:00' },
      { id: 11, name: 'Code Signing CA', crlSize: '1.2 KB', revocations: 1, lastGenerated: '2026-01-21 06:00', nextUpdate: '2026-02-21 06:00' },
    ],
  };
}

/**
 * OCSP Statistics
 */
export function getOCSPStats() {
  return {
    requests24h: 1847,
    requestsTotal: 45629,
    avgResponseTime: '12ms',
    cacheHitRate: '87%',
    responderStatus: 'active',
    responderUrl: 'http://ocsp.acme.com',
    lastRestart: '2026-01-15 10:30:00',
  };
}
