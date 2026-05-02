CATEGORIES = {
    'auth': ['login_success', 'login_failure', 'logout', 'session_expired', 'mfa_enable', 'mfa_disable', 'password_change'],
    'users': ['user_create', 'user_update', 'user_delete', 'role_change', 'user_activate', 'user_deactivate'],
    'certificates': ['cert_issue', 'cert_revoke', 'cert_renew', 'cert_export', 'cert_delete'],
    'cas': ['ca_create', 'ca_update', 'ca_delete', 'ca_import', 'ca_export'],
    'csrs': ['csr_upload', 'csr_sign', 'csr_reject', 'csr_delete'],
    'settings': ['settings_update', 'backup_create', 'backup_restore', 'backup_delete'],
    'api_keys': ['api_key_create', 'api_key_revoke', 'api_key_delete'],
    'security': ['permission_denied', 'invalid_token', 'rate_limited', 'suspicious_activity'],
}
