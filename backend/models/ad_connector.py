"""
Active Directory Connector model.

A single stored LDAP connection UCM uses to query Active Directory directly
-- currently for one purpose: resolving a Kerberos machine principal (e.g.
``WIN11$@HAGLAND.DOMAIN``) to its computer object's ``dNSHostName`` attribute,
so MS-WSTEP's Kerberos-bound CES endpoint can derive a subject/SAN for the
"naked" CSRs Windows' unattended GPO autoenrollment submits for machine
templates (see ``services/ad_connector/lookup.py``).

Deliberately separate from ``models/sso.py``'s ``SSOProvider`` LDAP fields:
SSO's LDAP provider isn't necessarily even Active Directory, and this
connector needs to be configurable independently of whether SSO is set up
at all -- an admin using local UCM accounts would never think to look under
SSO settings to enable AD connectivity for certificate autoenrollment.

Single-row table: there's exactly one AD UCM needs to talk to for this
purpose, the same posture as the Kerberos SPN/keytab config (one keytab per
UCM instance, not a multi-connection list).

Secrets encrypted at rest using ``utils/encryption.py`` (fail-closed: if the
encryption key can't be derived, saving raises rather than silently
persisting plaintext) -- the same mechanism and pattern as ``models/msca.py``'s
``MicrosoftCA.password``. Deliberately not ``security/encryption.py``, whose
``encrypt_string()`` silently returns plaintext when no master key is
configured (the out-of-the-box state on most installs) -- wrong fail
direction for a bind password.
"""

from models import db
from utils.datetime_utils import utc_now, utc_isoformat


class ADConnectorConfig(db.Model):
    """Active Directory connector connection configuration (single row)."""
    __tablename__ = 'ad_connector_config'

    id = db.Column(db.Integer, primary_key=True)

    server = db.Column(db.String(500))
    port = db.Column(db.Integer, default=389)
    use_ssl = db.Column(db.Boolean, default=False)
    verify_ssl = db.Column(db.Boolean, default=True)
    ca_bundle = db.Column(db.Text)

    base_dn = db.Column(db.String(500))
    bind_dn = db.Column(db.String(500))
    _bind_password = db.Column('bind_password', db.String(500))

    enabled = db.Column(db.Boolean, default=False)

    last_test_at = db.Column(db.DateTime)
    last_test_result = db.Column(db.String(500))

    # Last verdict of the scheduled DC probe, as JSON. On the row rather
    # than in process memory: the worker holding the scheduler's singleton
    # lock is the one that probes, and every other worker has to read it.
    _health = db.Column('health', db.Text)
    health_probe_interval = db.Column(db.Integer, default=120)

    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    created_by = db.Column(db.String(80))

    @property
    def servers(self):
        """The configured domain controllers as a list, in failover order.

        Stored newline-separated in the one ``server`` column rather than a
        child table: this is a single-row config whose server list is read
        whole on every use and never queried by member, so a table would
        buy nothing and cost a migration plus a backup-manifest section.
        A config written before the field accepted more than one DC holds a
        bare hostname, which parses as a one-element list unchanged.
        """
        from services.ad_connector.lookup import split_servers
        return split_servers(self.server)

    @servers.setter
    def servers(self, values):
        from services.ad_connector.lookup import join_servers
        self.server = join_servers(values) or None

    @property
    def health(self):
        """The stored probe verdict as a dict (``{}`` when never probed)."""
        from services.ad_connector.health import parse_health
        return parse_health(self._health)

    @health.setter
    def health(self, value):
        import json
        self._health = json.dumps(value) if value else None

    @property
    def bind_password(self):
        if not self._bind_password:
            return None
        try:
            from utils.encryption import decrypt_if_needed
            return decrypt_if_needed(self._bind_password)
        except Exception:
            return self._bind_password

    @bind_password.setter
    def bind_password(self, value):
        if value:
            # Fail-closed: if encryption is broken (missing key, etc.) we
            # MUST NOT silently store the credential in plaintext. Let the
            # exception propagate so the caller sees the failure and the
            # row is never persisted.
            from utils.encryption import encrypt_if_needed
            self._bind_password = encrypt_if_needed(value)
        else:
            self._bind_password = None

    @classmethod
    def get_singleton(cls):
        """The one connector row, or ``None`` if never configured."""
        return cls.query.first()

    def to_dict(self, include_secrets=False):
        from services.ad_connector.health import is_fresh, stale_after
        data = {
            'id': self.id,
            'server': self.server or '',
            'servers': self.servers,
            'port': self.port or 389,
            'use_ssl': bool(self.use_ssl),
            'verify_ssl': bool(self.verify_ssl),
            'ca_bundle': self.ca_bundle or '',
            'base_dn': self.base_dn or '',
            'bind_dn': self.bind_dn or '',
            'bind_password': '***' if self._bind_password else None,
            'enabled': bool(self.enabled),
            'last_test_at': utc_isoformat(self.last_test_at),
            'last_test_result': self.last_test_result,
            'health': self.health,
            'health_probe_interval': self.health_probe_interval or 120,
            # The window _connect applies to `health` before acting on it,
            # and the verdict on this row read against that window here
            # rather than in the browser, whose clock can be wrong.
            'health_stale_after': stale_after(self.health_probe_interval),
            'health_fresh': is_fresh(self.health, self.health_probe_interval),
            'created_at': utc_isoformat(self.created_at),
            'updated_at': utc_isoformat(self.updated_at),
            'created_by': self.created_by,
        }
        if include_secrets:
            data['bind_password'] = self.bind_password
        return data
