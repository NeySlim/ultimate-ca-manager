/**
 * Intelligent Badge Variant Mapping
 * Returns appropriate badge variant based on context and value
 * 
 * Principle: "Form Follows Function"
 * Badge colors are assigned based on semantic meaning, not arbitrarily
 */

const BADGE_MAPPING = {
  // Certificate Type (following prototype colors)
  'cert-type': {
    'server': 'info',      // Blue (like prototype badge-info)
    'acme': 'success',     // Green (like prototype badge-success)
    'internal': 'info',    // Blue/cyan
    'client': 'secondary', // Grey
    'code signing': 'warning',
  },
  
  // Certificate Status
  'cert-status': {
    'valid': 'success',
    'expiring': 'warning',
    'expired': 'danger',
    'revoked': 'danger',
    'pending': 'warning',
  },
  
  // CA Type
  'ca-type': {
    'root': 'info',
    'intermediate': 'secondary',
    'subordinate': 'secondary',
  },
  
  // CA Status
  'ca-status': {
    'active': 'success',
    'inactive': 'danger',
    'expired': 'danger',
  },
  
  // ACME Order Status
  'acme-order-status': {
    'valid': 'success',
    'pending': 'warning',
    'invalid': 'danger',
    'processing': 'info',
    'ready': 'success',
  },
  
  // SCEP Request Status
  'scep-status': {
    'pending': 'warning',
    'approved': 'success',
    'rejected': 'danger',
  },
  
  // User Role
  'user-role': {
    'admin': 'danger',     // Red = power/importance
    'administrator': 'danger',
    'user': 'secondary',
    'viewer': 'secondary',
  },
  
  // User Status
  'user-status': {
    'active': 'success',
    'locked': 'danger',
    'inactive': 'secondary',
  },
  
  // CSR Status
  'csr-status': {
    'pending': 'warning',
    'approved': 'success',
    'rejected': 'danger',
    'signed': 'success',
  },
  
  // CRL Status
  'crl-status': {
    'current': 'success',
    'expired': 'danger',
    'generating': 'info',
  },
  
  // Template Status
  'template-status': {
    'active': 'success',
    'inactive': 'secondary',
  },
};

/**
 * Get badge variant based on context and value
 * 
 * @param {string} context - Context (e.g., 'cert-status', 'user-role')
 * @param {string} value - Value to map (e.g., 'valid', 'admin')
 * @returns {string} Badge variant ('success', 'warning', 'danger', 'info', 'secondary')
 */
export function getBadgeVariant(context, value) {
  const contextMap = BADGE_MAPPING[context];
  
  if (!contextMap) {
    console.warn(`Unknown badge context: ${context}`);
    return 'secondary'; // Default fallback
  }
  
  const variant = contextMap[value?.toLowerCase()];
  
  if (!variant) {
    console.warn(`Unknown value "${value}" for context "${context}"`);
    return 'secondary'; // Default fallback
  }
  
  return variant;
}

/**
 * Get badge variant for certificate type
 * Matches prototype-dashboard.html color scheme
 */
export function getCertTypeVariant(type) {
  return getBadgeVariant('cert-type', type);
}

/**
 * Get badge variant for certificate status
 * Shorthand helper
 */
export function getCertStatusVariant(status) {
  return getBadgeVariant('cert-status', status);
}

/**
 * Get badge variant for CA type
 * Shorthand helper
 */
export function getCATypeVariant(type) {
  return getBadgeVariant('ca-type', type);
}

/**
 * Get badge variant for user role
 * Shorthand helper
 */
export function getUserRoleVariant(role) {
  return getBadgeVariant('user-role', role);
}

export default getBadgeVariant;
