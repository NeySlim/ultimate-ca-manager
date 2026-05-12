from services.audit import AuditService, audit_log, audit_event  # noqa: F401

# Webhook auth audit action constants (WK-2, issue #116).
# These are free-form strings consumed by AuditService.log_action(action=...).
#   webhook.auth_configured     — auth_type changed from 'none' to a live type
#   webhook.auth_disabled       — auth_type changed back to 'none'
#   webhook.auth_token_rotated  — token replaced on an existing auth config
#   webhook.auth_token_invalid  — delivery aborted: stored token failed decryption
