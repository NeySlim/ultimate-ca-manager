/** The CRL reason codes an operator may give (RFC 5280 §5.3.1), unspecified first; removeFromCRL is not one. */
export const REVOCATION_REASONS = [
  'unspecified',
  'keyCompromise',
  'cACompromise',
  'affiliationChanged',
  'superseded',
  'cessationOfOperation',
  'certificateHold',
  'privilegeWithdrawn',
  'aACompromise',
]
