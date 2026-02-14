/**
 * Help content for all UCM pages — v2.1.0
 * Each entry: { title, subtitle, overview, sections[], tips[], warnings[], related[] }
 * Section: { title, icon, content?, items?[], definitions?[], example? }
 * Item: string | { label, text }
 */

import {
  TreeStructure, Certificate, FileText, ClockCounterClockwise,
  ShieldCheck, Key, Users, Gear, Database, Lock, Globe,
  ListChecks, CloudArrowUp, HardDrive, UsersFour, Fingerprint,
  ArrowClockwise, Wrench, Stack, Robot
} from '@phosphor-icons/react'

export const helpContent = {

  // ===== DASHBOARD =====
  dashboard: {
    title: 'Dashboard',
    subtitle: 'System overview and monitoring',
    overview: 'Real-time overview of your PKI infrastructure. Widgets display certificate status, expiry alerts, system health, and recent activity. The layout is fully customizable with drag-and-drop.',
    sections: [
      {
        title: 'Widgets',
        icon: ListChecks,
        items: [
          { label: 'Statistics', text: 'Total CAs, active certificates, pending CSRs, and expiring soon counts' },
          { label: 'Certificate Trend', text: 'Issuance history chart over time' },
          { label: 'Status Distribution', text: 'Pie chart breakdown: valid / expiring / expired / revoked' },
          { label: 'Next Expiry', text: 'Certificates expiring within 30 days' },
          { label: 'System Status', text: 'Service health, uptime, ACME / SCEP / CRL / OCSP status' },
          { label: 'Recent Activity', text: 'Latest operations across the system' },
          { label: 'Recent Certificates', text: 'Recently issued or imported certificates' },
          { label: 'Certificate Authorities', text: 'CA list with chain information' },
          { label: 'ACME Accounts', text: 'Registered ACME client accounts' },
        ]
      },
    ],
    tips: [
      'Drag widgets to rearrange your dashboard layout',
      'Click the eye icon in the header to show/hide specific widgets',
      'The dashboard updates in real-time via WebSocket — no manual refresh needed',
      'Layout is saved per-user and persists across sessions',
    ],
    related: ['Certificates', 'CAs', 'Settings']
  },

  // ===== CERTIFICATE AUTHORITIES =====
  cas: {
    title: 'Certificate Authorities',
    subtitle: 'Manage your PKI hierarchy',
    overview: 'Create and manage Root and Intermediate Certificate Authorities. Build a complete trust chain for your organization. CAs with private keys can sign certificates directly.',
    sections: [
      {
        title: 'Views',
        icon: TreeStructure,
        items: [
          { label: 'Tree View', text: 'Hierarchical display showing parent-child CA relationships' },
          { label: 'List View', text: 'Flat table view with sorting and filtering' },
          { label: 'Org View', text: 'Grouped by organization for multi-tenant setups' },
        ]
      },
      {
        title: 'Actions',
        icon: Certificate,
        items: [
          { label: 'Create Root CA', text: 'Self-signed top-level authority' },
          { label: 'Create Intermediate', text: 'CA signed by a parent CA in the chain' },
          { label: 'Import CA', text: 'Import existing CA certificate (with or without private key)' },
          { label: 'Export', text: 'PEM, DER, or PKCS#12 (P12/PFX) with password protection' },
          { label: 'Renew CA', text: 'Re-issue the CA certificate with a new validity period' },
          { label: 'Chain Repair', text: 'Fix broken parent-child relationships automatically' },
        ]
      },
    ],
    tips: [
      'CAs with a key icon (🔑) have a private key and can sign certificates',
      'Use intermediate CAs for day-to-day signing, keep root CA offline when possible',
      'PKCS#12 export includes the full chain and is ideal for backup',
    ],
    warnings: [
      'Deleting a CA will NOT revoke certificates it has issued — revoke them first',
      'Private keys are stored encrypted; losing the database means losing the keys',
    ],
    related: ['Certificates', 'Templates', 'CRL/OCSP']
  },

  // ===== CERTIFICATES =====
  certificates: {
    title: 'Certificates',
    subtitle: 'Issue, manage, and monitor certificates',
    overview: 'Central management for all X.509 certificates. Issue new certificates from your CAs, import existing ones, track expiry dates, and handle renewals and revocations.',
    sections: [
      {
        title: 'Certificate Status',
        icon: Certificate,
        definitions: [
          { term: 'Valid', description: 'Within validity period and not revoked' },
          { term: 'Expiring', description: 'Will expire within 30 days' },
          { term: 'Expired', description: 'Past the "Not After" date' },
          { term: 'Revoked', description: 'Explicitly revoked (published in CRL)' },
          { term: 'Orphan', description: 'Issuing CA no longer exists in the system' },
        ]
      },
      {
        title: 'Actions',
        icon: Key,
        items: [
          { label: 'Issue', text: 'Create a new certificate signed by one of your CAs' },
          { label: 'Import', text: 'Import an existing certificate (PEM, DER, or PKCS#12)' },
          { label: 'Renew', text: 'Re-issue with the same subject and a new validity period' },
          { label: 'Revoke', text: 'Mark as revoked — will appear in CRL' },
          { label: 'Revoke & Replace', text: 'Revoke and immediately issue a replacement' },
          { label: 'Export', text: 'Download in PEM, DER, or PKCS#12 format' },
          { label: 'Compare', text: 'Side-by-side comparison of two certificates' },
        ]
      },
    ],
    tips: [
      'Star ⭐ important certificates to add them to your favorites list',
      'Use filters to quickly find certificates by status, CA, or search text',
      'Renewing preserves the same subject but generates a new key pair',
    ],
    warnings: [
      'Revocation is permanent — a revoked certificate cannot be un-revoked',
      'Deleting a certificate removes it from UCM but does not revoke it',
    ],
    related: ['CAs', 'CSRs', 'Templates', 'CRL/OCSP']
  },

  // ===== CSRs =====
  csrs: {
    title: 'Certificate Signing Requests',
    subtitle: 'Manage CSR workflow',
    overview: 'Upload, review, and sign Certificate Signing Requests. CSRs allow external systems to request certificates from your CAs without exposing private keys.',
    sections: [
      {
        title: 'Workflow',
        icon: FileText,
        items: [
          { label: 'Upload CSR', text: 'Accept PEM-encoded CSR files or paste PEM text' },
          { label: 'Review', text: 'Inspect subject, SANs, key type, and signature before signing' },
          { label: 'Sign', text: 'Select a CA, set validity period, and issue the certificate' },
          { label: 'Download', text: 'Download the original CSR in PEM format' },
        ]
      },
      {
        title: 'Tabs',
        icon: ListChecks,
        items: [
          { label: 'Pending', text: 'CSRs awaiting review and signing' },
          { label: 'History', text: 'Previously signed or rejected CSRs' },
        ]
      },
    ],
    tips: [
      'CSRs preserve the requester\'s private key — it never leaves their system',
      'You can add a private key to a CSR after signing if needed for PKCS#12 export',
    ],
    related: ['Certificates', 'CAs', 'Templates']
  },

  // ===== TEMPLATES =====
  templates: {
    title: 'Certificate Templates',
    subtitle: 'Reusable certificate profiles',
    overview: 'Define reusable certificate profiles with pre-configured subject fields, key usage, extended key usage, validity periods, and other extensions. Apply templates when issuing or signing certificates.',
    sections: [
      {
        title: 'Template Types',
        icon: FileText,
        definitions: [
          { term: 'End-Entity', description: 'For server, client, code signing, and email certificates' },
          { term: 'CA', description: 'For creating intermediate Certificate Authorities' },
        ]
      },
      {
        title: 'Features',
        icon: Gear,
        items: [
          { label: 'Subject Defaults', text: 'Pre-fill Organization, OU, Country, State, City' },
          { label: 'Key Usage', text: 'Digital Signature, Key Encipherment, etc.' },
          { label: 'Extended Key Usage', text: 'Server Auth, Client Auth, Code Signing, Email Protection' },
          { label: 'Validity', text: 'Default validity period in days' },
          { label: 'Duplicate', text: 'Clone an existing template and modify it' },
          { label: 'Import/Export', text: 'Share templates as JSON files between UCM instances' },
        ]
      },
    ],
    tips: [
      'Create separate templates for TLS servers, clients, and code signing',
      'Use the Duplicate action to quickly create variations of a template',
    ],
    related: ['Certificates', 'CSRs', 'CAs']
  },

  // ===== CRL/OCSP =====
  crlocsp: {
    title: 'CRL & OCSP',
    subtitle: 'Certificate revocation services',
    overview: 'Manage Certificate Revocation Lists (CRL) and Online Certificate Status Protocol (OCSP) services. These services allow clients to verify whether a certificate has been revoked.',
    sections: [
      {
        title: 'CRL Management',
        icon: ClockCounterClockwise,
        items: [
          { label: 'Auto-Regeneration', text: 'Toggle automatic CRL regeneration per CA' },
          { label: 'Manual Regenerate', text: 'Force CRL regeneration immediately' },
          { label: 'Download CRL', text: 'Download the CRL file in DER or PEM format' },
          { label: 'CDP URL', text: 'CRL Distribution Point URL to embed in certificates' },
        ]
      },
      {
        title: 'OCSP Service',
        icon: Globe,
        items: [
          { label: 'Status', text: 'Indicates whether the OCSP responder is active' },
          { label: 'AIA URL', text: 'Authority Information Access URL for certificates' },
          { label: 'Cache Hit Rate', text: 'Percentage of OCSP queries served from cache' },
          { label: 'Total Queries', text: 'Number of OCSP requests processed' },
        ]
      },
    ],
    tips: [
      'Enable auto-regeneration to keep CRLs fresh after certificate revocations',
      'Copy CDP and AIA URLs to embed them in your certificate profiles',
      'OCSP provides real-time revocation checking and is preferred over CRL',
    ],
    related: ['Certificates', 'CAs']
  },

  // ===== SCEP =====
  scep: {
    title: 'SCEP',
    subtitle: 'Simple Certificate Enrollment Protocol',
    overview: 'SCEP enables network devices (routers, switches, firewalls) and MDM solutions to automatically request and obtain certificates. Devices authenticate using a challenge password.',
    sections: [
      {
        title: 'Tabs',
        icon: ListChecks,
        items: [
          { label: 'Requests', text: 'Pending, approved, and rejected SCEP enrollment requests' },
          { label: 'Configuration', text: 'SCEP server settings: CA selection, CA identifier, auto-approve' },
          { label: 'Challenge Passwords', text: 'Manage per-CA challenge passwords for device enrollment' },
          { label: 'Information', text: 'SCEP endpoint URLs and integration instructions' },
        ]
      },
      {
        title: 'Configuration',
        icon: Gear,
        items: [
          { label: 'Signing CA', text: 'Select which CA signs SCEP-enrolled certificates' },
          { label: 'Auto-Approve', text: 'Automatically approve requests with valid challenge passwords' },
          { label: 'Challenge Password', text: 'Shared secret that devices use to authenticate enrollment' },
        ]
      },
    ],
    tips: [
      'Use unique challenge passwords per CA for better security auditing',
      'Auto-approve is convenient but review requests manually in high-security environments',
      'SCEP URL format: https://your-server:port/scep',
    ],
    warnings: [
      'Challenge passwords are transmitted in the SCEP request — use HTTPS for transport security',
    ],
    related: ['Certificates', 'CAs']
  },

  // ===== ACME =====
  acme: {
    title: 'ACME',
    subtitle: 'Automated Certificate Management',
    overview: 'UCM supports two ACME modes: Let\'s Encrypt client for public certificates, and Local ACME server for internal PKI automation. The local ACME server supports multi-CA domain mapping.',
    sections: [
      {
        title: "Let's Encrypt",
        icon: Globe,
        items: [
          { label: 'Client', text: 'Request public certificates from Let\'s Encrypt via ACME protocol' },
          { label: 'DNS Providers', text: 'Configure DNS-01 challenge providers (Cloudflare, Route53, etc.)' },
          { label: 'Domains', text: 'Map domains to DNS providers for automatic validation' },
        ]
      },
      {
        title: 'Local ACME Server',
        icon: HardDrive,
        items: [
          { label: 'Configuration', text: 'Enable/disable the built-in ACME server, select default CA' },
          { label: 'Local Domains', text: 'Map internal domains to specific CAs for multi-CA issuance' },
          { label: 'Accounts', text: 'View and manage registered ACME client accounts' },
          { label: 'History', text: 'Track all ACME certificate issuance orders' },
        ]
      },
      {
        title: 'Multi-CA Resolution',
        icon: TreeStructure,
        content: 'When an ACME client requests a certificate, UCM resolves the signing CA in this order:',
        items: [
          '1. Local Domain mapping — exact domain match, then parent domain',
          '2. DNS Domain mapping — checks the issuing CA configured for the DNS provider',
          '3. Global default — the CA set in ACME server configuration',
          '4. First available CA with a private key',
        ]
      },
    ],
    tips: [
      'ACME directory URL: https://your-server:port/acme/directory',
      'Use Local Domains to assign different CAs to different internal domains',
      'Any CA with a private key can be selected as the issuing CA',
      'Wildcard domains (*.example.com) require DNS-01 validation for Let\'s Encrypt',
    ],
    warnings: [
      "Let's Encrypt requires domain validation — your server must be reachable or DNS configured",
    ],
    related: ['Certificates', 'CAs', 'DNS Providers']
  },

  // ===== TRUST STORE =====
  truststore: {
    title: 'Trust Store',
    subtitle: 'Manage trusted certificates',
    overview: 'Import and manage trusted root and intermediate CA certificates. The trust store is used for chain validation and can be synchronized with the operating system trust store.',
    sections: [
      {
        title: 'Certificate Types',
        icon: ShieldCheck,
        definitions: [
          { term: 'Root CA', description: 'Self-signed top-level trust anchor' },
          { term: 'Intermediate', description: 'CA certificate signed by a root or another intermediate' },
          { term: 'Client Auth', description: 'Certificate used for client authentication (mTLS)' },
          { term: 'Code Signing', description: 'Certificate used for code signature verification' },
          { term: 'Custom', description: 'Manually categorized trusted certificate' },
        ]
      },
      {
        title: 'Actions',
        icon: CloudArrowUp,
        items: [
          { label: 'Import File', text: 'Upload PEM, DER, or PKCS#7 certificate files' },
          { label: 'Import URL', text: 'Fetch a certificate from a remote URL' },
          { label: 'Add PEM', text: 'Paste PEM-encoded certificate text directly' },
          { label: 'Sync from System', text: 'Import OS trusted CAs into UCM' },
          { label: 'Export', text: 'Download trusted certificates individually' },
        ]
      },
    ],
    tips: [
      'Use "Sync from System" to quickly populate the trust store with OS-level CAs',
      'Filter by purpose to focus on specific certificate categories',
    ],
    related: ['CAs', 'Certificates']
  },

  // ===== USERS & GROUPS =====
  usersGroups: {
    title: 'Users & Groups',
    subtitle: 'Identity and access management',
    overview: 'Manage user accounts and group memberships. Assign roles to control access to UCM features. Groups allow bulk permission management for teams.',
    sections: [
      {
        title: 'Users',
        icon: Users,
        items: [
          { label: 'Create User', text: 'Add a new user with username, email, and initial password' },
          { label: 'Roles', text: 'Assign system or custom roles to control permissions' },
          { label: 'Status', text: 'Enable or disable user accounts' },
          { label: 'Password Reset', text: 'Reset a user\'s password (admin action)' },
          { label: 'API Keys', text: 'Manage per-user API keys for programmatic access' },
        ]
      },
      {
        title: 'Groups',
        icon: UsersFour,
        items: [
          { label: 'Create Group', text: 'Define a group and assign members' },
          { label: 'Role Inheritance', text: 'Groups can inherit roles — all members get group permissions' },
          { label: 'Member Management', text: 'Add or remove users from groups' },
        ]
      },
    ],
    tips: [
      'Use groups to manage permissions for teams rather than individual users',
      'Disabled users cannot log in but their data is preserved',
    ],
    warnings: [
      'Deleting a user is permanent — consider disabling instead',
    ],
    related: ['RBAC', 'Audit Logs', 'Settings']
  },

  // ===== RBAC =====
  rbac: {
    title: 'Role-Based Access Control',
    subtitle: 'Fine-grained permission management',
    overview: 'Define custom roles with granular permissions. System roles (Admin, Operator, Viewer) are built-in. Custom roles let you control exactly which operations each user can perform.',
    sections: [
      {
        title: 'System Roles',
        icon: ShieldCheck,
        definitions: [
          { term: 'Admin', description: 'Full access to all features and settings' },
          { term: 'Operator', description: 'Can manage certificates and CAs but not system settings' },
          { term: 'Viewer', description: 'Read-only access to certificates and CAs' },
        ]
      },
      {
        title: 'Custom Roles',
        icon: Key,
        items: [
          { label: 'Create Role', text: 'Define a new role with a name and description' },
          { label: 'Permission Matrix', text: 'Check/uncheck permissions by category (CAs, Certs, Users, etc.)' },
          { label: 'Coverage', text: 'Visual percentage of total permissions granted to the role' },
          { label: 'User Count', text: 'See how many users are assigned to each role' },
        ]
      },
    ],
    tips: [
      'Follow the principle of least privilege — grant only necessary permissions',
      'System roles cannot be modified or deleted',
      'Toggle entire categories on/off for quick role setup',
    ],
    related: ['Users & Groups', 'Audit Logs']
  },

  // ===== AUDIT LOGS =====
  auditLogs: {
    title: 'Audit Logs',
    subtitle: 'Activity tracking and compliance',
    overview: 'Complete audit trail of all operations performed in UCM. Track who did what, when, and from where. Supports filtering, search, export, and integrity verification.',
    sections: [
      {
        title: 'Filters',
        icon: ListChecks,
        items: [
          { label: 'Action Type', text: 'Filter by operation type (create, update, delete, login, etc.)' },
          { label: 'User', text: 'Filter by the user who performed the action' },
          { label: 'Status', text: 'Show only successful or failed operations' },
          { label: 'Date Range', text: 'Set from/to dates to narrow the time window' },
          { label: 'Search', text: 'Free-text search across all log entries' },
        ]
      },
      {
        title: 'Actions',
        icon: Database,
        items: [
          { label: 'Export', text: 'Download logs in JSON or CSV format' },
          { label: 'Cleanup', text: 'Purge old logs with configurable retention (days)' },
          { label: 'Verify Integrity', text: 'Check log chain integrity to detect tampering' },
        ]
      },
    ],
    tips: [
      'Export logs regularly for compliance and archival purposes',
      'Failed login attempts are logged with source IP for security monitoring',
      'Log entries include User Agent for identifying client applications',
    ],
    warnings: [
      'Log cleanup is irreversible — exported data cannot be re-imported',
    ],
    related: ['Settings', 'Users & Groups', 'RBAC']
  },

  // ===== SETTINGS =====
  settings: {
    title: 'Settings',
    subtitle: 'System configuration',
    overview: 'Configure all aspects of the UCM system. Settings are organized by category: general, appearance, email, security, SSO, backup, audit, database, HTTPS, updates, and webhooks.',
    sections: [
      {
        title: 'Categories',
        icon: Gear,
        items: [
          { label: 'General', text: 'Instance name, hostname, and system-wide defaults' },
          { label: 'Appearance', text: 'Theme selection (light/dark/system), accent color, desktop mode' },
          { label: 'Email (SMTP)', text: 'SMTP server, port, credentials for email notifications' },
          { label: 'Security', text: 'Password policies, session timeout, rate limiting, IP restrictions' },
          { label: 'SSO', text: 'SAML and OIDC single sign-on integration' },
          { label: 'Backup', text: 'Manual and scheduled database backups' },
          { label: 'Audit', text: 'Log retention, syslog forwarding, integrity verification' },
          { label: 'Database', text: 'Database path, size, and migration status' },
          { label: 'HTTPS', text: 'TLS certificate for the UCM web interface' },
          { label: 'Updates', text: 'Check for new versions and view changelog' },
          { label: 'Webhooks', text: 'HTTP webhooks for certificate events (issue, revoke, expire)' },
        ]
      },
    ],
    tips: [
      'Use the System Status widget at the top to quickly check service health',
      'Test SMTP settings before relying on email notifications',
      'Schedule automatic backups for production environments',
    ],
    warnings: [
      'Changing the HTTPS certificate requires a service restart',
      'Modifying security settings may lock out users — verify access before saving',
    ],
    related: ['Users & Groups', 'Audit Logs', 'Account']
  },

  // ===== ACCOUNT =====
  account: {
    title: 'My Account',
    subtitle: 'Personal settings and security',
    overview: 'Manage your profile, security settings, and API keys. Enable two-factor authentication and register security keys for enhanced account protection.',
    sections: [
      {
        title: 'Profile',
        icon: Users,
        items: [
          { label: 'Full Name', text: 'Your display name shown across the application' },
          { label: 'Email', text: 'Used for notifications and account recovery' },
          { label: 'Account Info', text: 'Creation date, last login, total login count' },
        ]
      },
      {
        title: 'Security',
        icon: Lock,
        items: [
          { label: 'Password', text: 'Change your current password' },
          { label: '2FA (TOTP)', text: 'Enable time-based one-time passwords via authenticator app' },
          { label: 'Security Keys', text: 'Register WebAuthn/FIDO2 keys (YubiKey, fingerprint, etc.)' },
          { label: 'mTLS', text: 'Manage client certificates for mutual TLS authentication' },
        ]
      },
      {
        title: 'API Keys',
        icon: Key,
        items: [
          { label: 'Create Key', text: 'Generate a new API key with optional expiration' },
          { label: 'Permissions', text: 'API keys inherit your role permissions' },
          { label: 'Revoke', text: 'Immediately invalidate an API key' },
        ]
      },
    ],
    tips: [
      'Enable at least one second factor (TOTP or Security Key) for admin accounts',
      'API keys can be scoped with an expiration date for short-lived integrations',
      'Scan the QR code with any TOTP app: Google Authenticator, Authy, 1Password, etc.',
    ],
    related: ['Settings', 'Users & Groups']
  },

  // ===== IMPORT/EXPORT =====
  importExport: {
    title: 'Import & Export',
    subtitle: 'Data migration and backup',
    overview: 'Import certificates from external sources and export your PKI data. Smart Import auto-detects file types. OPNsense integration allows direct sync with your firewall.',
    sections: [
      {
        title: 'Import',
        icon: CloudArrowUp,
        items: [
          { label: 'Smart Import', text: 'Upload any certificate file — UCM auto-detects format (PEM, DER, P12, P7B)' },
          { label: 'OPNsense Sync', text: 'Connect to OPNsense firewall and import its certificates and CAs' },
        ]
      },
      {
        title: 'Export',
        icon: Database,
        items: [
          { label: 'Export Certificates', text: 'Bulk download certificates as PEM or PKCS#7 bundle' },
          { label: 'Export CAs', text: 'Bulk download CA certificates and chains' },
        ]
      },
      {
        title: 'OPNsense Integration',
        icon: Globe,
        items: [
          { label: 'Connection', text: 'Provide OPNsense URL, API key, and API secret' },
          { label: 'Test Connection', text: 'Verify connectivity before importing' },
          { label: 'Select Items', text: 'Choose which certificates and CAs to import' },
        ]
      },
    ],
    tips: [
      'Smart Import handles PEM bundles with multiple certificates in a single file',
      'Test the OPNsense connection before running a full import',
      'PKCS#12 files require the correct password to import private keys',
    ],
    related: ['Certificates', 'CAs', 'Operations']
  },

  // ===== CERTIFICATE TOOLS =====
  certTools: {
    title: 'Certificate Tools',
    subtitle: 'Decode, convert, and verify certificates',
    overview: 'A suite of tools for working with certificates, CSRs, and keys. Decode certificates to inspect their contents, convert between formats, check remote SSL endpoints, and verify key matches.',
    sections: [
      {
        title: 'Available Tools',
        icon: Wrench,
        items: [
          { label: 'SSL Checker', text: 'Connect to a remote host and inspect its SSL/TLS certificate chain' },
          { label: 'CSR Decoder', text: 'Paste a CSR in PEM format to view its subject, SANs, and key info' },
          { label: 'Certificate Decoder', text: 'Paste a certificate in PEM format to inspect all fields' },
          { label: 'Key Matcher', text: 'Verify that a certificate, CSR, and private key belong together' },
          { label: 'Converter', text: 'Convert between PEM, DER, PKCS#12, and PKCS#7 formats' },
        ]
      },
      {
        title: 'Converter Details',
        icon: ArrowClockwise,
        items: [
          'PEM ↔ DER conversion',
          'PEM → PKCS#12 with password and full chain',
          'PKCS#12 → PEM extraction',
          'PEM → PKCS#7 (P7B) chain bundling',
        ]
      },
    ],
    tips: [
      'SSL Checker supports custom ports — use it to check any TLS service',
      'Key Matcher compares modulus hashes to verify matching pairs',
      'Converter preserves the full certificate chain when creating PKCS#12',
    ],
    related: ['Certificates', 'CSRs', 'Import/Export']
  },

  // ===== OPERATIONS =====
  operations: {
    title: 'Operations',
    subtitle: 'Import, export & bulk actions',
    overview: 'Centralized operations center. Import certificates from files or OPNsense, export bundles in PEM/P7B formats, and perform bulk actions across all resource types with inline search and filters.',
    sections: [
      {
        title: 'Sidebar Tabs',
        icon: Stack,
        items: [
          { label: 'Import', text: 'Smart Import with automatic format detection, plus OPNsense sync to pull certificates from firewalls' },
          { label: 'Export', text: 'Download certificate bundles per resource type in PEM or P7B format via action cards' },
          { label: 'Bulk Actions', text: 'Select a resource type and perform batch operations on multiple items' },
        ]
      },
      {
        title: 'Bulk Actions',
        icon: ListChecks,
        items: [
          { label: 'Certificates', text: 'Revoke, renew, delete, or export — filter by status and issuing CA' },
          { label: 'CAs', text: 'Delete or export certificate authorities' },
          { label: 'CSRs', text: 'Sign with a CA or delete pending requests' },
          { label: 'Templates', text: 'Delete certificate templates' },
          { label: 'Users', text: 'Delete user accounts' },
        ]
      },
    ],
    tips: [
      'Use the resource chips to quickly switch between resource types',
      'The inline search and filters (Status, CA) let you narrow down items without leaving the toolbar',
      'Switch between Table and Basket (transfer panel) view modes on desktop',
      'Preview changes before confirming bulk operations',
    ],
    warnings: [
      'Bulk delete is irreversible — always create a backup first',
      'Bulk revoke will publish updated CRLs for all affected CAs',
    ],
    related: ['Certificates', 'CAs', 'Import/Export']
  },

  // ===== HSM =====
  hsm: {
    title: 'Hardware Security Modules',
    subtitle: 'External key storage',
    overview: 'Integrate with Hardware Security Modules for secure private key storage. Support for PKCS#11, AWS CloudHSM, Azure Key Vault, and Google Cloud KMS.',
    sections: [
      {
        title: 'Supported Providers',
        icon: HardDrive,
        definitions: [
          { term: 'PKCS#11', description: 'Industry standard HSM interface (Thales, Entrust, SoftHSM)' },
          { term: 'AWS CloudHSM', description: 'Amazon Web Services cloud-based HSM' },
          { term: 'Azure Key Vault', description: 'Microsoft Azure managed key storage' },
          { term: 'Google KMS', description: 'Google Cloud Key Management Service' },
        ]
      },
      {
        title: 'Actions',
        icon: Key,
        items: [
          { label: 'Add Provider', text: 'Configure connection to an HSM (library path, credentials, slot)' },
          { label: 'Test Connection', text: 'Verify the HSM is reachable and credentials are valid' },
          { label: 'Generate Key', text: 'Create a new key pair directly on the HSM' },
          { label: 'Status', text: 'Monitor provider connection health' },
        ]
      },
    ],
    tips: [
      'Use SoftHSM for testing before deploying with a physical HSM',
      'Keys generated on an HSM never leave the hardware — they cannot be exported',
      'Test connection before using an HSM provider for CA signing',
    ],
    warnings: [
      'HSM provider misconfiguration can prevent certificate signing',
      'Losing access to the HSM means losing access to the keys stored on it',
    ],
    related: ['CAs', 'Certificates', 'Settings']
  },

  // ===== SSO (sub-page of Settings, kept for reference) =====
  sso: {
    title: 'Single Sign-On',
    subtitle: 'SAML and OIDC integration',
    overview: 'Configure Single Sign-On to allow users to authenticate via their organization identity provider. Supports both SAML 2.0 and OpenID Connect (OIDC) protocols.',
    sections: [
      {
        title: 'SAML 2.0',
        icon: Lock,
        items: [
          { label: 'Identity Provider', text: 'Configure IDP metadata URL or upload XML' },
          { label: 'Entity ID', text: 'UCM service provider entity identifier' },
          { label: 'ACS URL', text: 'Assertion Consumer Service callback URL' },
          { label: 'Attribute Mapping', text: 'Map IDP attributes to UCM user fields' },
        ]
      },
      {
        title: 'OpenID Connect',
        icon: Globe,
        items: [
          { label: 'Discovery URL', text: 'OIDC provider .well-known/openid-configuration URL' },
          { label: 'Client ID/Secret', text: 'OAuth2 client credentials from your IDP' },
          { label: 'Scopes', text: 'OpenID scopes to request (openid, profile, email)' },
          { label: 'Auto-Create Users', text: 'Automatically create UCM accounts on first SSO login' },
        ]
      },
    ],
    tips: [
      'Test SSO with a non-admin account first to avoid lockouts',
      'Keep local admin login available as a fallback',
      'Map the IDP email attribute to ensure unique user identification',
    ],
    warnings: [
      'Misconfigured SSO can lock all users out — always keep a local admin',
    ],
    related: ['Settings', 'Users & Groups']
  },

  // ===== SECURITY (sub-page of Settings) =====
  security: {
    title: 'Security Settings',
    subtitle: 'Authentication and access policies',
    overview: 'Configure password policies, session management, rate limiting, and network security. These settings apply system-wide and affect all user accounts.',
    sections: [
      {
        title: 'Password Policy',
        icon: Lock,
        items: [
          { label: 'Minimum Length', text: 'Minimum number of characters required' },
          { label: 'Complexity', text: 'Require uppercase, lowercase, numbers, special characters' },
          { label: 'Expiry', text: 'Force password change after a set number of days' },
          { label: 'History', text: 'Prevent reuse of previous passwords' },
        ]
      },
      {
        title: 'Session & Access',
        icon: Fingerprint,
        items: [
          { label: 'Session Timeout', text: 'Auto-logout after inactivity period' },
          { label: 'Rate Limiting', text: 'Limit login attempts to prevent brute force attacks' },
          { label: 'IP Restrictions', text: 'Allow or deny access from specific IP ranges' },
          { label: '2FA Enforcement', text: 'Require two-factor authentication for all users' },
        ]
      },
    ],
    tips: [
      'Enable rate limiting to protect against automated attack tools',
      'Use IP restrictions to limit admin access to trusted networks',
    ],
    warnings: [
      'Locking the password policy too tightly may frustrate users',
      'Always ensure at least one admin can access the system before enabling IP restrictions',
    ],
    related: ['Account', 'Users & Groups', 'Settings']
  },
}

export default helpContent
