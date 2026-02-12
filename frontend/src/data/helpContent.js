/**
 * Help content for all UCM pages
 * Structure:
 * - title: Modal header title
 * - subtitle: Short description
 * - overview: Introduction paragraph
 * - sections: Array of content sections
 * - tips: Array of helpful tips
 * - warnings: Array of important warnings
 * - related: Array of related pages/topics
 */

import {
  TreeStructure, Certificate, FileText, ClockCounterClockwise,
  ShieldCheck, Key, Users, Gear, Database, Lock, Globe,
  ListChecks, CloudArrowUp, HardDrive, UsersFour, Fingerprint,
  ArrowClockwise
} from '@phosphor-icons/react'

export const helpContent = {
  // ===========================================
  // DASHBOARD
  // ===========================================
  dashboard: {
    title: 'Dashboard',
    subtitle: 'System overview and monitoring',
    overview: 'The dashboard provides a real-time overview of your PKI infrastructure. Monitor certificate status, expiring certificates, and system health at a glance.',
    sections: [
      {
        title: 'Key Metrics',
        icon: ListChecks,
        items: [
          { label: 'Total CAs', text: 'Number of Certificate Authorities (Root + Intermediate)' },
          { label: 'Active Certificates', text: 'Valid certificates currently in use' },
          { label: 'Pending CSRs', text: 'Certificate Signing Requests awaiting approval' },
          { label: 'Expiring Soon', text: 'Certificates expiring within 30 days' },
        ]
      },
      {
        title: 'Certificate Status',
        icon: Certificate,
        content: 'Certificates are categorized by their current status:',
        definitions: [
          { term: 'Valid', description: 'Active and not expired' },
          { term: 'Expiring', description: 'Will expire within 30 days' },
          { term: 'Expired', description: 'Past validity period' },
          { term: 'Revoked', description: 'Manually invalidated before expiry' },
        ]
      },
      {
        title: 'Recent Activity',
        icon: ClockCounterClockwise,
        content: 'Shows the latest operations performed on your PKI: certificate issuance, revocations, CA operations, and user actions.'
      }
    ],
    tips: [
      'Set up email alerts to be notified before certificates expire',
      'Click on any metric card to see detailed information',
      'Review expiring certificates regularly to avoid service disruption'
    ],
    related: ['Certificates', 'CAs', 'Audit Logs']
  },

  // ===========================================
  // CERTIFICATE AUTHORITIES
  // ===========================================
  cas: {
    title: 'Certificate Authorities',
    subtitle: 'Manage your PKI hierarchy',
    overview: 'Certificate Authorities (CAs) are the foundation of your PKI. They sign and issue certificates to establish trust. UCM supports hierarchical CA structures with Root and Intermediate CAs, with automatic AKI/SKI-based chain matching for reliable parent-child relationships.',
    sections: [
      {
        title: 'CA Hierarchy',
        icon: TreeStructure,
        content: 'A typical PKI hierarchy consists of:',
        items: [
          { label: 'Root CA', text: 'The top-level CA that signs intermediate CAs. Keep offline for maximum security.' },
          { label: 'Intermediate CA', text: 'Signs end-entity certificates. Used for daily operations.' },
          { label: 'End-Entity', text: 'Server/client certificates issued to users and services.' },
        ]
      },
      {
        title: 'Creating a CA',
        icon: Certificate,
        content: 'When creating a new CA, you\'ll need to specify:',
        items: [
          { label: 'Common Name', text: 'Unique identifier (e.g., "My Company Root CA")' },
          { label: 'Key Algorithm', text: 'RSA (2048/4096) or ECDSA (P-256/P-384)' },
          { label: 'Validity', text: 'Root CAs: 10-20 years, Intermediate: 5-10 years' },
          { label: 'Key Usage', text: 'Certificate signing, CRL signing capabilities' },
        ]
      },
      {
        title: 'CA Operations',
        icon: Gear,
        items: [
          { label: 'Issue Certificate', text: 'Sign a new certificate under this CA' },
          { label: 'Generate CRL', text: 'Create a Certificate Revocation List' },
          { label: 'Export', text: 'Download CA certificate in various formats (PEM, DER)' },
          { label: 'Renew', text: 'Create a new CA certificate with extended validity' },
        ]
      },
      {
        title: 'Chain Repair',
        icon: ArrowClockwise,
        content: 'UCM automatically maintains certificate chain integrity:',
        items: [
          { label: 'AKI/SKI Matching', text: 'Chains are built using cryptographic key identifiers, not names - reliable across imports and environments.' },
          { label: 'Automatic Repair', text: 'An hourly background task re-chains orphan CAs and certificates, and deduplicates entries with the same key.' },
          { label: 'Run Now', text: 'Use the Chain Repair bar at the top of this page to trigger an immediate repair or check status.' },
        ]
      }
    ],
    tips: [
      'Use a strong key algorithm: RSA 4096 or ECDSA P-384 for Root CAs',
      'Create at least one Intermediate CA for issuing end-entity certificates',
      'Keep your Root CA private key secure - consider HSM storage',
      'The Chain Repair bar shows chain integrity status - click "Run Now" after importing multiple CAs to link them immediately'
    ],
    warnings: [
      'Deleting a CA will NOT revoke certificates it has issued',
      'Root CA compromise affects your entire PKI - protect it carefully'
    ],
    related: ['Certificates', 'CRL/OCSP', 'Templates', 'HSM']
  },

  // ===========================================
  // CERTIFICATES
  // ===========================================
  certificates: {
    title: 'Certificates',
    subtitle: 'Issue and manage X.509 certificates',
    overview: 'Certificates bind a public key to an identity. UCM manages the full certificate lifecycle: issuance, renewal, and revocation.',
    sections: [
      {
        title: 'Certificate Types',
        icon: Certificate,
        definitions: [
          { term: 'Server (TLS)', description: 'For HTTPS websites and services' },
          { term: 'Client', description: 'For user/device authentication' },
          { term: 'Code Signing', description: 'For signing software and scripts' },
          { term: 'S/MIME', description: 'For email encryption and signing' },
        ]
      },
      {
        title: 'Issuing a Certificate',
        icon: FileText,
        content: 'You can issue certificates by:',
        items: [
          'Filling in the certificate details manually',
          'Using a pre-configured template',
          'Signing an existing CSR (Certificate Signing Request)',
          'Using SCEP or ACME for automated enrollment'
        ]
      },
      {
        title: 'Key Fields',
        icon: Key,
        definitions: [
          { term: 'Common Name', description: 'Primary identifier (e.g., domain name for TLS)' },
          { term: 'SAN', description: 'Subject Alternative Names - additional domains/IPs' },
          { term: 'Key Usage', description: 'What the key can be used for (signing, encryption)' },
          { term: 'Extended Key Usage', description: 'Specific purposes (serverAuth, clientAuth, etc.)' },
        ]
      },
      {
        title: 'Export Formats',
        icon: CloudArrowUp,
        definitions: [
          { term: 'PEM', description: 'Base64 encoded, used by Apache/Nginx' },
          { term: 'DER', description: 'Binary format' },
          { term: 'PKCS#12 (P12)', description: 'Contains cert + private key, password protected' },
          { term: 'Chain', description: 'Full certificate chain including intermediates' },
        ]
      }
    ],
    tips: [
      'Always include the full certificate chain when deploying TLS certificates',
      'Use PKCS#12 format when you need to export the private key',
      'Set up auto-renewal via ACME for public-facing services'
    ],
    warnings: [
      'Never share private keys - export only to authorized systems',
      'Revoke compromised certificates immediately'
    ],
    related: ['CAs', 'CSRs', 'Templates', 'SCEP', 'ACME']
  },

  // ===========================================
  // TEMPLATES
  // ===========================================
  templates: {
    title: 'Certificate Templates',
    subtitle: 'Pre-configured certificate profiles',
    overview: 'Templates define default values for certificate issuance, ensuring consistency and compliance. They specify key usage, validity periods, and other certificate attributes.',
    sections: [
      {
        title: 'Template Types',
        icon: FileText,
        definitions: [
          { term: 'CA Template', description: 'For creating new Certificate Authorities' },
          { term: 'Certificate Template', description: 'For issuing end-entity certificates' },
        ]
      },
      {
        title: 'Common Templates',
        icon: ListChecks,
        items: [
          { label: 'TLS Server', text: 'Web servers - includes serverAuth EKU and DNS SANs' },
          { label: 'TLS Client', text: 'Client authentication - includes clientAuth EKU' },
          { label: 'Code Signing', text: 'Software signing - includes codeSigning EKU' },
          { label: 'S/MIME', text: 'Email security - includes emailProtection EKU' },
        ]
      },
      {
        title: 'Template Fields',
        icon: Gear,
        definitions: [
          { term: 'Validity', description: 'Default certificate lifetime (days)' },
          { term: 'Key Algorithm', description: 'RSA/ECDSA key type and size' },
          { term: 'Key Usage', description: 'Digital signature, key encipherment, etc.' },
          { term: 'Extended Key Usage', description: 'serverAuth, clientAuth, codeSigning, etc.' },
          { term: 'Allowed SANs', description: 'DNS, IP, Email, URI types permitted' },
        ]
      }
    ],
    tips: [
      'Create templates for each certificate type used in your organization',
      'Use templates with SCEP/ACME for consistent automated enrollment',
      'Restrict templates to specific CAs if needed'
    ],
    related: ['Certificates', 'CAs', 'SCEP', 'ACME']
  },

  // ===========================================
  // CSRs
  // ===========================================
  csrs: {
    title: 'Certificate Signing Requests',
    subtitle: 'Review and sign CSRs',
    overview: 'A CSR contains a public key and identity information, submitted by a requester for CA signature. Review CSRs carefully before signing.',
    sections: [
      {
        title: 'CSR Workflow',
        icon: FileText,
        items: [
          'Requester generates a key pair and creates a CSR',
          'CSR is uploaded or submitted via SCEP',
          'Administrator reviews the request details',
          'CA signs the CSR to create a certificate',
          'Certificate is returned to the requester'
        ]
      },
      {
        title: 'Review Checklist',
        icon: ShieldCheck,
        items: [
          'Verify the Common Name matches the intended use',
          'Check SANs for valid domains/IPs',
          'Confirm key algorithm meets security requirements',
          'Verify the requester\'s identity through your process'
        ]
      }
    ],
    tips: [
      'Use templates to ensure signed certificates have correct attributes',
      'Set up automatic signing for trusted SCEP/ACME clients'
    ],
    warnings: [
      'Never sign a CSR without verifying the requester\'s identity',
      'Rejected CSRs should be investigated for potential abuse'
    ],
    related: ['Certificates', 'SCEP', 'ACME']
  },

  // ===========================================
  // CRL/OCSP
  // ===========================================
  crlocsp: {
    title: 'CRL & OCSP',
    subtitle: 'Certificate revocation management',
    overview: 'CRL (Certificate Revocation List) and OCSP (Online Certificate Status Protocol) allow clients to check if a certificate has been revoked.',
    sections: [
      {
        title: 'CRL vs OCSP',
        icon: ShieldCheck,
        definitions: [
          { term: 'CRL', description: 'A signed list of all revoked certificates. Downloaded periodically by clients.' },
          { term: 'OCSP', description: 'Real-time protocol to check individual certificate status.' },
        ]
      },
      {
        title: 'CRL Configuration',
        icon: ClockCounterClockwise,
        items: [
          { label: 'Auto-Regeneration', text: 'Automatically update CRL on schedule' },
          { label: 'Validity', text: 'How long the CRL is valid (nextUpdate field)' },
          { label: 'Distribution Points', text: 'URLs where clients can download the CRL' },
        ]
      },
      {
        title: 'OCSP Responder',
        icon: Globe,
        content: 'UCM includes a built-in OCSP responder. Configure the OCSP URL in your CA settings to enable real-time revocation checking.',
      }
    ],
    tips: [
      'Enable auto-regeneration to keep CRLs current',
      'Use OCSP for time-sensitive applications',
      'Publish CRLs to a highly available endpoint'
    ],
    warnings: [
      'Expired CRLs may cause clients to reject valid certificates',
      'Large CRLs can impact client performance'
    ],
    related: ['CAs', 'Certificates']
  },

  // ===========================================
  // SCEP
  // ===========================================
  scep: {
    title: 'SCEP',
    subtitle: 'Simple Certificate Enrollment Protocol',
    overview: 'SCEP allows devices to automatically request and receive certificates. Commonly used for network devices, MDM solutions, and IoT.',
    sections: [
      {
        title: 'How SCEP Works',
        icon: Certificate,
        items: [
          'Client generates a key pair',
          'Client creates a CSR with challenge password',
          'CSR is sent to SCEP server encrypted',
          'Server validates the challenge password',
          'If approved, CA signs and returns the certificate'
        ]
      },
      {
        title: 'Configuration',
        icon: Gear,
        definitions: [
          { term: 'Challenge Password', description: 'Shared secret for enrollment authentication' },
          { term: 'CA', description: 'Which CA will sign SCEP requests' },
          { term: 'Template', description: 'Certificate profile for issued certificates' },
          { term: 'Auto-Approve', description: 'Automatically sign matching requests' },
        ]
      },
      {
        title: 'SCEP URL',
        icon: Globe,
        content: 'The SCEP endpoint is available at:',
        example: 'https://your-ucm-server:8443/scep/{config-name}/pkiclient.exe'
      }
    ],
    tips: [
      'Use unique challenge passwords per device or device group',
      'Enable auto-approval only for trusted network segments',
      'Test SCEP with sscep or micromdm/scepclient before deployment'
    ],
    warnings: [
      'Challenge passwords are sensitive - distribute securely',
      'Monitor pending requests for unauthorized enrollment attempts'
    ],
    related: ['Certificates', 'Templates', 'CAs']
  },

  // ===========================================
  // ACME
  // ===========================================
  acme: {
    title: 'ACME',
    subtitle: 'Automated Certificate Management Environment',
    overview: 'ACME automates certificate issuance and renewal, similar to Let\'s Encrypt. Supports HTTP-01 and DNS-01 challenges for domain validation.',
    sections: [
      {
        title: 'ACME Flow',
        icon: Certificate,
        items: [
          'Client registers an account with the ACME server',
          'Client creates an order for a certificate',
          'Server issues challenges to verify domain ownership',
          'Client completes challenges (HTTP or DNS)',
          'Server validates and issues the certificate'
        ]
      },
      {
        title: 'Challenge Types',
        icon: ShieldCheck,
        definitions: [
          { term: 'HTTP-01', description: 'Place a file at /.well-known/acme-challenge/ on the web server' },
          { term: 'DNS-01', description: 'Create a TXT record _acme-challenge.domain.com' },
        ]
      },
      {
        title: 'ACME Directory',
        icon: Globe,
        content: 'The ACME directory URL is:',
        example: 'https://your-ucm-server:8443/acme/{server-name}/directory'
      }
    ],
    tips: [
      'Use certbot or acme.sh for easy ACME client integration',
      'DNS-01 challenges work for wildcard certificates',
      'Set up auto-renewal with cron or systemd timers'
    ],
    related: ['Certificates', 'CAs']
  },

  // ===========================================
  // TRUSTSTORE
  // ===========================================
  truststore: {
    title: 'Trust Store',
    subtitle: 'Manage trusted external CAs',
    overview: 'The trust store contains CA certificates from external sources that you trust. Useful for validating client certificates from partner organizations.',
    sections: [
      {
        title: 'Trust Store Sources',
        icon: Certificate,
        items: [
          { label: 'Manual Import', text: 'Upload CA certificates manually' },
          { label: 'Remote URL', text: 'Fetch certificates from a URL' },
          { label: 'System CA Bundle', text: 'Sync with the operating system trust store' },
        ]
      },
      {
        title: 'Use Cases',
        icon: ShieldCheck,
        items: [
          'Validate client certificates from partner CAs',
          'Trust certificates for mTLS connections',
          'Import public root CAs for verification'
        ]
      }
    ],
    tips: [
      'Only import CAs you actually need to trust',
      'Review imported CA validity and purpose',
      'Use tags to organize certificates by source or purpose'
    ],
    warnings: [
      'Trusting a CA means trusting all certificates it signs',
      'Regularly review and clean up unused trust entries'
    ],
    related: ['Certificates', 'CAs']
  },

  // ===========================================
  // USERS
  // ===========================================
  users: {
    title: 'Users',
    subtitle: 'User account management',
    overview: 'Manage user accounts that can access UCM. Configure authentication methods and permissions.',
    sections: [
      {
        title: 'Authentication Methods',
        icon: Fingerprint,
        definitions: [
          { term: 'Password', description: 'Traditional username/password login' },
          { term: 'WebAuthn', description: 'Hardware security keys (YubiKey, etc.) or biometrics' },
          { term: 'SSO', description: 'Single Sign-On via SAML or OIDC (Pro feature)' },
        ]
      },
      {
        title: 'User Properties',
        icon: Users,
        definitions: [
          { term: 'Username', description: 'Unique login identifier' },
          { term: 'Email', description: 'For notifications and recovery' },
          { term: 'Role', description: 'Permission level (Admin, Operator, Viewer)' },
          { term: 'Status', description: 'Active or disabled' },
        ]
      }
    ],
    tips: [
      'Enable WebAuthn for stronger authentication',
      'Use role-based access for least-privilege security',
      'Review user accounts regularly and disable unused ones'
    ],
    warnings: [
      'Deleting a user cannot be undone',
      'Disabling an admin could lock you out if you\'re the only one'
    ],
    related: ['Groups', 'RBAC', 'Settings']
  },

  // ===========================================
  // AUDIT LOGS
  // ===========================================
  auditLogs: {
    title: 'Audit Logs',
    subtitle: 'Activity and security logging',
    overview: 'Audit logs record all significant actions in UCM for compliance and security investigation.',
    sections: [
      {
        title: 'Logged Events',
        icon: ListChecks,
        items: [
          'User authentication (login, logout, failures)',
          'Certificate operations (issue, revoke, export)',
          'CA management (create, delete, sign)',
          'Configuration changes',
          'User management operations'
        ]
      },
      {
        title: 'Log Entry Fields',
        icon: FileText,
        definitions: [
          { term: 'Timestamp', description: 'When the event occurred' },
          { term: 'User', description: 'Who performed the action' },
          { term: 'Action', description: 'What was done' },
          { term: 'Resource', description: 'What was affected' },
          { term: 'IP Address', description: 'Where the request came from' },
          { term: 'Details', description: 'Additional context' },
        ]
      }
    ],
    tips: [
      'Filter by action type to investigate specific events',
      'Export logs regularly for long-term retention',
      'Set up alerts for suspicious activities'
    ],
    related: ['Settings', 'Users']
  },

  // ===========================================
  // SETTINGS
  // ===========================================
  settings: {
    title: 'Settings',
    subtitle: 'System configuration',
    overview: 'Configure UCM behavior, security settings, email notifications, and more.',
    sections: [
      {
        title: 'General',
        icon: Gear,
        definitions: [
          { term: 'Instance Name', description: 'Display name for this UCM installation' },
          { term: 'Base URL', description: 'Public URL for certificate distribution points' },
        ]
      },
      {
        title: 'Security',
        icon: Lock,
        definitions: [
          { term: 'Session Timeout', description: 'Auto-logout after inactivity' },
          { term: 'Password Policy', description: 'Minimum length and complexity' },
          { term: 'Two-Factor Auth', description: 'Require 2FA for all users' },
        ]
      },
      {
        title: 'Database',
        icon: Database,
        definitions: [
          { term: 'Backup', description: 'Create database backups' },
          { term: 'Restore', description: 'Restore from a previous backup' },
          { term: 'Optimization', description: 'Vacuum and analyze the database' },
        ]
      },
      {
        title: 'Email (SMTP)',
        icon: Globe,
        definitions: [
          { term: 'Server', description: 'SMTP server hostname and port' },
          { term: 'Authentication', description: 'Username/password for SMTP' },
          { term: 'Notifications', description: 'Certificate expiry alerts' },
        ]
      },
      {
        title: 'Appearance',
        icon: Gear,
        content: 'Choose from multiple color themes: Dark (default), Light, Ocean, Forest, Purple, Sunset, and more.'
      }
    ],
    tips: [
      'Test email settings before enabling notifications',
      'Create regular database backups',
      'Shorter session timeouts improve security'
    ],
    related: ['Users', 'Security']
  },

  // ===========================================
  // ACCOUNT
  // ===========================================
  account: {
    title: 'My Account',
    subtitle: 'Personal settings and security',
    overview: 'Manage your personal account settings, security options, and view your activity.',
    sections: [
      {
        title: 'Profile',
        icon: Users,
        items: [
          'Update your display name and email',
          'Change your password',
          'Manage notification preferences'
        ]
      },
      {
        title: 'Security',
        icon: Fingerprint,
        items: [
          { label: 'WebAuthn Keys', text: 'Add hardware security keys or biometric authenticators' },
          { label: 'Active Sessions', text: 'View and revoke logged-in sessions' },
          { label: 'Password', text: 'Change your password' },
        ]
      },
      {
        title: 'Activity',
        icon: ClockCounterClockwise,
        content: 'View your recent actions in UCM: logins, certificate operations, and other activities.'
      }
    ],
    tips: [
      'Register multiple WebAuthn keys for backup access',
      'Review active sessions and revoke unfamiliar ones',
      'Use a strong, unique password'
    ],
    related: ['Users', 'Settings']
  },

  // ===========================================
  // IMPORT/EXPORT
  // ===========================================
  importExport: {
    title: 'Import & Export',
    subtitle: 'Backup and migration',
    overview: 'Import and export UCM data for backup, migration, or integration with other systems.',
    sections: [
      {
        title: 'Export Options',
        icon: CloudArrowUp,
        items: [
          { label: 'Full Backup', text: 'Complete UCM data including keys (encrypted)' },
          { label: 'CA Export', text: 'Export specific CAs with or without private keys' },
          { label: 'Certificate Export', text: 'Batch export certificates' },
        ]
      },
      {
        title: 'Import Options',
        icon: Database,
        items: [
          { label: 'From Backup', text: 'Restore from a UCM backup file' },
          { label: 'External CA', text: 'Import CA certificate and optionally private key' },
          { label: 'From Host', text: 'Import system CA certificates' },
        ]
      }
    ],
    tips: [
      'Encrypt exports containing private keys',
      'Store backups in a secure, separate location',
      'Test restore procedure periodically'
    ],
    warnings: [
      'Importing overwrites existing data with the same IDs',
      'Private key exports require admin privileges'
    ],
    related: ['CAs', 'Certificates', 'Settings']
  },

  // ===========================================
  // PRO FEATURES
  // ===========================================

  // GROUPS (Community feature)
  groups: {
    title: 'Groups',
    subtitle: 'Team and access management',
    overview: 'Groups allow you to organize users into teams and apply permissions at the group level. Members inherit the group\'s role-based permissions.',
    sections: [
      {
        title: 'Group Management',
        icon: UsersFour,
        items: [
          'Create groups for departments or teams',
          'Add and remove members',
          'Assign roles to groups',
          'View group activity'
        ]
      },
      {
        title: 'Group Properties',
        icon: Users,
        definitions: [
          { term: 'Name', description: 'Unique group identifier' },
          { term: 'Description', description: 'Purpose of the group' },
          { term: 'Members', description: 'Users belonging to this group' },
          { term: 'Role', description: 'Permissions applied to all members' },
        ]
      }
    ],
    tips: [
      'Use groups for role-based access instead of per-user permissions',
      'Name groups by function (e.g., "PKI-Admins", "Certificate-Operators")',
      'Review group memberships during employee offboarding'
    ],
    related: ['Users', 'RBAC']
  },

  // RBAC (Pro)
  rbac: {
    title: 'Role-Based Access Control',
    subtitle: 'Fine-grained permissions (Pro)',
    overview: 'RBAC lets you define custom roles with specific permissions. Assign roles to users or groups to control who can perform which operations.',
    sections: [
      {
        title: 'Built-in Roles',
        icon: ShieldCheck,
        definitions: [
          { term: 'Admin', description: 'Full access to all features' },
          { term: 'Operator', description: 'Can manage certificates and CAs' },
          { term: 'Viewer', description: 'Read-only access' },
          { term: 'Auditor', description: 'Access to audit logs only' },
        ]
      },
      {
        title: 'Permission Categories',
        icon: Key,
        items: [
          { label: 'CAs', text: 'Create, delete, sign with CAs' },
          { label: 'Certificates', text: 'Issue, revoke, export certificates' },
          { label: 'Users', text: 'Create, modify, delete users' },
          { label: 'Settings', text: 'Modify system configuration' },
          { label: 'Audit', text: 'View and export audit logs' },
        ]
      },
      {
        title: 'Custom Roles',
        icon: Gear,
        content: 'Create custom roles by selecting specific permissions. Useful for compliance requirements or specialized teams.'
      }
    ],
    tips: [
      'Follow least-privilege principle - grant only needed permissions',
      'Use groups + RBAC together for scalable access management',
      'Audit role assignments regularly'
    ],
    warnings: [
      'Removing admin role from all users could lock you out',
      'Test custom roles before assigning to production users'
    ],
    related: ['Users', 'Groups']
  },

  // HSM (Pro)
  hsm: {
    title: 'HSM Integration',
    subtitle: 'Hardware Security Modules (Pro)',
    overview: 'Hardware Security Modules provide tamper-resistant storage for cryptographic keys. UCM supports PKCS#11 compatible HSMs.',
    sections: [
      {
        title: 'Supported HSMs',
        icon: HardDrive,
        items: [
          'Thales/Gemalto Luna',
          'AWS CloudHSM',
          'Azure Dedicated HSM',
          'nCipher nShield',
          'YubiHSM 2',
          'SoftHSM (for testing)'
        ]
      },
      {
        title: 'HSM Configuration',
        icon: Key,
        definitions: [
          { term: 'Library Path', description: 'Path to PKCS#11 library (.so/.dll)' },
          { term: 'Slot', description: 'HSM slot or token identifier' },
          { term: 'PIN', description: 'Authentication PIN for the slot' },
        ]
      },
      {
        title: 'HSM Operations',
        icon: ShieldCheck,
        items: [
          'Generate keys directly in HSM',
          'Sign certificates using HSM-stored keys',
          'Keys never leave the HSM boundary',
          'Automatic failover for clustered HSMs'
        ]
      }
    ],
    tips: [
      'Test HSM integration with SoftHSM first',
      'Configure HSM cluster for high availability',
      'Store Root CA keys in HSM for maximum security'
    ],
    warnings: [
      'HSM PINs are highly sensitive - store securely',
      'Lost HSM access = lost keys (no recovery)',
      'HSM performance may be slower than software keys'
    ],
    related: ['CAs', 'Settings']
  },

  // SSO (Pro)
  sso: {
    title: 'Single Sign-On',
    subtitle: 'SAML & OIDC integration (Pro)',
    overview: 'Integrate UCM with your identity provider for seamless authentication. Supports SAML 2.0 and OpenID Connect.',
    sections: [
      {
        title: 'Supported Protocols',
        icon: Globe,
        definitions: [
          { term: 'SAML 2.0', description: 'Enterprise SSO standard (Okta, Azure AD, ADFS)' },
          { term: 'OpenID Connect', description: 'Modern OAuth2-based SSO (Google, Auth0, Keycloak)' },
        ]
      },
      {
        title: 'SAML Configuration',
        icon: Gear,
        definitions: [
          { term: 'IdP Metadata', description: 'Import from your identity provider' },
          { term: 'Entity ID', description: 'UCM service provider identifier' },
          { term: 'ACS URL', description: 'Assertion Consumer Service endpoint' },
          { term: 'Attribute Mapping', description: 'Map IdP attributes to UCM fields' },
        ]
      },
      {
        title: 'OIDC Configuration',
        icon: Lock,
        definitions: [
          { term: 'Client ID', description: 'OAuth2 client identifier' },
          { term: 'Client Secret', description: 'OAuth2 client secret' },
          { term: 'Discovery URL', description: '.well-known/openid-configuration endpoint' },
          { term: 'Scopes', description: 'openid, profile, email' },
        ]
      }
    ],
    tips: [
      'Enable Just-In-Time provisioning to auto-create users',
      'Map IdP groups to UCM groups for role assignment',
      'Keep local admin account as backup access'
    ],
    warnings: [
      'Test SSO with a non-admin user first',
      'IdP outage = users can\'t login (keep local backup)',
      'Attribute mapping errors may prevent login'
    ],
    related: ['Users', 'Groups', 'RBAC']
  },

  // ===========================================
  // SECURITY DASHBOARD (Pro)
  // ===========================================
  security: {
    title: 'Security Dashboard',
    subtitle: 'Monitor and manage security settings (Pro)',
    overview: 'The Security Dashboard provides visibility into UCM security status. Monitor secrets, detect anomalies, and verify audit log integrity.',
    sections: [
      {
        title: 'Secrets Management',
        icon: Key,
        content: 'UCM uses cryptographic secrets for session management:',
        definitions: [
          { term: 'Session Secret', description: 'Encrypts server-side sessions (32+ bytes recommended)' },
          { term: 'Encryption Key', description: 'Optional key for encrypting private keys at rest' },
        ]
      },
      {
        title: 'Secret Rotation',
        icon: ShieldCheck,
        content: 'Rotate secrets periodically for security:',
        items: [
          { label: 'Generate', text: 'Click "Rotate Session Secret" to generate a new secret' },
          { label: 'Apply', text: 'Copy the new secret to your environment variables' },
          { label: 'Restart', text: 'Restart UCM backend to apply the new secret' },
          { label: 'Sessions', text: 'Existing sessions will be invalidated after rotation' },
        ]
      },
      {
        title: 'Anomaly Detection',
        icon: ShieldCheck,
        content: 'Automatic detection of suspicious login patterns:',
        definitions: [
          { term: 'Credential Stuffing', description: 'Multiple failed logins from same IP' },
          { term: 'Unusual Hours', description: 'Logins outside normal business hours' },
          { term: 'New Device', description: 'Login from previously unseen device/location' },
          { term: 'Brute Force', description: 'Rapid login attempts on same account' },
        ]
      },
      {
        title: 'Audit Integrity',
        icon: Lock,
        content: 'Audit logs use a cryptographic hash chain. Each entry contains a hash of the previous entry, making it impossible to modify or delete logs without detection.',
        items: [
          { label: 'Verify', text: 'Click "Verify Audit Integrity" to check the hash chain' },
          { label: 'Green', text: 'All entries verified - no tampering detected' },
          { label: 'Red', text: 'Hash mismatch - investigate immediately' },
        ]
      }
    ],
    tips: [
      'Rotate session secrets every 90 days',
      'Review anomalies daily for suspicious activity',
      'Verify audit integrity after any incident',
      'Use strong secrets (32+ random bytes)'
    ],
    warnings: [
      'Rotating secrets invalidates all existing sessions',
      'Keep backup of current secrets before rotation',
      'Audit integrity failures may indicate compromise'
    ],
    related: ['Audit Logs', 'Users', 'Settings']
  }
}

export default helpContent
