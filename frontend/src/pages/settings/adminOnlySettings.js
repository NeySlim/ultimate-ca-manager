// Mirrors _ADMIN_ONLY_SETTINGS on the server: sent without admin:settings, these keys are dropped.
export const ADMIN_ONLY_SETTINGS = [
  'enforce_2fa', 'session_timeout', 'session_max_lifetime', 'max_login_attempts',
  'lockout_duration', 'metrics_token', 'key_recovery_dual_control',
  'min_password_length', 'max_password_length', 'password_require_uppercase',
  'password_require_lowercase', 'password_require_numbers', 'password_require_special',
  'hsts_enabled', 'hsts_include_subdomains', 'hsts_max_age',
  'base_url', 'protocol_base_url', 'acme_public_vhost', 'acme_public_port',
  'acme_public_tls_cert_id', 'auto_backup_enabled', 'backup_frequency',
  'backup_retention_days', 'backup_max_total_mb', 'backup_password', 'backup_kdf',
  'clear_backup_password', 'ocsp_responder_auto_renew', 'ocsp_responder_renew_days',
  'crl_auto_delete_expired_revoked', 'crl_auto_purge_stale_serials',
  'audit_retention_days', 'admin_allowed_networks', 'compliance_profile_default',
]

export function withoutAdminOnly(settings, canAdmin) {
  if (canAdmin) return settings
  return Object.fromEntries(
    Object.entries(settings).filter(([k]) => !ADMIN_ONLY_SETTINGS.includes(k)))
}
