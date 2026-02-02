/**
 * Centralized message strings for i18n preparation
 * All user-facing text should be defined here
 */

// Error messages
export const ERRORS = {
  LOAD_FAILED: {
    CERTIFICATES: 'Failed to load certificates',
    CAS: 'Failed to load CAs',
    CSRS: 'Failed to load CSRs',
    USERS: 'Failed to load users',
    GROUPS: 'Failed to load groups',
    TEMPLATES: 'Failed to load templates',
    AUDIT_LOGS: 'Failed to load audit logs',
    SETTINGS: 'Failed to load settings',
    ACME: 'Failed to load ACME data',
    SCEP: 'Failed to load SCEP data',
    CRL: 'Failed to load CRL data',
    TRUSTSTORE: 'Failed to load trust store',
    DASHBOARD: 'Failed to load dashboard data',
    GENERIC: 'Failed to load data',
  },
  CREATE_FAILED: {
    CERTIFICATE: 'Failed to create certificate',
    CA: 'Failed to create CA',
    CSR: 'Failed to create CSR',
    USER: 'Failed to create user',
    GROUP: 'Failed to create group',
    TEMPLATE: 'Failed to create template',
    GENERIC: 'Failed to create',
  },
  UPDATE_FAILED: {
    CERTIFICATE: 'Failed to update certificate',
    CA: 'Failed to update CA',
    USER: 'Failed to update user',
    GROUP: 'Failed to update group',
    TEMPLATE: 'Failed to update template',
    SETTINGS: 'Failed to save settings',
    GENERIC: 'Failed to update',
  },
  DELETE_FAILED: {
    CERTIFICATE: 'Failed to delete certificate',
    CA: 'Failed to delete CA',
    CSR: 'Failed to delete CSR',
    USER: 'Failed to delete user',
    GROUP: 'Failed to delete group',
    TEMPLATE: 'Failed to delete template',
    GENERIC: 'Failed to delete',
  },
  VALIDATION: {
    REQUIRED_FIELD: 'This field is required',
    INVALID_EMAIL: 'Please enter a valid email address',
    INVALID_PASSWORD: 'Password does not meet requirements',
    PASSWORD_MISMATCH: 'Passwords do not match',
    INVALID_PEM: 'Invalid PEM format',
    INVALID_KEY: 'Invalid private key format - must be PEM format',
    KEY_MISMATCH: 'Private key does not match certificate',
    PASSPHRASE_REQUIRED: 'Private key is encrypted - please provide passphrase',
  },
  AUTH: {
    LOGIN_FAILED: 'Login failed',
    UNAUTHORIZED: 'Unauthorized',
    SESSION_EXPIRED: 'Session expired, please login again',
  },
}

// Success messages
export const SUCCESS = {
  CREATE: {
    CERTIFICATE: 'Certificate created successfully',
    CA: 'CA created successfully',
    CSR: 'CSR created successfully',
    USER: 'User created successfully',
    GROUP: 'Group created successfully',
    TEMPLATE: 'Template created successfully',
  },
  UPDATE: {
    CERTIFICATE: 'Certificate updated successfully',
    CA: 'CA updated successfully',
    USER: 'User updated successfully',
    GROUP: 'Group updated successfully',
    TEMPLATE: 'Template updated successfully',
    SETTINGS: 'Settings saved successfully',
  },
  DELETE: {
    CERTIFICATE: 'Certificate deleted successfully',
    CA: 'CA deleted successfully',
    CSR: 'CSR deleted successfully',
    USER: 'User deleted successfully',
    GROUP: 'Group deleted successfully',
    TEMPLATE: 'Template deleted successfully',
  },
  EXPORT: {
    CERTIFICATE: 'Certificate exported successfully',
    CA: 'CA exported successfully',
    BACKUP: 'Backup exported successfully',
  },
  IMPORT: {
    CERTIFICATE: 'Certificate imported successfully',
    CA: 'CA imported successfully',
    BACKUP: 'Backup restored successfully',
  },
  OTHER: {
    PASSWORD_RESET: 'Password reset successfully',
    KEY_UPLOADED: 'Private key uploaded successfully',
    REVOKED: 'Certificate revoked successfully',
    SIGNED: 'CSR signed successfully',
  },
}

// Button labels
export const BUTTONS = {
  // Actions
  CREATE: 'Create',
  SAVE: 'Save',
  CANCEL: 'Cancel',
  DELETE: 'Delete',
  EDIT: 'Edit',
  UPDATE: 'Update',
  CLOSE: 'Close',
  CONFIRM: 'Confirm',
  
  // Data operations
  EXPORT: 'Export',
  IMPORT: 'Import',
  DOWNLOAD: 'Download',
  UPLOAD: 'Upload',
  REFRESH: 'Refresh',
  SEARCH: 'Search',
  FILTER: 'Filter',
  CLEAR: 'Clear',
  
  // Certificate operations
  SIGN: 'Sign',
  REVOKE: 'Revoke',
  RENEW: 'Renew',
  ISSUE: 'Issue Certificate',
  
  // User operations
  RESET_PASSWORD: 'Reset Password',
  CHANGE_PASSWORD: 'Change Password',
  
  // Other
  VIEW_DETAILS: 'View Details',
  SHOW_MORE: 'Show More',
  SHOW_LESS: 'Show Less',
  BACK: 'Back',
  NEXT: 'Next',
  PREVIOUS: 'Previous',
}

// Labels
export const LABELS = {
  // User roles
  ROLES: {
    ADMIN: 'Admin',
    OPERATOR: 'Operator',
    VIEWER: 'Viewer',
  },
  
  // Status
  STATUS: {
    ACTIVE: 'Active',
    INACTIVE: 'Inactive',
    PENDING: 'Pending',
    APPROVED: 'Approved',
    REJECTED: 'Rejected',
    EXPIRED: 'Expired',
    REVOKED: 'Revoked',
    VALID: 'Valid',
  },
  
  // Certificate types
  CERT_TYPES: {
    CA: 'Certificate Authority',
    ROOT_CA: 'Root CA',
    INTERMEDIATE_CA: 'Intermediate CA',
    SERVER: 'Server',
    CLIENT: 'Client',
    CODE_SIGNING: 'Code Signing',
  },
  
  // Key types
  KEY_TYPES: {
    RSA_2048: 'RSA 2048-bit',
    RSA_4096: 'RSA 4096-bit',
    ECDSA_P256: 'ECDSA P-256',
    ECDSA_P384: 'ECDSA P-384',
  },
  
  // Table headers
  TABLE: {
    NAME: 'Name',
    EMAIL: 'Email',
    ROLE: 'Role',
    STATUS: 'Status',
    CREATED: 'Created',
    EXPIRES: 'Expires',
    SUBJECT: 'Subject',
    ISSUER: 'Issuer',
    SERIAL: 'Serial',
    ACTIONS: 'Actions',
    TIME: 'Time',
    USER: 'User',
    ACTION: 'Action',
    RESOURCE: 'Resource',
    IP: 'IP Address',
  },
  
  // Filter placeholders
  FILTERS: {
    ALL_ROLES: 'All Roles',
    ALL_STATUS: 'All Status',
    ALL_TYPES: 'All Types',
    ALL_ACTIONS: 'All Actions',
    ALL_CAS: 'All CAs',
    ALL_USERS: 'All Users',
    SEARCH: 'Search...',
  },
  
  // Settings tabs
  SETTINGS: {
    GENERAL: 'General',
    APPEARANCE: 'Appearance',
    EMAIL: 'Email',
    SECURITY: 'Security',
    BACKUP: 'Backup',
    AUDIT: 'Audit',
    DATABASE: 'Database',
    HTTPS: 'HTTPS',
  },
  
  // Theme options
  THEMES: {
    SYSTEM: 'Follow System',
    LIGHT: 'Light',
    DARK: 'Dark',
  },
  
  // Common
  YES: 'Yes',
  NO: 'No',
  NONE: 'None',
  LOADING: 'Loading...',
  NO_DATA: 'No data available',
  NO_RESULTS: 'No results found',
}

// Confirmation dialogs
export const CONFIRM = {
  DELETE: {
    TITLE: 'Confirm Delete',
    USER: 'Are you sure you want to delete this user?',
    GROUP: 'Are you sure you want to delete this group?',
    CERTIFICATE: 'Are you sure you want to delete this certificate?',
    CA: 'Are you sure you want to delete this CA?',
    TEMPLATE: 'Are you sure you want to delete this template?',
  },
  REVOKE: {
    TITLE: 'Confirm Revoke',
    MESSAGE: 'Are you sure you want to revoke this certificate? This action cannot be undone.',
  },
  RESET_PASSWORD: {
    TITLE: 'Reset Password',
    MESSAGE: 'Are you sure you want to reset this user\'s password?',
  },
}

// Page titles
export const TITLES = {
  DASHBOARD: 'Dashboard',
  CERTIFICATES: 'Certificates',
  CAS: 'Certificate Authorities',
  CSRS: 'Certificate Signing Requests',
  TEMPLATES: 'Certificate Templates',
  USERS: 'Users',
  GROUPS: 'Groups',
  ACME: 'ACME Configuration',
  SCEP: 'SCEP Configuration',
  CRL_OCSP: 'CRL & OCSP',
  TRUSTSTORE: 'Trust Store',
  IMPORT_EXPORT: 'Import & Export',
  AUDIT_LOGS: 'Audit Logs',
  SETTINGS: 'Settings',
  ACCOUNT: 'Account',
  LOGIN: 'Login',
}

// Empty state messages
export const EMPTY_STATES = {
  CERTIFICATES: 'No certificates found',
  CAS: 'No Certificate Authorities found',
  CSRS: 'No pending CSRs',
  USERS: 'No users found',
  GROUPS: 'No groups found',
  TEMPLATES: 'No templates found',
  AUDIT_LOGS: 'No audit logs found',
  ACME_ACCOUNTS: 'No ACME accounts registered',
  
  // With actions
  CREATE_FIRST: {
    CERTIFICATE: 'Create your first certificate',
    CA: 'Create your first Certificate Authority',
    USER: 'Create your first user',
    GROUP: 'Create your first group',
    TEMPLATE: 'Create your first template',
  },
}

// Export all as default for convenience
export default {
  ERRORS,
  SUCCESS,
  BUTTONS,
  LABELS,
  CONFIRM,
  TITLES,
  EMPTY_STATES,
}
