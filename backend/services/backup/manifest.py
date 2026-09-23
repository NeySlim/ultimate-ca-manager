"""What a backup carries, declared once.

The rule this file exists to enforce is that **a column is exported unless
someone wrote down why it is not**. The export used to be twenty-seven
hand-written dictionaries, so a column added to a model was simply absent
from every archive written afterwards, and nothing said so until a restore
came up short: private keys without their HSM link, users without their MFA
secret, SMTP without its OAuth2 credentials.

Each section below names the model it comes from, the fields that identify a
row across two installations (never the primary key, which means nothing on
the target), the columns deliberately left out with the reason, and the
columns holding secrets that must be decrypted at export time so the archive
is readable on an installation with a different database key.

`tests/test_backup_manifest.py` compares this file to the models themselves:
a new table or a new column fails the suite until it is either exported or
excluded here, on purpose and in writing.
"""
from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass(frozen=True)
class Section:
    """One section of the archive."""

    model: str                      # "module:ClassName"
    identity: Tuple[str, ...]       # columns identifying a row across installs
    exclude: Dict[str, str] = field(default_factory=dict)   # column -> reason
    secrets: Tuple[str, ...] = ()   # columns decrypted at export
    references: Dict[str, str] = field(default_factory=dict)
    """Columns carrying the number another section's row happens to have on
    this installation, mapped to that section: the export writes the identity
    of the row beside the number, and the restore resolves that identity
    against the target, whose numbering is its own.

    A column that already says the same thing on every installation is not a
    reference and must not be declared as one. Two were: the `used_by_account_id`
    of an EAB credential and the `account_id` of an ACME client order both hold
    the ACME account id, the string the protocol itself uses, while the section
    they named is indexed by primary key. Nothing ever matched, so no identity
    was written beside them; the restore found none, and cleared a link that
    would have survived untouched had nothing been declared at all."""
    stored: Dict[str, str] = field(default_factory=dict)
    """How a secret that is a plain column is kept in that column, for the
    secrets whose name is not a property of the model.

    `secrets` says a column must leave the installation in the clear, so the
    archive is readable on a server with another key. It did not say what to
    do on the way back, and the restore assigned the archive's cleartext
    straight to the column: an ACME account key, a deployment SSH key, a SCEP
    challenge, an Intune client secret and a webhook signing secret landed in
    the database readable, on an installation that had them encrypted before
    the restore. Where the name is a property the setter re-encrypts and
    there is nothing to declare; where it is a plain column, the layer the
    application writes it with is named here:

    * `master` for `security.encryption.encrypt_text`, the key-encryption key;
    * `database` for `utils.encryption.encrypt_if_needed`, the database key.

    A plain column absent from this mapping is one the application reads
    directly, in the clear: the MFA secret `pyotp` is handed, the Argon2
    hashes of the backup codes, the JSON configuration of an HSM provider.
    Encrypting those would hand the application a ciphertext it never
    decrypts. `tests/test_backup_manifest.py` refuses a secret that is
    neither a property, nor named here, nor named there as read in the
    clear."""
    optional: bool = False          # historical, exported only when asked
    custom: bool = False            # a dedicated exporter adds to this section
    handled: Dict[str, str] = field(default_factory=dict)
    """Columns the dedicated exporter writes under another name, e.g. the
    DER blob `crt` written as the PEM `certificate_pem`. Decided about, like
    an exclusion, but carried rather than dropped."""


# Columns every table has and no archive needs to carry as such.
_SURROGATE = {'id': 'primary key, meaningless on another installation'}

SECTIONS: Dict[str, Section] = {
    'users': Section(
        model='models:User',
        identity=('username',),
        exclude={
            **_SURROGATE,
            'failed_logins': 'live lockout counter, not part of the account',
            'locked_until': 'live lockout state',
            'login_count': 'usage statistic',
            'last_login': 'usage statistic',
            'password_reset_token': 'short-lived, and a restore must not carry a usable reset',
            'password_reset_expires': 'goes with the reset token',
        },
        secrets=('totp_secret', 'backup_codes'),
        references={'custom_role_id': 'custom_roles', 'sso_provider_id': 'sso_providers'},
    ),
    'certificate_authorities': Section(
        model='models:CA',
        identity=('refid',),
        exclude={**_SURROGATE},
        references={'hsm_key_id': 'hsm_keys', 'owner_group_id': 'groups'},
        custom=True,
        handled={'crt': 'certificate_pem', 'prv': 'private_key_pem_encrypted',
                 'csr': 'csr_pem'},
    ),
    'certificates': Section(
        model='models:Certificate',
        identity=('refid',),
        exclude={**_SURROGATE},
        references={'template_id': 'certificate_templates', 'owner_group_id': 'groups'},
        custom=True,
        handled={'crt': 'certificate_pem', 'prv': 'private_key_pem_encrypted',
                 'csr': 'csr_pem'},
    ),
    'revoked_serials': Section(
        model='models.revoked_serial:RevokedSerial',
        identity=('caref', 'serial_number'),
        exclude={**_SURROGATE, 'created_at': 'bookkeeping, revoked_at is the fact'},
        references={'certificate_id': 'certificates'},
        custom=True,
    ),
    'groups': Section(
        model='models.group:Group',
        identity=('name',),
        exclude={**_SURROGATE},
    ),
    'custom_roles': Section(
        model='models.rbac:CustomRole',
        identity=('name',),
        exclude={**_SURROGATE},
        # A role built on another one. The number is the source's, so the
        # restored role inherited from whichever role happened to hold it.
        references={'inherits_from': 'custom_roles'},
    ),
    'role_permissions': Section(
        model='models.rbac:RolePermission',
        identity=('role_id', 'permission'),
        exclude={**_SURROGATE},
        references={'role_id': 'custom_roles'},
    ),
    'certificate_templates': Section(
        model='models.certificate_template:CertificateTemplate',
        identity=('name',),
        exclude={**_SURROGATE},
    ),
    'ca_template_pins': Section(
        model='models.ca_template_pin:CATemplatePin',
        identity=('ca_id', 'template_id'),
        exclude={**_SURROGATE},
        references={'ca_id': 'certificate_authorities', 'template_id': 'certificate_templates'},
    ),
    'trusted_certificates': Section(
        model='models.truststore:TrustedCertificate',
        identity=('fingerprint_sha256',),
        exclude={**_SURROGATE},
    ),
    'sso_providers': Section(
        model='models.sso:SSOProvider',
        identity=('name',),
        exclude={**_SURROGATE, 'last_used_at': 'usage statistic'},
        secrets=('oauth2_client_secret', 'ldap_bind_password'),
    ),
    'hsm_providers': Section(
        model='models.hsm:HsmProvider',
        identity=('name',),
        exclude={
            **_SURROGATE,
            'status': 'live connection state, retested on the target',
            'last_tested_at': 'live connection state',
            'error_message': 'live connection state',
        },
        secrets=('config',),
        references={'created_by': 'users'},
    ),
    'hsm_keys': Section(
        model='models.hsm:HsmKey',
        identity=('provider_id', 'key_identifier'),
        exclude={**_SURROGATE},
        references={'provider_id': 'hsm_providers'},
    ),
    'api_keys': Section(
        model='models.api_key:APIKey',
        # The hash, not the prefix: the prefix is nullable and rows predating
        # it carry none, so it cannot identify a key on another installation.
        identity=('key_hash',),
        exclude={**_SURROGATE, 'last_used_at': 'usage statistic'},
        references={'user_id': 'users'},
    ),
    'auth_certificates': Section(
        model='models.auth_certificate:AuthCertificate',
        identity=('cert_fingerprint',),
        exclude={**_SURROGATE, 'last_used_at': 'usage statistic'},
        references={'user_id': 'users'},
    ),
    'smtp_config': Section(
        model='models.email_notification:SMTPConfig',
        identity=('id',),
        exclude={},
        secrets=('smtp_password', 'smtp_oauth_client_secret', 'smtp_oauth_refresh_token'),
    ),
    'notification_config': Section(
        model='models.email_notification:NotificationConfig',
        # One row per kind of notification, seven of them on any
        # installation, told apart by a `type` the table declares unique.
        # Identified by the primary key it read as a section holding a single
        # row, which it is not: a restore through the generic path would have
        # applied all seven onto the same one, and the six others would have
        # kept whatever the target held.
        identity=('type',),
        exclude={**_SURROGATE},
    ),
    'certificate_policies': Section(
        model='models.policy:CertificatePolicy',
        identity=('name',),
        exclude={**_SURROGATE},
        references={'ca_id': 'certificate_authorities',
                    'template_id': 'certificate_templates',
                    'approval_group_id': 'groups'},
    ),
    'approval_requests': Section(
        model='models.policy:ApprovalRequest',
        identity=('certificate_id', 'created_at'),
        exclude={**_SURROGATE},
        references={'certificate_id': 'certificates', 'policy_id': 'certificate_policies',
                    'requester_id': 'users'},
        optional=True,
    ),
    'dns_providers': Section(
        model='models.acme_models:DnsProvider',
        identity=('name',),
        exclude={**_SURROGATE},
        secrets=('credentials',),
    ),
    'acme_accounts': Section(
        model='models.acme_models:AcmeAccount',
        identity=('account_id',),
        exclude={**_SURROGATE},
    ),
    'acme_eab_credentials': Section(
        model='models.acme_models:AcmeEabCredential',
        identity=('kid',),
        exclude={**_SURROGATE},
        secrets=('hmac_key_b64',),
        # `used_by_account_id` holds the ACME account id itself, as text, and
        # is deliberately not a reference: see the note above `references`.
        references={'created_by_user_id': 'users', 'revoked_by_user_id': 'users'},
    ),
    'acme_domains': Section(
        model='models.acme_models:AcmeDomain',
        identity=('domain',),
        exclude={**_SURROGATE},
        references={'dns_provider_id': 'dns_providers', 'issuing_ca_id': 'certificate_authorities'},
    ),
    'acme_local_domains': Section(
        model='models.acme_models:AcmeLocalDomain',
        identity=('domain',),
        exclude={**_SURROGATE},
        # The authority that signs for this zone, and a column that cannot be
        # empty. Written with the source's number it named another authority
        # here, so the zone was signed by whoever held that number, and
        # PostgreSQL refused the row outright.
        references={'issuing_ca_id': 'certificate_authorities'},
    ),
    'acme_client_accounts': Section(
        model='models.acme_client_account:AcmeClientAccount',
        # The label is part of the identity because the pair
        # (directory_url, email) is not one: migration 077 dropped the
        # uniqueness of `directory_url` on purpose (#276), so an
        # administrator may hold several accounts at the same authority,
        # under the same shared mailbox, told apart only by what they called
        # them. Identified by the pair alone, the two collapsed into one
        # index entry: the second archived account overwrote the first, and
        # an order restored beside them was attached to whichever of the two
        # the index had kept.
        identity=('directory_url', 'email', 'label'),
        exclude={**_SURROGATE},
        secrets=('account_key', 'eab_hmac_key'),
        stored={'account_key': 'master'},
    ),
    'acme_client_orders': Section(
        model='models.acme_models:AcmeClientOrder',
        identity=('order_url',),
        exclude={**_SURROGATE},
        # `account_id` names the local ACME account by its account id, the
        # string the protocol itself uses, and is deliberately not a
        # reference: see the note above `references`.
        #
        # `acme_client_account_id` is a number, and names the account at the
        # external CA the order was placed with. Exported as it stood, the
        # source's number landed here on whichever account happened to hold
        # it: a renewal placed against a different CA, or against nothing.
        references={'dns_provider_id': 'dns_providers',
                    'acme_client_account_id': 'acme_client_accounts',
                    'certificate_id': 'certificates',
                    'source_certificate_id': 'certificates'},
        optional=True,
    ),
    'ssh_cas': Section(
        model='models.ssh:SSHCertificateAuthority',
        identity=('refid',),
        exclude={**_SURROGATE},
        references={'owner_group_id': 'groups'},
        custom=True,
        handled={'private_key': 'private_key_pem_encrypted'},
    ),
    'ssh_certificates': Section(
        model='models.ssh:SSHCertificate',
        identity=('serial', 'ssh_ca_id'),
        exclude={**_SURROGATE},
        references={'ssh_ca_id': 'ssh_cas',
                    'owner_group_id': 'groups'},
    ),
    'microsoft_cas': Section(
        model='models.msca:MicrosoftCA',
        identity=('name',),
        exclude={
            **_SURROGATE,
            'last_test_at': 'live connection state',
            'last_test_result': 'live connection state',
            'last_crl_sync_at': 'live sync state',
            'last_crl_sync_result': 'live sync state',
            'last_inventory_sync_at': 'live sync state',
            'last_inventory_sync_result': 'live sync state',
            'last_synced_request_id': 'live sync state',
        },
        # `client_key_pem` is the private key of the certificate UCM presents
        # to the authority: a mTLS connection's own key, kept encrypted at
        # rest like the two passwords beside it. Left undeclared, the archive
        # carried the ciphertext the source stored and the target came back
        # with a key it cannot open, so the connection it was there to make
        # could never be made again.
        secrets=('password', 'winrm_password', 'client_key_pem'),
    ),
    'msca_requests': Section(
        model='models.msca:MSCARequest',
        identity=('msca_id', 'request_id'),
        exclude={**_SURROGATE},
        references={'msca_id': 'microsoft_cas',
                    'cert_id': 'certificates',
                    'csr_id': 'certificates'},
        optional=True,
    ),
    'intune_apps': Section(
        model='models.scep:IntuneApp',
        identity=('name',),
        exclude={
            **_SURROGATE,
            'last_test_at': 'live connection state',
            'last_test_result': 'live connection state',
        },
        secrets=('client_secret',),
        stored={'client_secret': 'database'},
    ),
    'scep_profiles': Section(
        model='models.scep:ScepProfile',
        identity=('name',),
        exclude={
            **_SURROGATE,
            'intune_tenant_id': 'frozen by 092, the app registration lives in intune_apps',
            'intune_client_id': 'frozen by 092, the app registration lives in intune_apps',
            'intune_client_secret': 'frozen by 092, the app registration lives in intune_apps',
            'intune_last_test_at': 'frozen by 092, live connection state of the app',
            'intune_last_test_result': 'frozen by 092, live connection state of the app',
        },
        secrets=('challenge_password',),
        stored={'challenge_password': 'master'},
        references={'template_id': 'certificate_templates',
                    'intune_app_id': 'intune_apps'},
    ),
    'ad_connector': Section(
        model='models.ad_connector:ADConnectorConfig',
        identity=('id',),
        exclude={
            'last_test_at': 'live connection state',
            'last_test_result': 'live connection state',
            'health': 'live connection state: this installation\'s view of '
                      'which domain controllers answered, meaningless on another',
        },
        secrets=('bind_password',),
    ),
    'webhook_endpoints': Section(
        model='services.webhook_service:WebhookEndpoint',
        identity=('name',),
        exclude={
            **_SURROGATE,
            'last_success': 'delivery statistic',
            'last_failure': 'delivery statistic',
            'failure_count': 'delivery statistic',
        },
        secrets=('secret', 'auth_token'),
        stored={'secret': 'database'},
    ),
    'deploy_targets': Section(
        model='models.deploy:DeployTarget',
        identity=('name',),
        exclude={
            **_SURROGATE,
            'last_success_at': 'delivery statistic',
            'last_failure_at': 'delivery statistic',
            'failure_count': 'delivery statistic',
        },
        secrets=('private_key',),
        stored={'private_key': 'master'},
    ),
    'deploy_bindings': Section(
        model='models.deploy:DeployBinding',
        identity=('target_id', 'certificate_id'),
        exclude={**_SURROGATE},
        references={'target_id': 'deploy_targets', 'certificate_id': 'certificates'},
    ),
    'crl_deploy_bindings': Section(
        model='models.deploy:CRLDeployBinding',
        identity=('target_id', 'ca_id'),
        exclude={**_SURROGATE},
        references={
            'target_id': 'deploy_targets',
            'ca_id': 'certificate_authorities',
        },
    ),
    'scan_profiles': Section(
        model='models.discovered_certificate:ScanProfile',
        identity=('name',),
        exclude={**_SURROGATE},
    ),
    'scan_runs': Section(
        model='models.discovered_certificate:ScanRun',
        identity=('scan_profile_id', 'started_at'),
        exclude={**_SURROGATE},
        references={'scan_profile_id': 'scan_profiles'},
        optional=True,
    ),
    'discovered_certificates': Section(
        model='models.discovered_certificate:DiscoveredCertificate',
        identity=('fingerprint_sha256', 'target', 'port'),
        exclude={**_SURROGATE},
        references={'scan_profile_id': 'scan_profiles',
                    'ucm_certificate_id': 'certificates'},
        optional=True,
    ),
    'scep_requests': Section(
        model='models.scep:SCEPRequest',
        identity=('transaction_id',),
        exclude={**_SURROGATE},
        optional=True,
    ),
    'key_recovery_requests': Section(
        model='models.key_recovery:KeyRecoveryRequest',
        identity=('cert_refid', 'requested_at'),
        exclude={**_SURROGATE},
        references={'cert_id': 'certificates'},
        optional=True,
    ),
    'audit_logs': Section(
        model='models.audit_log:AuditLog',
        identity=('entry_hash',),
        exclude={**_SURROGATE},
        optional=True,
    ),
    'configuration': Section(
        model='models:SystemConfig',
        identity=('key',),
        exclude={**_SURROGATE},
        custom=True,
    ),
    'group_members': Section(
        model='models.group:GroupMember',
        identity=('group_id', 'user_id'),
        exclude={**_SURROGATE},
        references={'group_id': 'groups', 'user_id': 'users'},
    ),
    'webauthn_credentials': Section(
        model='models.webauthn:WebAuthnCredential',
        identity=('credential_id',),
        exclude={**_SURROGATE, 'last_used_at': 'usage statistic'},
        references={'user_id': 'users'},
    ),
}


# Tables no archive carries, each with the reason it is not a loss.
EXCLUDED_TABLES: Dict[str, str] = {
    'acme_nonces': 'single-use protocol nonces, valid for minutes',
    'acme_orders': 'in-flight protocol state; a client retries against the restored server',
    'acme_authorizations': 'in-flight protocol state, tied to orders',
    'acme_challenges': 'in-flight protocol state, tied to authorizations',
    'crls': 'regenerated from the CAs and their revocation records',
    'crl_metadata': 'regenerated with the CRLs',
    'ocsp_responses': 'a response cache, rebuilt on demand',
    'notification_log': 'delivery history, not configuration',
    'webhook_deliveries': 'delivery queue and history; endpoints are exported',
    'deploy_deliveries': 'delivery queue and history; targets and bindings are exported',
    'user_sessions': 'live sessions, deliberately not carried into a restore',
    'pro_sso_sessions': 'live SSO sessions',
    'webauthn_challenges': 'single-use registration and login challenges',
    'schema_migrations': 'migration bookkeeping of the target, never of the source',
    'alembic_version': 'migration bookkeeping of the target',
}
