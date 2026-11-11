"""Deploy hooks models (#299).

Push issued/renewed certificates and CRLs to remote hosts over SFTP, or a
certificate to an HTTP API (discussion #428). Each SSH binding may run its own
fixed reload command after a successful push. Admin-only feature: UCM holds
credentials that can act on the fleet, so everything is encrypted at rest and
audited.
"""
import json

from models import db
from utils.datetime_utils import utc_now, utc_isoformat


class DeployTarget(db.Model):
    """A remote host certificates can be pushed to.

    ``kind`` is ``ssh`` (SFTP push, optional reload over SSH) or ``http`` (one
    request to an API, body built from a template). An HTTP target keeps the
    SSH-only columns at their empty values: ``host`` and ``port`` mirror its
    URL for the listing, ``username`` and ``private_key`` are ``''``.
    """
    __tablename__ = 'deploy_targets'

    KIND_SSH = 'ssh'
    KIND_HTTP = 'http'
    KINDS = (KIND_SSH, KIND_HTTP)
    HTTP_METHODS = ('POST', 'PUT', 'PATCH')

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    kind = db.Column(db.String(8), nullable=False, default=KIND_SSH, server_default=KIND_SSH)
    host = db.Column(db.String(255), nullable=False)
    port = db.Column(db.Integer, nullable=False, default=22)
    username = db.Column(db.String(120), nullable=False)
    # SSH private key (PEM/OpenSSH), encrypted at rest like every other secret
    private_key = db.Column(db.Text, nullable=False)
    # HTTP target: the request. Headers carry API tokens, so they are stored
    # encrypted as a JSON object and never returned by the API (names only).
    url = db.Column(db.String(2048))
    http_method = db.Column(db.String(8))
    http_headers = db.Column(db.Text)
    body_template = db.Column(db.Text)
    # Extra trust anchor(s) for the target's TLS certificate, PEM. Verification
    # is never switched off: a self-signed appliance certificate goes here.
    tls_ca_pem = db.Column(db.Text)
    # The body template may name key_pem only when this is set, and then the
    # URL must be https.
    allow_private_key = db.Column(db.Boolean, nullable=False, default=False, server_default='0')
    # Matching OpenSSH public key — shown to the admin to install on the target
    public_key = db.Column(db.Text)
    # Pinned host key, '<type> <base64>', recorded on first connect (TOFU)
    host_key = db.Column(db.Text)
    # Legacy storage retained for downgrade compatibility. Migration 091 copies
    # this value to each binding; new code neither exposes nor executes it.
    reload_command = db.Column(db.String(512))
    enabled = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(db.DateTime, default=utc_now)
    created_by = db.Column(db.String(80))
    last_success_at = db.Column(db.DateTime)
    last_failure_at = db.Column(db.DateTime)
    failure_count = db.Column(db.Integer, nullable=False, default=0)

    def host_key_fingerprint(self):
        """SHA256 fingerprint of the pinned host key (OpenSSH style)."""
        if not self.host_key:
            return None
        try:
            import base64
            import hashlib
            key_b64 = self.host_key.split()[1]
            digest = hashlib.sha256(base64.b64decode(key_b64)).digest()
            return 'SHA256:' + base64.b64encode(digest).decode().rstrip('=')
        except Exception:
            return None

    @property
    def is_http(self):
        return self.kind == self.KIND_HTTP

    def http_header_names(self):
        """Names of the stored request headers; their values never leave."""
        from services.deploy.http import load_headers
        return sorted(load_headers(self.http_headers).keys())

    def to_dict(self):
        # private_key and header values are never exposed through the API
        data = {
            'id': self.id,
            'name': self.name,
            'kind': self.kind or self.KIND_SSH,
            'host': self.host,
            'port': self.port,
            'username': self.username,
            'enabled': self.enabled,
            'created_at': utc_isoformat(self.created_at),
            'created_by': self.created_by,
            'last_success_at': utc_isoformat(self.last_success_at),
            'last_failure_at': utc_isoformat(self.last_failure_at),
            'failure_count': self.failure_count or 0,
        }
        if self.is_http:
            data.update({
                'url': self.url,
                'http_method': self.http_method or 'POST',
                'http_header_names': self.http_header_names(),
                'body_template': self.body_template or '',
                'tls_ca_pem': self.tls_ca_pem or '',
                'allow_private_key': bool(self.allow_private_key),
            })
        else:
            data.update({
                'public_key': self.public_key,
                'host_key_fingerprint': self.host_key_fingerprint(),
                'host_key_pinned': bool(self.host_key),
            })
        return data


class DeployBinding(db.Model):
    """Attach a certificate to a target with fixed destination paths."""
    __tablename__ = 'deploy_bindings'
    __table_args__ = (
        db.UniqueConstraint('target_id', 'certificate_id', name='uq_deploy_binding'),
    )

    id = db.Column(db.Integer, primary_key=True)
    target_id = db.Column(db.Integer, db.ForeignKey('deploy_targets.id'), nullable=False, index=True)
    certificate_id = db.Column(db.Integer, db.ForeignKey('certificates.id'), nullable=False, index=True)
    # Destination paths on the target; NULL = don't push that file
    cert_path = db.Column(db.String(512))
    key_path = db.Column(db.String(512))
    fullchain_path = db.Column(db.String(512))
    # Trusted roots are normally installed separately and should not be sent
    # in a TLS server's fullchain. Keep the exceptional legacy behaviour as
    # an explicit per-binding choice.
    include_root = db.Column(db.Boolean, nullable=False, default=False)
    # 'auto' = the chain the CA serves; otherwise a variant id ('primary', 'cross:<id>')
    chain_variant = db.Column(db.String(40), nullable=False, default='auto', server_default='auto')
    # Optional command for this certificate deployment only. The same SSH
    # target can therefore serve different daemons with different reloads.
    reload_command = db.Column(db.String(512))
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    # Set when a renewal left this binding on the previous certificate (migration 151);
    # cleared by reattachment, or when the successor receives its key
    attention_reason = db.Column(db.String(40))
    attention_successor_id = db.Column(db.Integer, index=True)

    created_at = db.Column(db.DateTime, default=utc_now)
    created_by = db.Column(db.String(80))

    target = db.relationship('DeployTarget', backref=db.backref('bindings', lazy='dynamic'))
    certificate = db.relationship('Certificate', backref=db.backref('deploy_bindings', lazy='dynamic'))
    # No foreign key: deleting the successor clears the state (services.binding_attention)
    attention_successor = db.relationship(
        'Certificate', primaryjoin='foreign(DeployBinding.attention_successor_id) == Certificate.id',
        viewonly=True)

    def attention(self):
        """The left-behind state as the API shows it, or None."""
        if not self.attention_reason:
            return None
        from services.binding_attention import can_reattach
        successor = self.attention_successor
        return {
            'reason': self.attention_reason,
            'successor_id': self.attention_successor_id,
            'successor_refid': successor.refid if successor else None,
            'successor_has_key': bool(successor and successor.has_private_key),
            'can_reattach': can_reattach(self),
        }

    def to_dict(self, include_target=True):
        data = {
            'id': self.id,
            'target_id': self.target_id,
            'certificate_id': self.certificate_id,
            'cert_path': self.cert_path,
            'key_path': self.key_path,
            'fullchain_path': self.fullchain_path,
            'include_root': self.include_root,
            'chain_variant': self.chain_variant or 'auto',
            'reload_command': self.reload_command,
            'enabled': self.enabled,
            'created_at': utc_isoformat(self.created_at),
            'created_by': self.created_by,
            'needs_attention': self.attention(),
        }
        if include_target and self.target:
            data['target_name'] = self.target.name
            data['target_host'] = self.target.host
            data['target_kind'] = self.target.kind or DeployTarget.KIND_SSH
            data['target_enabled'] = self.target.enabled
        return data


class CRLDeployBinding(db.Model):
    """Attach a CA's complete CRL to an existing SSH deploy target."""
    __tablename__ = 'crl_deploy_bindings'
    __table_args__ = (
        db.UniqueConstraint('target_id', 'ca_id', name='uq_crl_deploy_binding'),
    )

    FORMAT_PEM = 'pem'
    FORMAT_DER = 'der'

    id = db.Column(db.Integer, primary_key=True)
    target_id = db.Column(
        db.Integer, db.ForeignKey('deploy_targets.id'), nullable=False, index=True)
    ca_id = db.Column(
        db.Integer, db.ForeignKey('certificate_authorities.id'), nullable=False, index=True)
    crl_path = db.Column(db.String(512), nullable=False)
    format = db.Column(db.String(8), nullable=False, default=FORMAT_PEM)
    include_parent_crls = db.Column(db.Boolean, nullable=False, default=False)
    reload_command = db.Column(db.String(512))
    enabled = db.Column(db.Boolean, nullable=False, default=True)

    created_at = db.Column(db.DateTime, default=utc_now)
    created_by = db.Column(db.String(80))

    target = db.relationship(
        'DeployTarget', backref=db.backref('crl_bindings', lazy='dynamic'))
    ca = db.relationship(
        'CA', backref=db.backref('crl_deploy_bindings', lazy='dynamic'))

    def to_dict(self, include_target=True):
        data = {
            'id': self.id,
            'target_id': self.target_id,
            'ca_id': self.ca_id,
            'crl_path': self.crl_path,
            'format': self.format,
            'include_parent_crls': self.include_parent_crls,
            'reload_command': self.reload_command,
            'enabled': self.enabled,
            'created_at': utc_isoformat(self.created_at),
            'created_by': self.created_by,
        }
        if self.ca:
            data['ca_name'] = self.ca.descr
            data['ca_refid'] = self.ca.refid
        if include_target and self.target:
            data['target_name'] = self.target.name
            data['target_host'] = self.target.host
            data['target_enabled'] = self.target.enabled
        return data


class DeployDelivery(db.Model):
    """Durable deploy queue — same model as webhook_deliveries: pending rows
    are drained by a scheduler task with retry/backoff."""
    __tablename__ = 'deploy_deliveries'

    STATUS_PENDING = 'pending'
    STATUS_DELIVERED = 'delivered'
    STATUS_FAILED = 'failed'

    BINDING_CERTIFICATE = 'certificate'
    BINDING_CRL = 'crl'

    id = db.Column(db.Integer, primary_key=True)
    # Logical reference to deploy_bindings.id (no DB-level FK so delivery
    # history survives binding deletion until explicitly cleaned up).
    binding_id = db.Column(db.Integer, nullable=False, index=True)
    binding_type = db.Column(
        db.String(16), nullable=False, default=BINDING_CERTIFICATE, index=True)
    # Certificate: 'certificate.issued', 'certificate.renewed', 'initial',
    # 'binding.updated', 'manual'. CRL: 'crl.updated' plus the shared latter
    # three event types.
    event_type = db.Column(db.String(32), nullable=False)

    status = db.Column(db.String(16), nullable=False, default=STATUS_PENDING, index=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    max_attempts = db.Column(db.Integer, nullable=False, default=5)
    next_attempt_at = db.Column(db.DateTime, default=utc_now, index=True)

    last_error = db.Column(db.Text)
    # JSON summary of what was pushed / reload outcome, for the UI history
    detail = db.Column(db.Text)
    triggered_by = db.Column(db.String(80))

    created_at = db.Column(db.DateTime, default=utc_now)
    delivered_at = db.Column(db.DateTime)

    def get_detail(self):
        try:
            return json.loads(self.detail) if self.detail else None
        except Exception:
            return None

    def to_dict(self):
        return {
            'id': self.id,
            'binding_id': self.binding_id,
            'binding_type': self.binding_type,
            'event_type': self.event_type,
            'status': self.status,
            'attempts': self.attempts,
            'max_attempts': self.max_attempts,
            'next_attempt_at': utc_isoformat(self.next_attempt_at),
            'last_error': self.last_error,
            'detail': self.get_detail(),
            'triggered_by': self.triggered_by,
            'created_at': utc_isoformat(self.created_at),
            'delivered_at': utc_isoformat(self.delivered_at),
        }
