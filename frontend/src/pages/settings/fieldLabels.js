/**
 * Label of each field the settings save bar can name (the mockup lists the changed fields:
 * « Modifié, non enregistré : Nom de l’instance, Port. »). Keys: a setting name, or
 * `<part>.<field>` for a part saved by its own route.
 */
export const FIELD_LABELS = {
  // Général
  system_name: 'settings.systemName',
  base_url: 'settings.baseUrl',
  protocol_base_url: 'settings.protocolBaseUrl',
  http_protocol_port: 'settings.httpProtocolPort',
  acme_public_vhost: 'settings.acmePublicVhost',
  acme_public_port: 'settings.acmePublicPort',
  acme_public_tls_cert_id: 'settings.acmePublicTlsCertId',
  session_timeout: 'settings.sessionTimeout',
  max_login_attempts: 'settings.maxLoginAttempts',
  lockout_duration: 'settings.lockoutDuration',
  timezone: 'settings.timezone',
  date_format: 'settings.dateFormat',
  show_time: 'settings.showTime',
  // Sécurité
  enforce_2fa: 'settings.enforce2fa',
  admin_allowed_networks: 'settings.adminAllowlistNetworks',
  hsts_enabled: 'settings.hstsEnabled',
  hsts_include_subdomains: 'settings.hstsIncludeSubdomains',
  hsts_max_age: 'settings.hstsMaxAge',
  ocsp_response_validity_hours: 'settings.ocspResponseValidity',
  ocsp_responder_auto_renew: 'settings.ocspResponderAutoRenew',
  ocsp_responder_renew_days: 'settings.ocspResponderRenewDays',
  crl_auto_delete_expired_revoked: 'settings.crlAutoDeleteExpiredRevoked',
  crl_auto_purge_stale_serials: 'settings.crlAutoPurgeStaleSerials',
  key_recovery_dual_control: 'settings.keyRecoveryDualControl',
  min_password_length: 'settings.minPasswordLength',
  password_require_uppercase: 'settings.requireUppercase',
  password_require_numbers: 'settings.requireNumbers',
  password_require_special: 'settings.requireSpecial',
  session_max_lifetime: 'settings.sessionDuration',
  // Sauvegarde
  auto_backup_enabled: 'settings.enableAutoBackups',
  backup_frequency: 'settings.backupFrequency',
  backup_kdf: 'settings.backupKdf',
  backup_password: 'settings.autoBackupPassword',
  backup_retention_days: 'settings.retentionPeriod',
  backup_max_total_mb: 'settings.backupMaxTotalMb',
  // Audit et syslog
  audit_retention_days: 'settings.logRetention',
  'syslog.enabled': 'settings.enableSyslog',
  'syslog.host': 'settings.syslogHost',
  'syslog.port': 'settings.syslogPort',
  'syslog.protocol': 'settings.syslogProtocol',
  'syslog.framing': 'settings.syslogFraming',
  'syslog.tls': 'settings.syslogTls',
  'syslog.tls_verify': 'settings.syslogTlsVerify',
  'syslog.categories': 'settings.syslogCategories',
  // SMTP
  smtp_host: 'settings.smtpHost',
  smtp_port: 'settings.smtpPort',
  smtp_security: 'settings.smtpSecurity',
  smtp_from_email: 'settings.fromEmail',
  smtp_auth_method: 'settings.smtpAuthMethod',
  smtp_content_type: 'settings.emailFormat',
  smtp_username: 'settings.smtpUsername',
  smtp_password: 'settings.smtpPassword',
  smtp_oauth_tenant_id: 'settings.smtpOauthTenant',
  smtp_oauth_client_id: 'settings.smtpOauthClientId',
  smtp_oauth_client_secret: 'settings.smtpOauthClientSecret',
  smtp_oauth_authorize_url: 'settings.smtpOauthAuthorizeUrl',
  smtp_oauth_token_url: 'settings.smtpOauthTokenUrl',
  smtp_oauth_scope: 'settings.smtpOauthScope',
  smtp_oauth_redirect_uri: 'settings.smtpOauthRedirectUri',
  'expiry.enabled': 'settings.enableExpiryAlerts',
  'expiry.alert_days': 'settings.alertDays',
  'expiry.recipients': 'settings.alertRecipients',
  'expiry.include_revoked': 'settings.includeRevoked',
  'expiry.exclude_acme': 'settings.excludeAcme',
  // Certificate Transparency
  'ct.enabled': 'settings.ctEnabled',
  'ct.auto_submit': 'settings.ctAutoSubmit',
  'ct.embed_sct': 'settings.ctEmbedSct',
  'ct.required': 'settings.ctRequired',
  'ct.log_urls': 'settings.ctLogUrls',
  // Renouvellement automatique
  'ar.enabled': 'settings.autoRenewalEnabled',
  'ar.days_before_expiry': 'settings.autoRenewalDays',
  'ar.sources': 'settings.autoRenewalSources',
  'ar.notify_on_renewal': 'settings.autoRenewalNotifyOnRenewal',
  'ar.notify_on_failure': 'settings.autoRenewalNotifyOnFailure',
  'ar.notify_emails': 'settings.autoRenewalNotifyEmails',
  // mTLS
  'mtls.enabled': 'settings.mtls.enable',
  'mtls.trusted_ca_id': 'settings.mtls.trustedCA',
  'mtls.required': 'settings.mtls.required',
}

/**
 * The labels of the changed fields, in order and once each: a field without a known label
 * is named by its section, so nothing pending goes unnamed.
 */
export function changedLabels(changes, t, sectionLabel) {
  const seen = new Set()
  const out = []
  for (const { key, section } of changes) {
    const label = FIELD_LABELS[key] ? t(FIELD_LABELS[key]) : sectionLabel(section)
    if (!seen.has(label)) {
      seen.add(label)
      out.push(label)
    }
  }
  return out
}
