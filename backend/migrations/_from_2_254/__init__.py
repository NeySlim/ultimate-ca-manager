"""The steps of migration 300, the upgrade of a 2.254 database to 3.0, and the 2.254 registry.

Each step is the 3.0 development migration of the same number, idempotent on both backends:
an upgrade interrupted after any step and started again ends in the same state. 154 is gone,
2.254 ran the same cleanup as its migration 136.
"""
import importlib

STEPS = (
    '138_flask_sessions', '139_dashboard_aggregates', '141_cluster_nodes',
    '142_serial_per_ca_and_proxy_links', '143_cluster_commands',
    '144_canonical_certificate_serials', '145_saml_request_next_path',
    '146_acme_order_replaced_certificates', '148_acme_replaced_certificate_fingerprints',
    '149_websocket_relay', '150_users_id_never_reused', '151_deploy_binding_attention',
    '152_shared_files', '153_encryption_keys', '155_windows_enrollment_profiles',
    '156_template_cn_pattern', '157_certificate_subject_key', '158_ca_parent_confirmation',
    '159_second_factor_failures', '160_backup_archives',
)

# Every name a 2.254 start leaves in `_migrations` (the migration files of tag v2.254-rc1,
# 000 to 019 included on PostgreSQL, where they are recorded without running)
PIVOT_NAMES = frozenset((
    '000_baseline_v252', '001_fix_dn_format', '002_add_sso_ssl_fields',
    '003_add_microsoft_ca_tables', '004_add_delta_crl', '005_add_approval_request_data',
    '006_fix_overbroad_approval_policies', '007_cdp_urls_use_refid', '008_cdp_ocsp_urls_use_http',
    '009_add_discovery_san_email_uri', '010_acme_client_key_type', '011_msca_enroll_on_behalf',
    '012_aia_ca_issuers', '013_fix_protocol_urls_https', '014_multi_url_and_cps',
    '015_add_rfc5280_constraints', '016_acme_pre_authorization', '017_remove_ca_template',
    '018_add_ssh_certificates', '019_acme_auto_approve_safe_default',
    '020_fix_acme_client_order_expires_at', '021_acme_client_order_account_link',
    '022_add_user_preferences', '023_sso_sync_role_on_login', '024_user_auth_source',
    '025_smtp_oauth2', '026_add_api_key_prefix', '027_acme_eab_credentials',
    '027_backfill_san_email', '028_scep_request_ca_scope', '029_encrypt_acme_account_keys',
    '030_add_certificate_san_upn', '031_acme_client_accounts', '032_ca_hsm_key_unique',
    '033_acme_authz_order_id_nullable', '034_add_ca_offline', '035_reconcile_pg_schema',
    '036_add_webhook_auth', '037_ca_template_pins', '038_eab_notes', '039_acme_terms_defaults',
    '040_ldap_required_groups', '041_webhook_deliveries', '042_key_recovery_requests',
    '043_users_email_not_unique', '044_users_email_unique_again', '045_sso_stable_identity',
    '046_2fa_enforcement', '047_acme_client_order_ca_account_link', '048_acme_ca_account_timing',
    '049_acme_key_source_preflight', '050_acme_proxy_ca_account_link', '051_acme_proxy_slug',
    '052_encrypt_dns_provider_credentials', '053_msca_crl_sync', '054_msca_admin_channel',
    '055_msca_inventory', '056_acme_preferred_chain', '057_pkcs11_config_keys',
    '058_certificate_invalidity_at', '059_ca_crl_schedule', '060_ca_url_slug',
    '061_encrypt_acme_client_eab_keys', '062_oidc_id_token_verification',
    '063_acme_order_replaces', '064_acme_order_profile', '065_reset_webauthn_sign_counts',
    '066_preserve_prev_2200_behaviors', '067_normalize_wildcard_authz', '068_scep_profiles',
    '069_eab_allowed_domains', '070_template_overrides', '071_certificate_template_autoenroll',
    '072_ad_connector', '073_certificate_template_ad_derived_subject',
    '074_certificate_template_enroll_acl', '075_certificate_template_pinned_subject_fields',
    '076_scep_profile_intune', '077_acme_client_account_dup_directory', '078_revoked_serials',
    '079_ca_external_csr', '080_crl_metadata_is_external', '081_deploy_hooks',
    '082_expiry_alert_thresholds', '083_ca_revocation', '084_approval_requests_index',
    '085_scep_request_profile', '086_scep_request_renewal_of', '087_webhooks_from_settings',
    '088_default_policies_off', '089_deploy_binding_include_root', '090_crl_deploy',
    '091_binding_reload_commands', '092_intune_apps', '093_ad_connector_health',
    '094_expiry_alerts_exclude_acme', '095_certificate_key_algo_backfill',
    '096_template_key_type_canonical', '098_audit_chain_keyed', '099_policy_operations',
    '100_user_webauthn_second_factor', '101_acme_eab_keys_import', '102_dead_settings',
    '103_saml_strict', '104_group_permissions_lists', '105_legacy_ldap_settings',
    '106_ca_signature_scheme', '107_ca_compliance_profile', '108_hsm_provider_certification',
    '109_user_custom_role_source', '110_ssh_ca_allow_any_principal', '111_acme_dns_update',
    '112_acme_proxy_authz_deactivation', '113_hsm_module_info', '114_ca_cross_certificates',
    '115_related_certificates', '116_ssh_ca_permissions', '117_related_cert_requests',
    '118_ca_issuance_hidden', '119_ssh_ca_allow_custom_key_id', '120_certificates_lookup_indexes',
    '121_acme_renewal_order_duplicates', '122_strip_port_zero_protocol_urls',
    '123_acme_client_order_pending_key_lease', '124_unique_provider_account_webhook_names',
    '127_certificate_template_custom_extensions', '128_revoked_key_digest_upstream_revocations',
    '129_compromised_keys', '130_auth_certificate_serial_per_issuer', '131_deploy_target_http',
    '132_est_signer_certs', '133_audit_log_text_fields', '134_crl_number_unique_and_counters',
    '135_user_totp_step_session_version', '136_lifted_hold_leftovers', '137_ldap_start_tls',
))

# What else a 2.254 registry may hold: 001 to 042 of the 2.0 series, which the 2.52 baseline
# (000) folded and kept recorded, and the name migrate_v1_to_v2 writes
RECORDED_BEFORE_2_52 = frozenset((
    '001_add_api_keys', '002_upgrade_users_table', '003_create_v2_tables',
    '004_create_webauthn_table', '005_create_webauthn_challenges', '006_add_locked_until',
    '007_add_audit_hash_chain', '008_fix_certificate_templates', '009_add_password_reset_fields',
    '010_create_acme_client_tables', '011_add_notification_retry_count',
    '012_sync_acme_client_schema', '013_create_acme_domains', '014_add_proxy_order_fields',
    '015_add_upstream_authz_urls', '016_create_hsm_tables', '017_add_hsm_key_to_cas',
    '018_add_user_custom_role', '019_add_groups_updated_at', '020_update_trusted_certificates',
    '021_add_group_members_role', '022_add_ski_aki_columns', '023_add_acme_domain_issuing_ca',
    '024_create_acme_local_domains', '025_add_notification_cooldown', '026_add_smtp_auth_flag',
    '027_add_smtp_content_type', '028_add_email_template', '029_add_email_text_template',
    '030_fix_schema_mismatches', '031_seed_default_policies', '032_seed_report_schedule',
    '033_add_saml_metadata_url', '034_add_saml_sp_cert_source', '035_add_ldap_group_member_attr',
    '036_rename_user_role_add_auditor', '037_add_mtls_settings',
    '040_create_discovered_certificate_table', '041_add_discovery_dns_hostname',
    '042_add_discovery_san_sni', 'v1_to_v2_migration',
))


def step(name):
    """The module of one step."""
    return importlib.import_module(f'{__name__}.{name}')
