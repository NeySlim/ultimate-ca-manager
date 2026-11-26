"""SSH hosts (issue #451): single-use enrollment tokens exchanged for a host certificate.

A token is created by an administrator for one host CA, the principals the host may claim and
the validity of its certificates; only its SHA-256 is stored and it is spent at the first
exchange. The host sends its own public key: UCM never sees a host's private key.
"""
import fnmatch
import hashlib
import ipaddress
import json
import logging
import re
import secrets
from datetime import timedelta

from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from cryptography.hazmat.primitives.serialization import ssh as ssh_serialization
from sqlalchemy import update

from models import db
from models.ssh import SSHCertificateAuthority, SSHHost, SSHHostEnrollmentToken
from services.ssh_cert.signing import MAX_VALIDITY_SECONDS
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

TOKEN_PREFIX = 'ucmh_'
_TOKEN = re.compile(r'^ucmh_[A-Za-z0-9_-]{43}$')
_HOSTNAME = re.compile(r'^(?=.{1,253}$)[A-Za-z0-9_](?:[A-Za-z0-9_-]{0,62})(?:\.[A-Za-z0-9_](?:[A-Za-z0-9_-]{0,62}))*\.?$')
MAX_PRINCIPALS = 32
TOKEN_LIFETIME_DEFAULT = 3600
TOKEN_LIFETIME_RANGE = (300, 7 * 86400)
RENEW_PERCENT_DEFAULT = 30
RENEW_PERCENT_RANGE = (5, 90)
MIN_RSA_BITS = 2048
MAX_PUBLIC_KEY_LENGTH = 16384


class EnrollmentRefused(Exception):
    """An exchange refused: *status* and *public* answer the host, *reason* goes to the audit."""

    def __init__(self, status, public, reason=None):
        super().__init__(reason or public)
        self.status, self.public, self.reason = status, public, reason or public


def hash_token(secret):
    return hashlib.sha256(secret.encode('utf-8')).hexdigest()


def checked_principals(principals):
    """Host names or IP addresses, each once, in order; ValueError otherwise."""
    if isinstance(principals, str):
        principals = principals.split(',')
    if not isinstance(principals, list):
        raise ValueError('principals must be a list of host names')
    seen = []
    for name in principals:
        if not isinstance(name, str):
            raise ValueError('principals must be a list of host names')
        name = name.strip()
        if not name:
            continue
        try:
            ipaddress.ip_address(name)
        except ValueError:
            if not _HOSTNAME.match(name):
                raise ValueError(f'invalid host name: {name[:80]!r}') from None
        if name not in seen:
            seen.append(name)
    if not seen:
        raise ValueError('at least one host name is required')
    if len(seen) > MAX_PRINCIPALS:
        raise ValueError(f'at most {MAX_PRINCIPALS} host names')
    return seen


def checked_host_key(public_key):
    """(key, 'type base64') of a host public key line; ValueError for anything else."""
    from services.ssh_cert.utils import SSHCertificateUtilsMixin
    if not isinstance(public_key, str) or not public_key.strip() or len(public_key) > MAX_PUBLIC_KEY_LENGTH:
        raise ValueError('public_key is required')
    parts = public_key.split()
    if len(parts) < 2 or '-cert-' in parts[0]:
        raise ValueError('public_key must be an OpenSSH public key, not a certificate')
    try:
        key = ssh_serialization.load_ssh_public_key(f'{parts[0]} {parts[1]}'.encode())
    except Exception:
        raise ValueError('public_key is not a valid OpenSSH public key') from None
    # The FIPS refusal of Ed25519, as for any SSH key UCM signs
    SSHCertificateUtilsMixin._parse_public_key(f'{parts[0]} {parts[1]}')
    if isinstance(key, rsa.RSAPublicKey):
        if key.key_size < MIN_RSA_BITS:
            raise ValueError(f'an RSA host key needs {MIN_RSA_BITS} bits at least')
    elif not isinstance(key, (ed25519.Ed25519PublicKey, ec.EllipticCurvePublicKey)):
        raise ValueError('unsupported host key type')
    return key, ssh_serialization.serialize_ssh_public_key(key).decode()


def _check_against_ca(ca, principals):
    allowed = ca.get_allowed_principals()
    if not allowed and not ca.allow_any_principal:
        raise ValueError('This SSH CA lists no allowed principals: add some, or allow any principal')
    for name in principals:
        if allowed and not any(fnmatch.fnmatchcase(name, pattern) for pattern in allowed):
            raise ValueError(f"Principal '{name}' is not in the CA's allowed principals list")


def _ranged(value, name, low, high, default):
    if value is None or value == '':
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f'{name} must be an integer')
    if not low <= value <= high:
        raise ValueError(f'{name} must be between {low} and {high}')
    return value


def create_token(ca_id, principals, *, validity_seconds=None, lifetime_seconds=None,
                 renew_percent=None, descr=None, username=None):
    """(token row, secret): the secret is shown once and never stored."""
    ca = db.session.get(SSHCertificateAuthority, ca_id) if isinstance(ca_id, int) else None
    if not ca:
        raise LookupError('SSH CA not found')
    if ca.ca_type != 'host':
        raise ValueError('Enrollment tokens are for host CAs')
    names = checked_principals(principals)
    _check_against_ca(ca, names)
    validity = _ranged(validity_seconds, 'validity_seconds', 60, MAX_VALIDITY_SECONDS, None)
    if validity and ca.max_ttl and validity > ca.max_ttl:
        raise ValueError(f"validity_seconds exceeds this CA's max_ttl ({ca.max_ttl} seconds)")
    lifetime = _ranged(lifetime_seconds, 'lifetime_seconds', *TOKEN_LIFETIME_RANGE, TOKEN_LIFETIME_DEFAULT)
    percent = _ranged(renew_percent, 'renew_percent', *RENEW_PERCENT_RANGE, RENEW_PERCENT_DEFAULT)
    if descr is not None and (not isinstance(descr, str) or len(descr) > 255):
        raise ValueError('descr is text of 255 characters at most')
    secret = TOKEN_PREFIX + secrets.token_urlsafe(32)
    now = utc_now()
    token = SSHHostEnrollmentToken(
        ssh_ca_id=ca.id, token_hash=hash_token(secret), token_prefix=secret[:12],
        descr=(descr or '').strip() or None, principals=json.dumps(names), validity_seconds=validity,
        renew_percent=percent, expires_at=now + timedelta(seconds=lifetime), created_at=now,
        created_by=username)
    db.session.add(token)
    db.session.commit()
    return token, secret


def revoke_token(token_id):
    token = db.session.get(SSHHostEnrollmentToken, token_id)
    if not token:
        raise LookupError('Enrollment token not found')
    if token.revoked_at or token.used_at:
        raise ValueError(f'This token is already {token.state}')
    token.revoked_at = utc_now()
    db.session.commit()
    return token


def enroll(ca_refid, secret, public_key, principals=None, ip=None):
    """(host, certificate) for the host key *public_key*; EnrollmentRefused otherwise."""
    from services.ssh_cert import SSHCertificateService
    refused = EnrollmentRefused(403, 'invalid, used or expired enrollment token')
    if not isinstance(secret, str) or not _TOKEN.match(secret):
        raise EnrollmentRefused(403, refused.public, 'malformed token')
    ca = SSHCertificateAuthority.query.filter_by(refid=ca_refid).first()
    if not ca:
        raise EnrollmentRefused(404, 'SSH CA not found')
    token = SSHHostEnrollmentToken.query.filter_by(token_hash=hash_token(secret)).first()
    if token is None:
        raise EnrollmentRefused(403, refused.public, 'unknown token')
    if token.ssh_ca_id != ca.id:
        raise EnrollmentRefused(403, refused.public, f'token {token.token_prefix} is for another CA')
    if token.state != 'active':
        raise EnrollmentRefused(403, refused.public, f'token {token.token_prefix} is {token.state}')
    try:
        key, key_line = checked_host_key(public_key)
        allowed = token.get_principals()
        names = allowed if principals in (None, [], '') else checked_principals(principals)
    except ValueError as e:
        raise EnrollmentRefused(400, str(e)) from None
    outside = [n for n in names if n not in allowed]
    if outside:
        raise EnrollmentRefused(403, f"host name not allowed by this token: {outside[0]}")

    # Spent before the signature: two exchanges of one token, one wins
    now = utc_now()
    table = SSHHostEnrollmentToken.__table__
    spent = db.session.execute(update(table).where(
        table.c.id == token.id, table.c.used_at.is_(None), table.c.revoked_at.is_(None),
        table.c.expires_at > now).values(used_at=now))
    if spent.rowcount != 1:
        db.session.rollback()
        raise EnrollmentRefused(403, refused.public, f'token {token.token_prefix} spent meanwhile')
    db.session.commit()

    from services.ssh_cert.utils import SSHCertificateUtilsMixin
    fingerprint = SSHCertificateUtilsMixin._compute_fingerprint(key)
    try:
        cert = SSHCertificateService.sign_certificate(
            ca_id=ca.id, public_key_data=key_line, cert_type='host', principals=names,
            validity_seconds=token.validity_seconds, descr=f"Host cert for {', '.join(names)}",
            source='enrollment', username='ssh-host-enrollment')
    except ValueError as e:
        raise EnrollmentRefused(400, str(e)) from None

    host = SSHHost.query.filter(SSHHost.ssh_ca_id == ca.id, SSHHost.fingerprint == fingerprint,
                                SSHHost.revoked_at.is_(None)).first()
    if host is None:
        host = SSHHost(ssh_ca_id=ca.id, fingerprint=fingerprint, enrolled_at=now)
        db.session.add(host)
    host.name = names[0]
    host.principals = json.dumps(names)
    host.public_key = key_line
    host.key_type = SSHCertificateUtilsMixin._detect_key_type(key)
    host.validity_seconds = token.validity_seconds
    host.renew_percent = token.renew_percent
    host.certificate_id = cert.id
    host.auto_renew = True
    host.enrolled_ip = (ip or '')[:45] or None
    host.token_id = token.id
    host.last_seen_at = now
    host.challenge = host.challenge_expires_at = None
    db.session.flush()
    db.session.execute(update(table).where(table.c.id == token.id).values(used_by_host_id=host.id))
    db.session.commit()
    return host, cert


def revoke_host(host_id, reason='host revoked', username=None):
    """The host's certificate revoked (published in the KRL) and its renewals ended for good."""
    from services.ssh_cert import SSHCertificateService
    host = db.session.get(SSHHost, host_id)
    if not host:
        raise LookupError('SSH host not found')
    if host.revoked_at:
        raise ValueError('This host is already revoked')
    cert = host.certificate
    if cert is not None and not cert.revoked:
        SSHCertificateService.revoke_certificate(cert.id, reason, username)
    host = db.session.get(SSHHost, host_id)
    host.revoked_at = utc_now()
    host.auto_renew = False
    host.challenge = host.challenge_expires_at = None
    db.session.commit()
    return host


def set_auto_renew(host_id, enabled):
    host = db.session.get(SSHHost, host_id)
    if not host:
        raise LookupError('SSH host not found')
    if not isinstance(enabled, bool):
        raise ValueError('enabled must be true or false')
    if enabled and host.revoked_at:
        raise ValueError('A revoked host cannot renew: enroll it again with a new token')
    host.auto_renew = enabled
    if not enabled:
        host.challenge = host.challenge_expires_at = None
    db.session.commit()
    return host
