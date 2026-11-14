-- Schema of UCM 2.254, the 3.0 upgrade pivot, as its models create it (postgresql), with its
-- migrations recorded as applied. Generated from the v2.254-rc1 tag by scripts/schema_fixture.py;
-- never edited by hand.

CREATE TABLE acme_accounts (
	id SERIAL NOT NULL, 
	account_id VARCHAR(64) NOT NULL, 
	jwk TEXT NOT NULL, 
	jwk_thumbprint VARCHAR(128) NOT NULL, 
	contact TEXT, 
	status VARCHAR(20) NOT NULL, 
	terms_of_service_agreed BOOLEAN, 
	external_account_binding TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_acme_accounts_account_id ON acme_accounts (account_id);

CREATE UNIQUE INDEX ix_acme_accounts_jwk_thumbprint ON acme_accounts (jwk_thumbprint);

CREATE TABLE acme_client_accounts (
	id SERIAL NOT NULL, 
	directory_url VARCHAR(500) NOT NULL, 
	label VARCHAR(100) NOT NULL, 
	email VARCHAR(255) NOT NULL, 
	account_url VARCHAR(500), 
	account_key TEXT, 
	account_key_algorithm VARCHAR(20) NOT NULL, 
	eab_kid VARCHAR(255), 
	eab_hmac_key TEXT, 
	is_default BOOLEAN NOT NULL, 
	proxy_slug VARCHAR(63), 
	proxy_enabled BOOLEAN NOT NULL, 
	order_poll_timeout_sec INTEGER NOT NULL, 
	order_poll_interval_sec INTEGER NOT NULL, 
	http_timeout_sec INTEGER NOT NULL, 
	preferred_chain VARCHAR(255), 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_acme_client_accounts_directory_url ON acme_client_accounts (directory_url);

CREATE UNIQUE INDEX ix_acme_client_accounts_proxy_slug ON acme_client_accounts (proxy_slug);

CREATE UNIQUE INDEX uq_acme_client_accounts_label ON acme_client_accounts (label);

CREATE TABLE acme_eab_credentials (
	id SERIAL NOT NULL, 
	kid VARCHAR(255) NOT NULL, 
	hmac_key_b64 TEXT NOT NULL, 
	label VARCHAR(255), 
	created_by_user_id INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	expires_at TIMESTAMP WITHOUT TIME ZONE, 
	used_at TIMESTAMP WITHOUT TIME ZONE, 
	used_by_account_id VARCHAR(64), 
	revoked_at TIMESTAMP WITHOUT TIME ZONE, 
	revoked_by_user_id INTEGER, 
	status VARCHAR(20) NOT NULL, 
	notes TEXT, 
	allowed_domains TEXT, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_acme_eab_credentials_kid ON acme_eab_credentials (kid);

CREATE INDEX ix_acme_eab_credentials_status ON acme_eab_credentials (status);

CREATE TABLE acme_nonces (
	id SERIAL NOT NULL, 
	token VARCHAR(64) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	used BOOLEAN, 
	used_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE INDEX idx_nonce_expires ON acme_nonces (expires_at);

CREATE UNIQUE INDEX ix_acme_nonces_token ON acme_nonces (token);

CREATE TABLE ad_connector_config (
	id SERIAL NOT NULL, 
	server VARCHAR(500), 
	port INTEGER, 
	use_ssl BOOLEAN, 
	verify_ssl BOOLEAN, 
	ca_bundle TEXT, 
	base_dn VARCHAR(500), 
	bind_dn VARCHAR(500), 
	bind_password VARCHAR(500), 
	enabled BOOLEAN, 
	last_test_at TIMESTAMP WITHOUT TIME ZONE, 
	last_test_result VARCHAR(500), 
	health TEXT, 
	health_probe_interval INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	created_by VARCHAR(80), 
	PRIMARY KEY (id)
);

CREATE TABLE audit_logs (
	id SERIAL NOT NULL, 
	timestamp TIMESTAMP WITHOUT TIME ZONE, 
	username TEXT, 
	action VARCHAR(100) NOT NULL, 
	resource_type VARCHAR(50), 
	resource_id TEXT, 
	resource_name TEXT, 
	details TEXT, 
	ip_address VARCHAR(45), 
	user_agent TEXT, 
	success BOOLEAN, 
	prev_hash VARCHAR(64), 
	entry_hash VARCHAR(64), 
	hash_version INTEGER, 
	hash_key_id VARCHAR(16), 
	chain_start INTEGER, 
	retired_keys TEXT, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_audit_logs_timestamp ON audit_logs (timestamp);

CREATE INDEX ix_audit_logs_username ON audit_logs (username);

CREATE TABLE certificate_templates (
	id SERIAL NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	description TEXT, 
	template_type VARCHAR(50) NOT NULL, 
	key_type VARCHAR(20), 
	validity_days INTEGER, 
	digest VARCHAR(20), 
	dn_template TEXT, 
	extensions_template TEXT NOT NULL, 
	is_system BOOLEAN, 
	is_active BOOLEAN, 
	enforce_san_types BOOLEAN DEFAULT false NOT NULL, 
	ad_derived_subject BOOLEAN, 
	autoenroll_enabled BOOLEAN, 
	allowed_ad_group VARCHAR(255), 
	pinned_subject_fields TEXT, 
	custom_extensions TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	created_by VARCHAR(80), 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_by VARCHAR(80), 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_certificate_templates_name ON certificate_templates (name);

CREATE TABLE compromised_keys (
	id SERIAL NOT NULL, 
	public_key_sha256 VARCHAR(64) NOT NULL, 
	revoked_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	source VARCHAR(20) NOT NULL, 
	cert_refid VARCHAR(36), 
	subject TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_compromised_keys_public_key_sha256 ON compromised_keys (public_key_sha256);

CREATE TABLE crl_number_counters (
	id SERIAL NOT NULL, 
	issuer_key VARCHAR(64) NOT NULL, 
	last_number INTEGER NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_crl_number_counters_issuer_key ON crl_number_counters (issuer_key);

CREATE TABLE crls (
	id SERIAL NOT NULL, 
	caref VARCHAR(36) NOT NULL, 
	descr VARCHAR(255) NOT NULL, 
	text TEXT NOT NULL, 
	serial INTEGER, 
	lifetime INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_crls_caref ON crls (caref);

CREATE TABLE deploy_deliveries (
	id SERIAL NOT NULL, 
	binding_id INTEGER NOT NULL, 
	binding_type VARCHAR(16) NOT NULL, 
	event_type VARCHAR(32) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	attempts INTEGER NOT NULL, 
	max_attempts INTEGER NOT NULL, 
	next_attempt_at TIMESTAMP WITHOUT TIME ZONE, 
	last_error TEXT, 
	detail TEXT, 
	triggered_by VARCHAR(80), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	delivered_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_deploy_deliveries_binding_id ON deploy_deliveries (binding_id);

CREATE INDEX ix_deploy_deliveries_binding_type ON deploy_deliveries (binding_type);

CREATE INDEX ix_deploy_deliveries_next_attempt_at ON deploy_deliveries (next_attempt_at);

CREATE INDEX ix_deploy_deliveries_status ON deploy_deliveries (status);

CREATE TABLE deploy_targets (
	id SERIAL NOT NULL, 
	name VARCHAR(120) NOT NULL, 
	kind VARCHAR(8) DEFAULT 'ssh' NOT NULL, 
	host VARCHAR(255) NOT NULL, 
	port INTEGER NOT NULL, 
	username VARCHAR(120) NOT NULL, 
	private_key TEXT NOT NULL, 
	url VARCHAR(2048), 
	http_method VARCHAR(8), 
	http_headers TEXT, 
	body_template TEXT, 
	tls_ca_pem TEXT, 
	allow_private_key BOOLEAN DEFAULT '0' NOT NULL, 
	public_key TEXT, 
	host_key TEXT, 
	reload_command VARCHAR(512), 
	enabled BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	created_by VARCHAR(80), 
	last_success_at TIMESTAMP WITHOUT TIME ZONE, 
	last_failure_at TIMESTAMP WITHOUT TIME ZONE, 
	failure_count INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);

CREATE TABLE discovery_scan_profiles (
	id SERIAL NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	description TEXT, 
	targets TEXT NOT NULL, 
	ports TEXT NOT NULL, 
	schedule_enabled BOOLEAN NOT NULL, 
	schedule_interval_minutes INTEGER NOT NULL, 
	notify_on_new BOOLEAN NOT NULL, 
	notify_on_change BOOLEAN NOT NULL, 
	notify_on_expiry BOOLEAN NOT NULL, 
	notify_email VARCHAR(255), 
	timeout INTEGER NOT NULL, 
	max_workers INTEGER NOT NULL, 
	resolve_dns BOOLEAN NOT NULL, 
	last_scan_at TIMESTAMP WITHOUT TIME ZONE, 
	next_scan_at TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);

CREATE TABLE dns_providers (
	id SERIAL NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	provider_type VARCHAR(50) NOT NULL, 
	credentials TEXT, 
	zones TEXT, 
	is_default BOOLEAN, 
	enabled BOOLEAN, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX uq_dns_providers_name ON dns_providers (name);

CREATE TABLE groups (
	id SERIAL NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	description TEXT, 
	permissions JSON, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);

CREATE TABLE intune_apps (
	id SERIAL NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	tenant_id VARCHAR(255) NOT NULL, 
	client_id VARCHAR(255) NOT NULL, 
	client_secret TEXT NOT NULL, 
	last_test_at TIMESTAMP WITHOUT TIME ZONE, 
	last_test_result VARCHAR(255), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	created_by VARCHAR(80), 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_by VARCHAR(80), 
	PRIMARY KEY (id), 
	UNIQUE (name)
);

CREATE TABLE key_recovery_requests (
	id SERIAL NOT NULL, 
	cert_id INTEGER NOT NULL, 
	cert_refid VARCHAR(64), 
	cert_cn VARCHAR(255), 
	reason TEXT NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	requested_by VARCHAR(120) NOT NULL, 
	requested_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	decided_by VARCHAR(120), 
	decided_at TIMESTAMP WITHOUT TIME ZONE, 
	decision_note TEXT, 
	recovered_by VARCHAR(120), 
	recovered_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_key_recovery_requests_cert_id ON key_recovery_requests (cert_id);

CREATE INDEX ix_key_recovery_requests_status ON key_recovery_requests (status);

CREATE TABLE microsoft_cas (
	id SERIAL NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	server VARCHAR(500) NOT NULL, 
	ca_name VARCHAR(200), 
	auth_method VARCHAR(20) NOT NULL, 
	username VARCHAR(500), 
	password VARCHAR(500), 
	client_cert_pem TEXT, 
	client_key_pem TEXT, 
	kerberos_principal VARCHAR(500), 
	kerberos_keytab_path VARCHAR(500), 
	use_ssl BOOLEAN, 
	verify_ssl BOOLEAN, 
	ca_bundle TEXT, 
	default_template VARCHAR(200), 
	enabled BOOLEAN, 
	last_test_at TIMESTAMP WITHOUT TIME ZONE, 
	last_test_result VARCHAR(500), 
	crl_sync_enabled BOOLEAN, 
	crl_url TEXT, 
	last_crl_sync_at TIMESTAMP WITHOUT TIME ZONE, 
	last_crl_sync_result VARCHAR(500), 
	winrm_enabled BOOLEAN, 
	winrm_host VARCHAR(500), 
	winrm_port INTEGER, 
	winrm_use_ssl BOOLEAN, 
	winrm_verify_ssl BOOLEAN, 
	winrm_transport VARCHAR(20), 
	winrm_username VARCHAR(500), 
	winrm_password TEXT, 
	ca_config VARCHAR(500), 
	inventory_sync_enabled BOOLEAN, 
	last_inventory_sync_at TIMESTAMP WITHOUT TIME ZONE, 
	last_inventory_sync_result VARCHAR(500), 
	last_synced_request_id INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	created_by VARCHAR(80), 
	PRIMARY KEY (id), 
	UNIQUE (name)
);

CREATE TABLE notification_config (
	id SERIAL NOT NULL, 
	type VARCHAR(50) NOT NULL, 
	enabled BOOLEAN, 
	days_before INTEGER, 
	alert_days TEXT, 
	include_revoked BOOLEAN, 
	exclude_acme BOOLEAN DEFAULT false NOT NULL, 
	recipients TEXT, 
	subject_template VARCHAR(255), 
	description VARCHAR(512), 
	cooldown_hours INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_notification_config_type ON notification_config (type);

CREATE TABLE notification_log (
	id SERIAL NOT NULL, 
	type VARCHAR(50) NOT NULL, 
	recipient VARCHAR(255) NOT NULL, 
	subject VARCHAR(255), 
	body_preview TEXT, 
	status VARCHAR(20) NOT NULL, 
	error_message TEXT, 
	resource_type VARCHAR(50), 
	resource_id VARCHAR(100), 
	threshold_days INTEGER, 
	retry_count INTEGER, 
	sent_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE INDEX idx_notification_dedup ON notification_log (type, resource_type, resource_id, sent_at);

CREATE INDEX ix_notification_log_sent_at ON notification_log (sent_at);

CREATE INDEX ix_notification_log_status ON notification_log (status);

CREATE INDEX ix_notification_log_type ON notification_log (type);

CREATE TABLE pro_custom_roles (
	id SERIAL NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	description TEXT, 
	permissions JSON, 
	inherits_from INTEGER, 
	is_system BOOLEAN, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (name), 
	FOREIGN KEY(inherits_from) REFERENCES pro_custom_roles (id)
);

CREATE TABLE pro_sso_providers (
	id SERIAL NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	provider_type VARCHAR(50) NOT NULL, 
	enabled BOOLEAN, 
	is_default BOOLEAN, 
	display_name VARCHAR(200), 
	icon VARCHAR(100), 
	saml_metadata_url VARCHAR(500), 
	saml_entity_id VARCHAR(500), 
	saml_sso_url VARCHAR(500), 
	saml_slo_url VARCHAR(500), 
	saml_certificate TEXT, 
	saml_sign_requests BOOLEAN, 
	saml_sp_cert_source VARCHAR(50), 
	saml_name_id_format VARCHAR(255), 
	saml_allow_idp_initiated BOOLEAN DEFAULT false NOT NULL, 
	saml_verify_ssl BOOLEAN, 
	saml_ca_bundle TEXT, 
	oauth2_client_id VARCHAR(500), 
	oauth2_client_secret VARCHAR(500), 
	oauth2_auth_url VARCHAR(500), 
	oauth2_token_url VARCHAR(500), 
	oauth2_userinfo_url VARCHAR(500), 
	oauth2_scopes VARCHAR(500), 
	oauth2_issuer VARCHAR(500), 
	oauth2_jwks_uri VARCHAR(500), 
	id_token_verify BOOLEAN NOT NULL, 
	oauth2_verify_ssl BOOLEAN, 
	oauth2_ca_bundle TEXT, 
	ldap_server VARCHAR(500), 
	ldap_port INTEGER, 
	ldap_use_ssl BOOLEAN, 
	ldap_start_tls BOOLEAN DEFAULT false NOT NULL, 
	ldap_verify_ssl BOOLEAN, 
	ldap_ca_bundle TEXT, 
	ldap_bind_dn VARCHAR(500), 
	ldap_bind_password VARCHAR(500), 
	ldap_base_dn VARCHAR(500), 
	ldap_user_filter VARCHAR(500), 
	ldap_group_filter VARCHAR(500), 
	ldap_username_attr VARCHAR(100), 
	ldap_email_attr VARCHAR(100), 
	ldap_fullname_attr VARCHAR(100), 
	ldap_uid_attr VARCHAR(100), 
	ldap_group_member_attr VARCHAR(100), 
	ldap_required_groups TEXT, 
	account_status_attr VARCHAR(100), 
	attribute_mapping TEXT, 
	role_mapping TEXT, 
	default_role VARCHAR(50), 
	auto_create_users BOOLEAN, 
	auto_update_users BOOLEAN, 
	sync_role_on_login BOOLEAN NOT NULL, 
	enforce_2fa BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	last_used_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);

CREATE TABLE pro_sso_saml_message_ids (
	id SERIAL NOT NULL, 
	kind VARCHAR(16) NOT NULL, 
	message_id VARCHAR(256) NOT NULL, 
	provider_id INTEGER NOT NULL, 
	expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_saml_message_kind_id UNIQUE (kind, message_id)
);

CREATE INDEX ix_pro_sso_saml_message_ids_expires_at ON pro_sso_saml_message_ids (expires_at);

CREATE TABLE related_cert_requests (
	id SERIAL NOT NULL, 
	request_sha256 VARCHAR(64) NOT NULL, 
	spki_sha256 VARCHAR(64) NOT NULL, 
	request_time TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (request_sha256)
);

CREATE INDEX ix_related_cert_requests_request_time ON related_cert_requests (request_time);

CREATE TABLE smtp_config (
	id SERIAL NOT NULL, 
	smtp_host VARCHAR(255), 
	smtp_port INTEGER, 
	smtp_user VARCHAR(255), 
	smtp_password VARCHAR(512), 
	smtp_from VARCHAR(255), 
	smtp_from_name VARCHAR(255), 
	smtp_use_tls BOOLEAN, 
	smtp_use_ssl BOOLEAN, 
	smtp_auth BOOLEAN, 
	smtp_content_type VARCHAR(10), 
	email_template TEXT, 
	email_text_template TEXT, 
	enabled BOOLEAN, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_by VARCHAR(80), 
	smtp_auth_method VARCHAR(20) NOT NULL, 
	smtp_oauth_provider VARCHAR(20), 
	smtp_oauth_tenant_id VARCHAR(100), 
	smtp_oauth_client_id VARCHAR(255), 
	smtp_oauth_client_secret VARCHAR(1024), 
	smtp_oauth_refresh_token VARCHAR(4096), 
	smtp_oauth_authorize_url VARCHAR(512), 
	smtp_oauth_token_url VARCHAR(512), 
	smtp_oauth_scope VARCHAR(512), 
	smtp_oauth_redirect_uri VARCHAR(512), 
	PRIMARY KEY (id)
);

CREATE TABLE system_config (
	id SERIAL NOT NULL, 
	key VARCHAR(100) NOT NULL, 
	value TEXT, 
	encrypted BOOLEAN, 
	description VARCHAR(255), 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_by VARCHAR(80), 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_system_config_key ON system_config (key);

CREATE TABLE trusted_certificates (
	id SERIAL NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	description TEXT, 
	certificate_pem TEXT NOT NULL, 
	fingerprint_sha256 VARCHAR(64) NOT NULL, 
	fingerprint_sha1 VARCHAR(40), 
	subject VARCHAR(500), 
	issuer VARCHAR(500), 
	serial_number VARCHAR(100), 
	not_before TIMESTAMP WITHOUT TIME ZONE, 
	not_after TIMESTAMP WITHOUT TIME ZONE, 
	purpose VARCHAR(100), 
	added_by VARCHAR(80), 
	added_at TIMESTAMP WITHOUT TIME ZONE, 
	notes TEXT, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_trusted_certificates_fingerprint_sha1 ON trusted_certificates (fingerprint_sha1);

CREATE UNIQUE INDEX ix_trusted_certificates_fingerprint_sha256 ON trusted_certificates (fingerprint_sha256);

CREATE INDEX ix_trusted_certificates_name ON trusted_certificates (name);

CREATE TABLE webhook_deliveries (
	id SERIAL NOT NULL, 
	endpoint_id INTEGER NOT NULL, 
	event_type VARCHAR(64) NOT NULL, 
	payload TEXT NOT NULL, 
	event_timestamp VARCHAR(40) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	attempts INTEGER NOT NULL, 
	max_attempts INTEGER NOT NULL, 
	next_attempt_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	last_response_code INTEGER, 
	last_error TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	delivered_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_webhook_deliveries_endpoint_id ON webhook_deliveries (endpoint_id);

CREATE INDEX ix_webhook_deliveries_next_attempt_at ON webhook_deliveries (next_attempt_at);

CREATE INDEX ix_webhook_deliveries_status ON webhook_deliveries (status);

CREATE TABLE webhook_endpoints (
	id SERIAL NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	url VARCHAR(500) NOT NULL, 
	secret VARCHAR(255), 
	events TEXT, 
	ca_filter VARCHAR(100), 
	enabled BOOLEAN, 
	last_success TIMESTAMP WITHOUT TIME ZONE, 
	last_failure TIMESTAMP WITHOUT TIME ZONE, 
	failure_count INTEGER, 
	custom_headers TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	auth_type VARCHAR(20) NOT NULL, 
	_auth_token TEXT, 
	auth_username VARCHAR(255), 
	auth_header_name VARCHAR(100), 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX uq_webhook_endpoints_name ON webhook_endpoints (name);

CREATE TABLE acme_dns_update_keys (
	id SERIAL NOT NULL, 
	acme_client_account_id INTEGER NOT NULL, 
	eab_credential_id INTEGER, 
	eab_bound BOOLEAN NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	algorithm VARCHAR(32) NOT NULL, 
	secret TEXT NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	created_by_user_id INTEGER, 
	last_used_at TIMESTAMP WITHOUT TIME ZONE, 
	revoked_at TIMESTAMP WITHOUT TIME ZONE, 
	notes TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(acme_client_account_id) REFERENCES acme_client_accounts (id) ON DELETE CASCADE, 
	FOREIGN KEY(eab_credential_id) REFERENCES acme_eab_credentials (id) ON DELETE CASCADE, 
	UNIQUE (name)
);

CREATE INDEX ix_acme_dns_update_keys_acme_client_account_id ON acme_dns_update_keys (acme_client_account_id);

CREATE INDEX ix_acme_dns_update_keys_eab_credential_id ON acme_dns_update_keys (eab_credential_id);

CREATE INDEX ix_acme_dns_update_keys_status ON acme_dns_update_keys (status);

CREATE TABLE discovery_scan_runs (
	id SERIAL NOT NULL, 
	scan_profile_id INTEGER, 
	started_at TIMESTAMP WITHOUT TIME ZONE, 
	completed_at TIMESTAMP WITHOUT TIME ZONE, 
	status VARCHAR(32) NOT NULL, 
	total_targets INTEGER NOT NULL, 
	targets_scanned INTEGER NOT NULL, 
	certs_found INTEGER NOT NULL, 
	new_certs INTEGER NOT NULL, 
	changed_certs INTEGER NOT NULL, 
	errors INTEGER NOT NULL, 
	triggered_by VARCHAR(32) NOT NULL, 
	triggered_by_user VARCHAR(100), 
	timeout INTEGER NOT NULL, 
	max_workers INTEGER NOT NULL, 
	resolve_dns BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(scan_profile_id) REFERENCES discovery_scan_profiles (id) ON DELETE SET NULL
);

CREATE TABLE pro_role_permissions (
	id SERIAL NOT NULL, 
	role_id INTEGER NOT NULL, 
	permission VARCHAR(100) NOT NULL, 
	resource_type VARCHAR(50), 
	resource_id INTEGER, 
	PRIMARY KEY (id), 
	UNIQUE (role_id, permission, resource_type, resource_id), 
	FOREIGN KEY(role_id) REFERENCES pro_custom_roles (id)
);

CREATE TABLE ssh_cas (
	id SERIAL NOT NULL, 
	refid VARCHAR(36) NOT NULL, 
	descr VARCHAR(255) NOT NULL, 
	ca_type VARCHAR(10) NOT NULL, 
	public_key TEXT NOT NULL, 
	private_key TEXT NOT NULL, 
	key_type VARCHAR(20) NOT NULL, 
	fingerprint VARCHAR(100) NOT NULL, 
	serial_counter INTEGER NOT NULL, 
	default_ttl INTEGER, 
	max_ttl INTEGER, 
	default_extensions TEXT, 
	allowed_principals TEXT, 
	allow_any_principal BOOLEAN NOT NULL, 
	allow_custom_key_id BOOLEAN NOT NULL, 
	comment TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	created_by VARCHAR(80), 
	owner_group_id INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(owner_group_id) REFERENCES groups (id)
);

CREATE INDEX ix_ssh_cas_ca_type ON ssh_cas (ca_type);

CREATE INDEX ix_ssh_cas_fingerprint ON ssh_cas (fingerprint);

CREATE UNIQUE INDEX ix_ssh_cas_refid ON ssh_cas (refid);

CREATE TABLE users (
	id SERIAL NOT NULL, 
	username VARCHAR(80) NOT NULL, 
	email VARCHAR(120) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	full_name VARCHAR(255), 
	role VARCHAR(20) NOT NULL, 
	custom_role_id INTEGER, 
	custom_role_source VARCHAR(16), 
	active BOOLEAN, 
	mfa_enabled BOOLEAN, 
	totp_secret VARCHAR(32), 
	totp_confirmed BOOLEAN, 
	backup_codes TEXT, 
	totp_last_step BIGINT, 
	totp_exempt BOOLEAN, 
	webauthn_2fa BOOLEAN DEFAULT false NOT NULL, 
	force_password_change BOOLEAN, 
	password_reset_token VARCHAR(128), 
	password_reset_expires TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	last_login TIMESTAMP WITHOUT TIME ZONE, 
	login_count INTEGER, 
	failed_logins INTEGER, 
	locked_until TIMESTAMP WITHOUT TIME ZONE, 
	session_version INTEGER DEFAULT '0' NOT NULL, 
	preferences TEXT, 
	auth_source VARCHAR(20) NOT NULL, 
	sso_provider_id INTEGER, 
	sso_external_id VARCHAR(255), 
	sso_orphan_of VARCHAR(600), 
	PRIMARY KEY (id), 
	FOREIGN KEY(custom_role_id) REFERENCES pro_custom_roles (id) ON DELETE SET NULL, 
	FOREIGN KEY(sso_provider_id) REFERENCES pro_sso_providers (id) ON DELETE SET NULL
);

CREATE UNIQUE INDEX ix_users_email_local ON users (email) WHERE auth_source = 'local';

CREATE INDEX ix_users_sso_identity ON users (sso_provider_id, sso_external_id);

CREATE UNIQUE INDEX ix_users_username ON users (username);

CREATE TABLE api_keys (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	key_hash VARCHAR(255) NOT NULL, 
	key_prefix VARCHAR(20), 
	name VARCHAR(100) NOT NULL, 
	permissions TEXT NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	expires_at TIMESTAMP WITHOUT TIME ZONE, 
	last_used_at TIMESTAMP WITHOUT TIME ZONE, 
	is_active BOOLEAN, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE UNIQUE INDEX ix_api_keys_key_hash ON api_keys (key_hash);

CREATE TABLE auth_certificates (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	cert_pem BYTEA, 
	cert_serial VARCHAR(128) NOT NULL, 
	cert_subject TEXT NOT NULL, 
	cert_issuer TEXT, 
	cert_fingerprint VARCHAR(128), 
	name VARCHAR(128), 
	enabled BOOLEAN NOT NULL, 
	valid_from TIMESTAMP WITHOUT TIME ZONE, 
	valid_until TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	last_used_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_auth_certificates_cert_fingerprint ON auth_certificates (cert_fingerprint);

CREATE INDEX ix_auth_certificates_cert_serial ON auth_certificates (cert_serial);

CREATE UNIQUE INDEX uq_auth_certificates_issuer_serial ON auth_certificates (cert_issuer, cert_serial);

CREATE TABLE group_members (
	id SERIAL NOT NULL, 
	group_id INTEGER NOT NULL, 
	user_id INTEGER NOT NULL, 
	role VARCHAR(20), 
	joined_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (group_id, user_id), 
	FOREIGN KEY(group_id) REFERENCES groups (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE hsm_providers (
	id SERIAL NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	type VARCHAR(50) NOT NULL, 
	config TEXT NOT NULL, 
	status VARCHAR(20), 
	last_tested_at TIMESTAMP WITHOUT TIME ZONE, 
	error_message TEXT, 
	certification VARCHAR(32), 
	module_info TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	created_by INTEGER, 
	PRIMARY KEY (id), 
	UNIQUE (name), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE INDEX ix_hsm_providers_type ON hsm_providers (type);

CREATE TABLE pro_sso_sessions (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	provider_id INTEGER NOT NULL, 
	session_id VARCHAR(500), 
	sso_name_id VARCHAR(500), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	expires_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id), 
	FOREIGN KEY(provider_id) REFERENCES pro_sso_providers (id), 
	UNIQUE (session_id)
);

CREATE TABLE ssh_certificates (
	id SERIAL NOT NULL, 
	refid VARCHAR(36) NOT NULL, 
	descr VARCHAR(255), 
	ssh_ca_id INTEGER NOT NULL, 
	cert_type VARCHAR(10) NOT NULL, 
	key_id TEXT NOT NULL, 
	public_key TEXT NOT NULL, 
	certificate TEXT NOT NULL, 
	principals TEXT NOT NULL, 
	serial INTEGER NOT NULL, 
	valid_from TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	valid_to TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	key_type VARCHAR(20) NOT NULL, 
	fingerprint VARCHAR(100) NOT NULL, 
	extensions TEXT, 
	critical_options TEXT, 
	revoked BOOLEAN, 
	revoked_at TIMESTAMP WITHOUT TIME ZONE, 
	revoke_reason VARCHAR(255), 
	source VARCHAR(20), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	created_by VARCHAR(80), 
	owner_group_id INTEGER, 
	PRIMARY KEY (id), 
	FOREIGN KEY(ssh_ca_id) REFERENCES ssh_cas (id), 
	FOREIGN KEY(owner_group_id) REFERENCES groups (id)
);

CREATE INDEX ix_ssh_certificates_cert_type ON ssh_certificates (cert_type);

CREATE INDEX ix_ssh_certificates_fingerprint ON ssh_certificates (fingerprint);

CREATE UNIQUE INDEX ix_ssh_certificates_refid ON ssh_certificates (refid);

CREATE INDEX ix_ssh_certificates_revoked ON ssh_certificates (revoked);

CREATE INDEX ix_ssh_certificates_serial ON ssh_certificates (serial);

CREATE INDEX ix_ssh_certificates_ssh_ca_id ON ssh_certificates (ssh_ca_id);

CREATE INDEX ix_ssh_certificates_valid_to ON ssh_certificates (valid_to);

CREATE TABLE user_sessions (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	session_id VARCHAR(255) NOT NULL, 
	ip_address VARCHAR(45), 
	user_agent VARCHAR(500), 
	auth_method VARCHAR(50), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	last_activity TIMESTAMP WITHOUT TIME ZONE, 
	expires_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE UNIQUE INDEX ix_user_sessions_session_id ON user_sessions (session_id);

CREATE TABLE webauthn_challenges (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	challenge VARCHAR(128) NOT NULL, 
	challenge_type VARCHAR(20) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	used BOOLEAN, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE UNIQUE INDEX ix_webauthn_challenges_challenge ON webauthn_challenges (challenge);

CREATE TABLE webauthn_credentials (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	credential_id BYTEA NOT NULL, 
	public_key BYTEA NOT NULL, 
	sign_count INTEGER NOT NULL, 
	name VARCHAR(128), 
	aaguid VARCHAR(36), 
	transports TEXT, 
	is_backup_eligible BOOLEAN, 
	is_backup_device BOOLEAN, 
	user_verified BOOLEAN, 
	enabled BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	last_used_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE UNIQUE INDEX ix_webauthn_credentials_credential_id ON webauthn_credentials (credential_id);

CREATE TABLE hsm_keys (
	id SERIAL NOT NULL, 
	provider_id INTEGER NOT NULL, 
	key_identifier VARCHAR(255) NOT NULL, 
	label VARCHAR(255) NOT NULL, 
	algorithm VARCHAR(50) NOT NULL, 
	key_type VARCHAR(20) NOT NULL, 
	purpose VARCHAR(50) NOT NULL, 
	public_key_pem TEXT, 
	is_extractable BOOLEAN, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	extra_data TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_hsm_key_provider_identifier UNIQUE (provider_id, key_identifier), 
	FOREIGN KEY(provider_id) REFERENCES hsm_providers (id) ON DELETE CASCADE
);

CREATE INDEX ix_hsm_keys_algorithm ON hsm_keys (algorithm);

CREATE INDEX ix_hsm_keys_provider_id ON hsm_keys (provider_id);

CREATE TABLE certificate_authorities (
	id SERIAL NOT NULL, 
	refid VARCHAR(36) NOT NULL, 
	url_slug VARCHAR(64), 
	descr VARCHAR(255) NOT NULL, 
	crt TEXT NOT NULL, 
	prv TEXT, 
	csr TEXT, 
	serial INTEGER, 
	caref VARCHAR(36), 
	subject TEXT, 
	issuer TEXT, 
	serial_number VARCHAR(100), 
	ski VARCHAR(200), 
	valid_from TIMESTAMP WITHOUT TIME ZONE, 
	valid_to TIMESTAMP WITHOUT TIME ZONE, 
	imported_from VARCHAR(50), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	created_by VARCHAR(80), 
	owner_group_id INTEGER, 
	cdp_enabled BOOLEAN, 
	cdp_url VARCHAR(512), 
	delta_crl_enabled BOOLEAN, 
	delta_crl_interval INTEGER, 
	crl_validity_days INTEGER, 
	crl_publish_interval_hours INTEGER, 
	crl_digest VARCHAR(20), 
	signature_scheme VARCHAR(16) DEFAULT 'pkcs1v15' NOT NULL, 
	compliance_profile VARCHAR(16), 
	issuance_hidden BOOLEAN DEFAULT false NOT NULL, 
	ocsp_enabled BOOLEAN, 
	ocsp_url VARCHAR(512), 
	aia_ca_issuers_enabled BOOLEAN, 
	aia_ca_issuers_url VARCHAR(512), 
	cps_enabled BOOLEAN, 
	cps_uri TEXT, 
	cps_oid TEXT, 
	path_length INTEGER, 
	name_constraints_permitted TEXT, 
	name_constraints_excluded TEXT, 
	policy_constraints_require INTEGER, 
	policy_constraints_inhibit INTEGER, 
	inhibit_any_policy INTEGER, 
	sia_enabled BOOLEAN, 
	sia_urls TEXT, 
	hsm_key_id INTEGER, 
	offline BOOLEAN, 
	offline_reason VARCHAR(1024), 
	offline_mode VARCHAR(32), 
	revoked BOOLEAN, 
	revoked_at TIMESTAMP WITHOUT TIME ZONE, 
	revoke_reason VARCHAR(100), 
	invalidity_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (url_slug), 
	FOREIGN KEY(owner_group_id) REFERENCES groups (id), 
	FOREIGN KEY(hsm_key_id) REFERENCES hsm_keys (id)
);

CREATE UNIQUE INDEX ix_certificate_authorities_refid ON certificate_authorities (refid);

CREATE TABLE acme_domains (
	id SERIAL NOT NULL, 
	domain VARCHAR(255) NOT NULL, 
	dns_provider_id INTEGER NOT NULL, 
	issuing_ca_id INTEGER, 
	is_wildcard_allowed BOOLEAN, 
	auto_approve BOOLEAN, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	created_by VARCHAR(80), 
	PRIMARY KEY (id), 
	FOREIGN KEY(dns_provider_id) REFERENCES dns_providers (id), 
	FOREIGN KEY(issuing_ca_id) REFERENCES certificate_authorities (id)
);

CREATE UNIQUE INDEX ix_acme_domains_domain ON acme_domains (domain);

CREATE TABLE acme_local_domains (
	id SERIAL NOT NULL, 
	domain VARCHAR(255) NOT NULL, 
	issuing_ca_id INTEGER NOT NULL, 
	auto_approve BOOLEAN, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	created_by VARCHAR(80), 
	PRIMARY KEY (id), 
	FOREIGN KEY(issuing_ca_id) REFERENCES certificate_authorities (id)
);

CREATE UNIQUE INDEX ix_acme_local_domains_domain ON acme_local_domains (domain);

CREATE TABLE ca_cross_certificates (
	id SERIAL NOT NULL, 
	ca_id INTEGER NOT NULL, 
	crt TEXT NOT NULL, 
	fingerprint_sha256 VARCHAR(64) NOT NULL, 
	subject TEXT, 
	issuer TEXT, 
	issuer_caref VARCHAR(36), 
	serial_number VARCHAR(100), 
	aki VARCHAR(200), 
	valid_from TIMESTAMP WITHOUT TIME ZONE, 
	valid_to TIMESTAMP WITHOUT TIME ZONE, 
	served BOOLEAN DEFAULT false NOT NULL, 
	revoked BOOLEAN DEFAULT false NOT NULL, 
	revoked_at TIMESTAMP WITHOUT TIME ZONE, 
	revoke_reason VARCHAR(100), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	created_by VARCHAR(80), 
	PRIMARY KEY (id), 
	FOREIGN KEY(ca_id) REFERENCES certificate_authorities (id) ON DELETE CASCADE, 
	UNIQUE (fingerprint_sha256)
);

CREATE INDEX ix_ca_cross_certificates_ca_id ON ca_cross_certificates (ca_id);

CREATE INDEX ix_ca_cross_certificates_issuer_caref ON ca_cross_certificates (issuer_caref);

CREATE TABLE ca_template_pins (
	id SERIAL NOT NULL, 
	ca_id INTEGER NOT NULL, 
	template_id INTEGER NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_by VARCHAR(80), 
	PRIMARY KEY (id), 
	FOREIGN KEY(ca_id) REFERENCES certificate_authorities (id) ON DELETE CASCADE, 
	FOREIGN KEY(template_id) REFERENCES certificate_templates (id) ON DELETE CASCADE
);

CREATE INDEX ix_ca_template_pins_ca_id ON ca_template_pins (ca_id);

CREATE INDEX ix_ca_template_pins_template_id ON ca_template_pins (template_id);

CREATE TABLE certificate_policies (
	id SERIAL NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	description TEXT, 
	policy_type VARCHAR(50), 
	operations TEXT, 
	ca_id INTEGER, 
	template_id INTEGER, 
	rules TEXT NOT NULL, 
	requires_approval BOOLEAN, 
	approval_group_id INTEGER, 
	min_approvers INTEGER, 
	notify_on_violation BOOLEAN, 
	notification_emails TEXT, 
	is_active BOOLEAN, 
	priority INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	created_by VARCHAR(80), 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(ca_id) REFERENCES certificate_authorities (id), 
	FOREIGN KEY(template_id) REFERENCES certificate_templates (id), 
	FOREIGN KEY(approval_group_id) REFERENCES groups (id)
);

CREATE UNIQUE INDEX ix_certificate_policies_name ON certificate_policies (name);

CREATE TABLE certificates (
	id SERIAL NOT NULL, 
	refid VARCHAR(36) NOT NULL, 
	descr VARCHAR(255) NOT NULL, 
	caref VARCHAR(36), 
	crt TEXT, 
	csr TEXT, 
	prv TEXT, 
	cert_type VARCHAR(50), 
	subject TEXT, 
	subject_cn VARCHAR(255), 
	issuer TEXT, 
	serial_number VARCHAR(100), 
	aki VARCHAR(200), 
	ski VARCHAR(200), 
	valid_from TIMESTAMP WITHOUT TIME ZONE, 
	valid_to TIMESTAMP WITHOUT TIME ZONE, 
	key_algo VARCHAR(50), 
	san_dns TEXT, 
	san_ip TEXT, 
	san_email TEXT, 
	san_uri TEXT, 
	san_upn TEXT, 
	ocsp_uri VARCHAR(255), 
	ocsp_must_staple BOOLEAN, 
	private_key_location VARCHAR(20), 
	revoked BOOLEAN, 
	revoked_at TIMESTAMP WITHOUT TIME ZONE, 
	revoke_reason VARCHAR(100), 
	invalidity_at TIMESTAMP WITHOUT TIME ZONE, 
	archived BOOLEAN, 
	imported_from VARCHAR(50), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	created_by VARCHAR(80), 
	renewed_at TIMESTAMP WITHOUT TIME ZONE, 
	renewed_times INTEGER DEFAULT '0' NOT NULL, 
	source VARCHAR(20), 
	template_id INTEGER, 
	template_overrides TEXT, 
	owner_group_id INTEGER, 
	related_certificate_id INTEGER, 
	hybrid_role VARCHAR(16), 
	PRIMARY KEY (id), 
	FOREIGN KEY(caref) REFERENCES certificate_authorities (refid), 
	FOREIGN KEY(template_id) REFERENCES certificate_templates (id), 
	FOREIGN KEY(owner_group_id) REFERENCES groups (id)
);

CREATE INDEX ix_certificates_caref ON certificates (caref);

CREATE UNIQUE INDEX ix_certificates_refid ON certificates (refid);

CREATE INDEX ix_certificates_related_certificate_id ON certificates (related_certificate_id);

CREATE INDEX ix_certificates_serial_number ON certificates (serial_number);

CREATE TABLE crl_deploy_bindings (
	id SERIAL NOT NULL, 
	target_id INTEGER NOT NULL, 
	ca_id INTEGER NOT NULL, 
	crl_path VARCHAR(512) NOT NULL, 
	format VARCHAR(8) NOT NULL, 
	include_parent_crls BOOLEAN NOT NULL, 
	reload_command VARCHAR(512), 
	enabled BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	created_by VARCHAR(80), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_crl_deploy_binding UNIQUE (target_id, ca_id), 
	FOREIGN KEY(target_id) REFERENCES deploy_targets (id), 
	FOREIGN KEY(ca_id) REFERENCES certificate_authorities (id)
);

CREATE INDEX ix_crl_deploy_bindings_ca_id ON crl_deploy_bindings (ca_id);

CREATE INDEX ix_crl_deploy_bindings_target_id ON crl_deploy_bindings (target_id);

CREATE TABLE crl_metadata (
	id SERIAL NOT NULL, 
	ca_id INTEGER NOT NULL, 
	crl_number INTEGER NOT NULL, 
	this_update TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	next_update TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	crl_pem TEXT NOT NULL, 
	crl_der BYTEA NOT NULL, 
	is_delta BOOLEAN, 
	base_crl_number INTEGER, 
	is_external BOOLEAN, 
	revoked_count INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	generated_by VARCHAR(80), 
	PRIMARY KEY (id), 
	FOREIGN KEY(ca_id) REFERENCES certificate_authorities (id)
);

CREATE INDEX ix_crl_metadata_ca_id ON crl_metadata (ca_id);

CREATE INDEX ix_crl_metadata_created_at ON crl_metadata (created_at);

CREATE UNIQUE INDEX uix_crl_ca_number ON crl_metadata (ca_id, crl_number);

CREATE TABLE ocsp_responses (
	id SERIAL NOT NULL, 
	ca_id INTEGER NOT NULL, 
	cert_serial VARCHAR(64) NOT NULL, 
	response_der BYTEA NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	this_update TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	next_update TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	revocation_time TIMESTAMP WITHOUT TIME ZONE, 
	revocation_reason INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(ca_id) REFERENCES certificate_authorities (id)
);

CREATE INDEX idx_ocsp_ca_serial ON ocsp_responses (ca_id, cert_serial);

CREATE INDEX idx_ocsp_next_update ON ocsp_responses (next_update);

CREATE INDEX ix_ocsp_responses_cert_serial ON ocsp_responses (cert_serial);

CREATE TABLE revoked_serials (
	id SERIAL NOT NULL, 
	caref VARCHAR(36) NOT NULL, 
	serial_number VARCHAR(100) NOT NULL, 
	revoked_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	revoke_reason VARCHAR(100), 
	invalidity_at TIMESTAMP WITHOUT TIME ZONE, 
	valid_to TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP, 
	certificate_id INTEGER, 
	public_key_sha256 VARCHAR(64), 
	PRIMARY KEY (id), 
	FOREIGN KEY(caref) REFERENCES certificate_authorities (refid)
);

CREATE INDEX ix_revoked_serials_caref ON revoked_serials (caref);

CREATE INDEX ix_revoked_serials_certificate_id ON revoked_serials (certificate_id);

CREATE INDEX ix_revoked_serials_public_key_sha256 ON revoked_serials (public_key_sha256);

CREATE INDEX ix_revoked_serials_serial_number ON revoked_serials (serial_number);

CREATE TABLE scep_profiles (
	id SERIAL NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	url_slug VARCHAR(64) NOT NULL, 
	description VARCHAR(255), 
	enabled BOOLEAN NOT NULL, 
	ca_refid VARCHAR(36) NOT NULL, 
	template_id INTEGER, 
	challenge_password TEXT, 
	challenge_generated_at TIMESTAMP WITHOUT TIME ZONE, 
	auto_approve BOOLEAN NOT NULL, 
	intune_enabled BOOLEAN NOT NULL, 
	intune_app_id INTEGER, 
	intune_tenant_id VARCHAR(255), 
	intune_client_id VARCHAR(255), 
	intune_client_secret TEXT, 
	intune_last_test_at TIMESTAMP WITHOUT TIME ZONE, 
	intune_last_test_result VARCHAR(255), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	created_by VARCHAR(80), 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_by VARCHAR(80), 
	PRIMARY KEY (id), 
	UNIQUE (name), 
	FOREIGN KEY(ca_refid) REFERENCES certificate_authorities (refid), 
	FOREIGN KEY(intune_app_id) REFERENCES intune_apps (id)
);

CREATE INDEX ix_scep_profiles_ca_refid ON scep_profiles (ca_refid);

CREATE UNIQUE INDEX ix_scep_profiles_url_slug ON scep_profiles (url_slug);

CREATE TABLE scep_requests (
	id SERIAL NOT NULL, 
	transaction_id VARCHAR(100) NOT NULL, 
	ca_refid VARCHAR(36), 
	csr TEXT NOT NULL, 
	status VARCHAR(20), 
	approved_by VARCHAR(80), 
	approved_at TIMESTAMP WITHOUT TIME ZONE, 
	rejection_reason VARCHAR(255), 
	cert_refid VARCHAR(36), 
	subject TEXT, 
	client_ip VARCHAR(45), 
	profile_id INTEGER, 
	renewal_of TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_scep_request_txn_ca UNIQUE (transaction_id, ca_refid), 
	FOREIGN KEY(ca_refid) REFERENCES certificate_authorities (refid)
);

CREATE INDEX ix_scep_requests_ca_refid ON scep_requests (ca_refid);

CREATE INDEX ix_scep_requests_transaction_id ON scep_requests (transaction_id);

CREATE TABLE acme_client_orders (
	id SERIAL NOT NULL, 
	domains TEXT NOT NULL, 
	challenge_type VARCHAR(20) NOT NULL, 
	environment VARCHAR(20) NOT NULL, 
	key_type VARCHAR(20), 
	key_source VARCHAR(20) NOT NULL, 
	csr_pem TEXT, 
	source_certificate_id INTEGER, 
	status VARCHAR(20) NOT NULL, 
	order_url VARCHAR(500), 
	account_url VARCHAR(500), 
	finalize_url VARCHAR(500), 
	certificate_url VARCHAR(500), 
	challenges_data TEXT, 
	dns_provider_id INTEGER, 
	acme_client_account_id INTEGER, 
	certificate_id INTEGER, 
	renewal_enabled BOOLEAN, 
	last_renewal_at TIMESTAMP WITHOUT TIME ZONE, 
	renewal_failures INTEGER, 
	error_message TEXT, 
	last_error_at TIMESTAMP WITHOUT TIME ZONE, 
	pending_key TEXT, 
	renewal_claimed_at TIMESTAMP WITHOUT TIME ZONE, 
	upstream_revocations TEXT, 
	renewal_of_order_id INTEGER, 
	is_proxy_order BOOLEAN, 
	dns_records_created TEXT, 
	client_jwk_thumbprint VARCHAR(64), 
	upstream_order_url TEXT, 
	upstream_authz_urls TEXT, 
	deactivated_authz_urls TEXT, 
	account_id VARCHAR(64), 
	expires_at TIMESTAMP WITHOUT TIME ZONE, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(source_certificate_id) REFERENCES certificates (id), 
	FOREIGN KEY(dns_provider_id) REFERENCES dns_providers (id), 
	FOREIGN KEY(acme_client_account_id) REFERENCES acme_client_accounts (id), 
	FOREIGN KEY(certificate_id) REFERENCES certificates (id), 
	FOREIGN KEY(renewal_of_order_id) REFERENCES acme_client_orders (id) ON DELETE SET NULL, 
	FOREIGN KEY(account_id) REFERENCES acme_accounts (account_id)
);

CREATE INDEX ix_acme_client_orders_account_id ON acme_client_orders (account_id);

CREATE INDEX ix_acme_client_orders_acme_client_account_id ON acme_client_orders (acme_client_account_id);

CREATE INDEX ix_acme_client_orders_renewal_of_order_id ON acme_client_orders (renewal_of_order_id);

CREATE TABLE acme_orders (
	id SERIAL NOT NULL, 
	order_id VARCHAR(64) NOT NULL, 
	account_id VARCHAR(64) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	identifiers TEXT NOT NULL, 
	not_before TIMESTAMP WITHOUT TIME ZONE, 
	not_after TIMESTAMP WITHOUT TIME ZONE, 
	replaces VARCHAR(255), 
	profile VARCHAR(64), 
	error TEXT, 
	csr TEXT, 
	certificate_id INTEGER, 
	certificate_url VARCHAR(512), 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	expires TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(account_id) REFERENCES acme_accounts (account_id), 
	FOREIGN KEY(certificate_id) REFERENCES certificates (id)
);

CREATE UNIQUE INDEX ix_acme_orders_order_id ON acme_orders (order_id);

CREATE INDEX ix_acme_orders_replaces ON acme_orders (replaces);

CREATE TABLE approval_requests (
	id SERIAL NOT NULL, 
	request_type VARCHAR(50) NOT NULL, 
	certificate_id INTEGER, 
	request_data TEXT, 
	policy_id INTEGER, 
	requester_id INTEGER, 
	requester_comment TEXT, 
	status VARCHAR(20), 
	approvals TEXT, 
	required_approvals INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	expires_at TIMESTAMP WITHOUT TIME ZONE, 
	resolved_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(certificate_id) REFERENCES certificates (id), 
	FOREIGN KEY(policy_id) REFERENCES certificate_policies (id), 
	FOREIGN KEY(requester_id) REFERENCES users (id)
);

CREATE INDEX ix_approval_requests_status_type ON approval_requests (status, request_type);

CREATE TABLE deploy_bindings (
	id SERIAL NOT NULL, 
	target_id INTEGER NOT NULL, 
	certificate_id INTEGER NOT NULL, 
	cert_path VARCHAR(512), 
	key_path VARCHAR(512), 
	fullchain_path VARCHAR(512), 
	include_root BOOLEAN NOT NULL, 
	chain_variant VARCHAR(40) DEFAULT 'auto' NOT NULL, 
	reload_command VARCHAR(512), 
	enabled BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	created_by VARCHAR(80), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_deploy_binding UNIQUE (target_id, certificate_id), 
	FOREIGN KEY(target_id) REFERENCES deploy_targets (id), 
	FOREIGN KEY(certificate_id) REFERENCES certificates (id)
);

CREATE INDEX ix_deploy_bindings_certificate_id ON deploy_bindings (certificate_id);

CREATE INDEX ix_deploy_bindings_target_id ON deploy_bindings (target_id);

CREATE TABLE discovered_certificates (
	id SERIAL NOT NULL, 
	scan_profile_id INTEGER, 
	target VARCHAR(1024) NOT NULL, 
	port INTEGER NOT NULL, 
	sni_hostname VARCHAR(1024) NOT NULL, 
	subject TEXT, 
	issuer TEXT, 
	serial_number VARCHAR(100), 
	not_before TIMESTAMP WITHOUT TIME ZONE, 
	not_after TIMESTAMP WITHOUT TIME ZONE, 
	fingerprint_sha256 VARCHAR(64), 
	pem_certificate TEXT, 
	status VARCHAR(32) NOT NULL, 
	ucm_certificate_id INTEGER, 
	first_seen TIMESTAMP WITHOUT TIME ZONE, 
	last_seen TIMESTAMP WITHOUT TIME ZONE, 
	last_changed_at TIMESTAMP WITHOUT TIME ZONE, 
	previous_fingerprint VARCHAR(64), 
	expiry_notified_fingerprint VARCHAR(64), 
	dns_hostname VARCHAR(1024), 
	san_dns_names TEXT NOT NULL, 
	san_ip_addresses TEXT NOT NULL, 
	san_emails TEXT NOT NULL, 
	san_uris TEXT NOT NULL, 
	scan_error TEXT, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_disc_cert_target_port_sni UNIQUE (target, port, sni_hostname), 
	FOREIGN KEY(scan_profile_id) REFERENCES discovery_scan_profiles (id) ON DELETE SET NULL, 
	FOREIGN KEY(ucm_certificate_id) REFERENCES certificates (id) ON DELETE SET NULL
);

CREATE INDEX ix_discovered_certificates_fingerprint_sha256 ON discovered_certificates (fingerprint_sha256);

CREATE TABLE est_signer_certs (
	id SERIAL NOT NULL, 
	ca_id INTEGER NOT NULL, 
	certificate_id INTEGER NOT NULL, 
	serial_number VARCHAR(100) NOT NULL, 
	issuer_fingerprint VARCHAR(64) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(ca_id) REFERENCES certificate_authorities (id) ON DELETE CASCADE, 
	FOREIGN KEY(certificate_id) REFERENCES certificates (id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX ix_est_signer_certs_ca_id ON est_signer_certs (ca_id);

CREATE TABLE msca_requests (
	id SERIAL NOT NULL, 
	msca_id INTEGER NOT NULL, 
	csr_id INTEGER, 
	cert_id INTEGER, 
	request_id INTEGER, 
	disposition_message TEXT, 
	template VARCHAR(200) NOT NULL, 
	status VARCHAR(20), 
	submitted_at TIMESTAMP WITHOUT TIME ZONE, 
	issued_at TIMESTAMP WITHOUT TIME ZONE, 
	error_message TEXT, 
	cert_pem TEXT, 
	submitted_by VARCHAR(80), 
	enrollee_name VARCHAR(500), 
	enrollee_upn VARCHAR(500), 
	PRIMARY KEY (id), 
	FOREIGN KEY(msca_id) REFERENCES microsoft_cas (id), 
	FOREIGN KEY(csr_id) REFERENCES certificates (id), 
	FOREIGN KEY(cert_id) REFERENCES certificates (id)
);

CREATE TABLE acme_authorizations (
	id SERIAL NOT NULL, 
	authorization_id VARCHAR(64) NOT NULL, 
	order_id VARCHAR(64), 
	account_id VARCHAR(64), 
	identifier TEXT NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	expires TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	wildcard BOOLEAN, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(order_id) REFERENCES acme_orders (order_id), 
	FOREIGN KEY(account_id) REFERENCES acme_accounts (account_id)
);

CREATE UNIQUE INDEX ix_acme_authorizations_authorization_id ON acme_authorizations (authorization_id);

CREATE TABLE acme_proxy_dns_challenges (
	id SERIAL NOT NULL, 
	order_id INTEGER NOT NULL, 
	acme_client_account_id INTEGER, 
	account_id VARCHAR(64), 
	client_jwk_thumbprint VARCHAR(128) NOT NULL, 
	identifier VARCHAR(255) NOT NULL, 
	record_name VARCHAR(255) NOT NULL, 
	txt_value VARCHAR(64) NOT NULL, 
	zone_name VARCHAR(255) NOT NULL, 
	upstream_challenge_url TEXT, 
	status VARCHAR(16) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	client_confirmed_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_acme_proxy_dns_challenge UNIQUE (order_id, record_name, txt_value), 
	FOREIGN KEY(order_id) REFERENCES acme_client_orders (id) ON DELETE CASCADE
);

CREATE INDEX idx_acme_proxy_dns_expires ON acme_proxy_dns_challenges (expires_at);

CREATE INDEX idx_acme_proxy_dns_status_expires ON acme_proxy_dns_challenges (status, expires_at);

CREATE INDEX ix_acme_proxy_dns_challenges_acme_client_account_id ON acme_proxy_dns_challenges (acme_client_account_id);

CREATE INDEX ix_acme_proxy_dns_challenges_order_id ON acme_proxy_dns_challenges (order_id);

CREATE INDEX ix_acme_proxy_dns_challenges_record_name ON acme_proxy_dns_challenges (record_name);

CREATE INDEX ix_acme_proxy_dns_challenges_zone_name ON acme_proxy_dns_challenges (zone_name);

CREATE TABLE acme_challenges (
	id SERIAL NOT NULL, 
	challenge_id VARCHAR(64) NOT NULL, 
	authorization_id VARCHAR(64) NOT NULL, 
	type VARCHAR(20) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	token VARCHAR(64) NOT NULL, 
	url VARCHAR(512), 
	validated TIMESTAMP WITHOUT TIME ZONE, 
	error TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(authorization_id) REFERENCES acme_authorizations (authorization_id)
);

CREATE UNIQUE INDEX ix_acme_challenges_challenge_id ON acme_challenges (challenge_id);

CREATE TABLE IF NOT EXISTS _migrations ( id SERIAL PRIMARY KEY, name VARCHAR(255) NOT NULL UNIQUE, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP );
INSERT INTO _migrations (name) VALUES ('000_baseline_v252');
INSERT INTO _migrations (name) VALUES ('001_fix_dn_format');
INSERT INTO _migrations (name) VALUES ('002_add_sso_ssl_fields');
INSERT INTO _migrations (name) VALUES ('003_add_microsoft_ca_tables');
INSERT INTO _migrations (name) VALUES ('004_add_delta_crl');
INSERT INTO _migrations (name) VALUES ('005_add_approval_request_data');
INSERT INTO _migrations (name) VALUES ('006_fix_overbroad_approval_policies');
INSERT INTO _migrations (name) VALUES ('007_cdp_urls_use_refid');
INSERT INTO _migrations (name) VALUES ('008_cdp_ocsp_urls_use_http');
INSERT INTO _migrations (name) VALUES ('009_add_discovery_san_email_uri');
INSERT INTO _migrations (name) VALUES ('010_acme_client_key_type');
INSERT INTO _migrations (name) VALUES ('011_msca_enroll_on_behalf');
INSERT INTO _migrations (name) VALUES ('012_aia_ca_issuers');
INSERT INTO _migrations (name) VALUES ('013_fix_protocol_urls_https');
INSERT INTO _migrations (name) VALUES ('014_multi_url_and_cps');
INSERT INTO _migrations (name) VALUES ('015_add_rfc5280_constraints');
INSERT INTO _migrations (name) VALUES ('016_acme_pre_authorization');
INSERT INTO _migrations (name) VALUES ('017_remove_ca_template');
INSERT INTO _migrations (name) VALUES ('018_add_ssh_certificates');
INSERT INTO _migrations (name) VALUES ('019_acme_auto_approve_safe_default');
INSERT INTO _migrations (name) VALUES ('020_fix_acme_client_order_expires_at');
INSERT INTO _migrations (name) VALUES ('021_acme_client_order_account_link');
INSERT INTO _migrations (name) VALUES ('022_add_user_preferences');
INSERT INTO _migrations (name) VALUES ('023_sso_sync_role_on_login');
INSERT INTO _migrations (name) VALUES ('024_user_auth_source');
INSERT INTO _migrations (name) VALUES ('025_smtp_oauth2');
INSERT INTO _migrations (name) VALUES ('026_add_api_key_prefix');
INSERT INTO _migrations (name) VALUES ('027_acme_eab_credentials');
INSERT INTO _migrations (name) VALUES ('027_backfill_san_email');
INSERT INTO _migrations (name) VALUES ('028_scep_request_ca_scope');
INSERT INTO _migrations (name) VALUES ('029_encrypt_acme_account_keys');
INSERT INTO _migrations (name) VALUES ('030_add_certificate_san_upn');
INSERT INTO _migrations (name) VALUES ('031_acme_client_accounts');
INSERT INTO _migrations (name) VALUES ('032_ca_hsm_key_unique');
INSERT INTO _migrations (name) VALUES ('033_acme_authz_order_id_nullable');
INSERT INTO _migrations (name) VALUES ('034_add_ca_offline');
INSERT INTO _migrations (name) VALUES ('035_reconcile_pg_schema');
INSERT INTO _migrations (name) VALUES ('036_add_webhook_auth');
INSERT INTO _migrations (name) VALUES ('037_ca_template_pins');
INSERT INTO _migrations (name) VALUES ('038_eab_notes');
INSERT INTO _migrations (name) VALUES ('039_acme_terms_defaults');
INSERT INTO _migrations (name) VALUES ('040_ldap_required_groups');
INSERT INTO _migrations (name) VALUES ('041_webhook_deliveries');
INSERT INTO _migrations (name) VALUES ('042_key_recovery_requests');
INSERT INTO _migrations (name) VALUES ('043_users_email_not_unique');
INSERT INTO _migrations (name) VALUES ('044_users_email_unique_again');
INSERT INTO _migrations (name) VALUES ('045_sso_stable_identity');
INSERT INTO _migrations (name) VALUES ('046_2fa_enforcement');
INSERT INTO _migrations (name) VALUES ('047_acme_client_order_ca_account_link');
INSERT INTO _migrations (name) VALUES ('048_acme_ca_account_timing');
INSERT INTO _migrations (name) VALUES ('049_acme_key_source_preflight');
INSERT INTO _migrations (name) VALUES ('050_acme_proxy_ca_account_link');
INSERT INTO _migrations (name) VALUES ('051_acme_proxy_slug');
INSERT INTO _migrations (name) VALUES ('052_encrypt_dns_provider_credentials');
INSERT INTO _migrations (name) VALUES ('053_msca_crl_sync');
INSERT INTO _migrations (name) VALUES ('054_msca_admin_channel');
INSERT INTO _migrations (name) VALUES ('055_msca_inventory');
INSERT INTO _migrations (name) VALUES ('056_acme_preferred_chain');
INSERT INTO _migrations (name) VALUES ('057_pkcs11_config_keys');
INSERT INTO _migrations (name) VALUES ('058_certificate_invalidity_at');
INSERT INTO _migrations (name) VALUES ('059_ca_crl_schedule');
INSERT INTO _migrations (name) VALUES ('060_ca_url_slug');
INSERT INTO _migrations (name) VALUES ('061_encrypt_acme_client_eab_keys');
INSERT INTO _migrations (name) VALUES ('062_oidc_id_token_verification');
INSERT INTO _migrations (name) VALUES ('063_acme_order_replaces');
INSERT INTO _migrations (name) VALUES ('064_acme_order_profile');
INSERT INTO _migrations (name) VALUES ('065_reset_webauthn_sign_counts');
INSERT INTO _migrations (name) VALUES ('066_preserve_prev_2200_behaviors');
INSERT INTO _migrations (name) VALUES ('067_normalize_wildcard_authz');
INSERT INTO _migrations (name) VALUES ('068_scep_profiles');
INSERT INTO _migrations (name) VALUES ('069_eab_allowed_domains');
INSERT INTO _migrations (name) VALUES ('070_template_overrides');
INSERT INTO _migrations (name) VALUES ('071_certificate_template_autoenroll');
INSERT INTO _migrations (name) VALUES ('072_ad_connector');
INSERT INTO _migrations (name) VALUES ('073_certificate_template_ad_derived_subject');
INSERT INTO _migrations (name) VALUES ('074_certificate_template_enroll_acl');
INSERT INTO _migrations (name) VALUES ('075_certificate_template_pinned_subject_fields');
INSERT INTO _migrations (name) VALUES ('076_scep_profile_intune');
INSERT INTO _migrations (name) VALUES ('077_acme_client_account_dup_directory');
INSERT INTO _migrations (name) VALUES ('078_revoked_serials');
INSERT INTO _migrations (name) VALUES ('079_ca_external_csr');
INSERT INTO _migrations (name) VALUES ('080_crl_metadata_is_external');
INSERT INTO _migrations (name) VALUES ('081_deploy_hooks');
INSERT INTO _migrations (name) VALUES ('082_expiry_alert_thresholds');
INSERT INTO _migrations (name) VALUES ('083_ca_revocation');
INSERT INTO _migrations (name) VALUES ('084_approval_requests_index');
INSERT INTO _migrations (name) VALUES ('085_scep_request_profile');
INSERT INTO _migrations (name) VALUES ('086_scep_request_renewal_of');
INSERT INTO _migrations (name) VALUES ('087_webhooks_from_settings');
INSERT INTO _migrations (name) VALUES ('088_default_policies_off');
INSERT INTO _migrations (name) VALUES ('089_deploy_binding_include_root');
INSERT INTO _migrations (name) VALUES ('090_crl_deploy');
INSERT INTO _migrations (name) VALUES ('091_binding_reload_commands');
INSERT INTO _migrations (name) VALUES ('092_intune_apps');
INSERT INTO _migrations (name) VALUES ('093_ad_connector_health');
INSERT INTO _migrations (name) VALUES ('094_expiry_alerts_exclude_acme');
INSERT INTO _migrations (name) VALUES ('095_certificate_key_algo_backfill');
INSERT INTO _migrations (name) VALUES ('096_template_key_type_canonical');
INSERT INTO _migrations (name) VALUES ('098_audit_chain_keyed');
INSERT INTO _migrations (name) VALUES ('099_policy_operations');
INSERT INTO _migrations (name) VALUES ('100_user_webauthn_second_factor');
INSERT INTO _migrations (name) VALUES ('101_acme_eab_keys_import');
INSERT INTO _migrations (name) VALUES ('102_dead_settings');
INSERT INTO _migrations (name) VALUES ('103_saml_strict');
INSERT INTO _migrations (name) VALUES ('104_group_permissions_lists');
INSERT INTO _migrations (name) VALUES ('105_legacy_ldap_settings');
INSERT INTO _migrations (name) VALUES ('106_ca_signature_scheme');
INSERT INTO _migrations (name) VALUES ('107_ca_compliance_profile');
INSERT INTO _migrations (name) VALUES ('108_hsm_provider_certification');
INSERT INTO _migrations (name) VALUES ('109_user_custom_role_source');
INSERT INTO _migrations (name) VALUES ('110_ssh_ca_allow_any_principal');
INSERT INTO _migrations (name) VALUES ('111_acme_dns_update');
INSERT INTO _migrations (name) VALUES ('112_acme_proxy_authz_deactivation');
INSERT INTO _migrations (name) VALUES ('113_hsm_module_info');
INSERT INTO _migrations (name) VALUES ('114_ca_cross_certificates');
INSERT INTO _migrations (name) VALUES ('115_related_certificates');
INSERT INTO _migrations (name) VALUES ('116_ssh_ca_permissions');
INSERT INTO _migrations (name) VALUES ('117_related_cert_requests');
INSERT INTO _migrations (name) VALUES ('118_ca_issuance_hidden');
INSERT INTO _migrations (name) VALUES ('119_ssh_ca_allow_custom_key_id');
INSERT INTO _migrations (name) VALUES ('120_certificates_lookup_indexes');
INSERT INTO _migrations (name) VALUES ('121_acme_renewal_order_duplicates');
INSERT INTO _migrations (name) VALUES ('122_strip_port_zero_protocol_urls');
INSERT INTO _migrations (name) VALUES ('123_acme_client_order_pending_key_lease');
INSERT INTO _migrations (name) VALUES ('124_unique_provider_account_webhook_names');
INSERT INTO _migrations (name) VALUES ('127_certificate_template_custom_extensions');
INSERT INTO _migrations (name) VALUES ('128_revoked_key_digest_upstream_revocations');
INSERT INTO _migrations (name) VALUES ('129_compromised_keys');
INSERT INTO _migrations (name) VALUES ('130_auth_certificate_serial_per_issuer');
INSERT INTO _migrations (name) VALUES ('131_deploy_target_http');
INSERT INTO _migrations (name) VALUES ('132_est_signer_certs');
INSERT INTO _migrations (name) VALUES ('133_audit_log_text_fields');
INSERT INTO _migrations (name) VALUES ('134_crl_number_unique_and_counters');
INSERT INTO _migrations (name) VALUES ('135_user_totp_step_session_version');
INSERT INTO _migrations (name) VALUES ('136_lifted_hold_leftovers');
INSERT INTO _migrations (name) VALUES ('137_ldap_start_tls');
