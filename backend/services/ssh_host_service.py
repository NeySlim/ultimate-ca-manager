"""SSH hosts (issue #451): single-use enrollment tokens exchanged for a host certificate.

A token is created by an administrator for one host CA, the principals the host may claim and
the validity of its certificates; only its SHA-256 is stored and it is spent at the first
exchange. The host sends its own public key and the token signed with it: UCM never sees a
host's private key.
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
from sqlalchemy import or_, update

from models import db
from models.ssh import SSHCertificate, SSHCertificateAuthority, SSHHost, SSHHostEnrollmentToken
from services.ssh_cert.signing import MAX_VALIDITY_SECONDS
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

TOKEN_PREFIX = 'ucmh_'
ENROLL_NAMESPACE = 'ucm-ssh-host-enrollment'
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


def enroll(ca_refid, secret, public_key, principals=None, ip=None, signature=None):
    """(host, certificate) for the host key *public_key*, whose possession *signature* proves
    (the token signed with it, namespace ENROLL_NAMESPACE); EnrollmentRefused otherwise."""
    from services.ssh_cert import SSHCertificateService
    from services.ssh_cert.utils import SSHCertificateUtilsMixin
    from utils import sshsig
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
    # A public key is public: only the holder of its private key enrolls it
    if not isinstance(signature, str) or not signature.strip():
        raise EnrollmentRefused(403, 'the signature does not prove the host key',
                                'no signature of the token by the host key')
    try:
        sshsig.verify(signature, secret.encode(), ENROLL_NAMESPACE, key_line)
    except sshsig.SignatureError as e:
        raise EnrollmentRefused(403, 'the signature does not prove the host key', str(e)) from None
    fingerprint = SSHCertificateUtilsMixin._compute_fingerprint(key)
    enrolled = SSHHost.query.filter(SSHHost.ssh_ca_id == ca.id, SSHHost.fingerprint == fingerprint,
                                    SSHHost.revoked_at.is_(None)).first()
    if enrolled is not None and set(enrolled.get_principals()) != set(names):
        raise EnrollmentRefused(409, 'this host key is enrolled with other host names: revoke that host first',
                                f'key {fingerprint} is enrolled as host {enrolled.name} with other host names')

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

    try:
        cert = SSHCertificateService.sign_certificate(
            ca_id=ca.id, public_key_data=key_line, cert_type='host', principals=names,
            validity_seconds=token.validity_seconds, descr=f"Host cert for {', '.join(names)}",
            source='enrollment', username='ssh-host-enrollment')
    except Exception as e:
        # Nothing was issued: the token is given back, unless another write touched it since
        prefix = token.token_prefix
        db.session.rollback()
        try:
            db.session.execute(update(table).where(table.c.id == token.id, table.c.used_at == now,
                                                   table.c.used_by_host_id.is_(None)).values(used_at=None))
            db.session.commit()
        except Exception as lost:
            # The signing error is the one to report: this one only leaves the token spent
            db.session.rollback()
            logger.error(f'Enrollment token {prefix} could not be given back ({lost}) '
                         f'after a failed signature: {e}')
        if isinstance(e, ValueError):
            raise EnrollmentRefused(400, str(e)) from None
        raise

    host = SSHHost.query.filter(SSHHost.ssh_ca_id == ca.id, SSHHost.fingerprint == fingerprint,
                                SSHHost.revoked_at.is_(None)).first()
    if host is None:
        host = SSHHost(ssh_ca_id=ca.id, fingerprint=fingerprint, enrolled_at=now)
        db.session.add(host)
        # Named once: enrolled again, with the same names in any order, the host keeps its own
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


def _live_certificates_of_key(host):
    """Ids of the unrevoked, unexpired certificates of *host*'s CA for its key, current first."""
    key = host.public_key.split()[:2]
    certs = SSHCertificate.query.filter(
        SSHCertificate.ssh_ca_id == host.ssh_ca_id, SSHCertificate.valid_to > utc_now(),
        or_(SSHCertificate.revoked.is_(False), SSHCertificate.revoked.is_(None))).all()
    ids = [c.id for c in certs if (c.public_key or '').split()[:2] == key]
    return sorted(ids, key=lambda i: (i != host.certificate_id, i))


def _sweepable(host):
    """Live certificates of the revoked *host*'s key that its revocation owes to the KRL: issued
    before it, or by its renewal, and before the key was enrolled again as an unrevoked host."""
    successor = SSHHost.query.filter(
        SSHHost.ssh_ca_id == host.ssh_ca_id, SSHHost.fingerprint == host.fingerprint,
        SSHHost.revoked_at.is_(None)).first()
    ids = []
    for cert_id in _live_certificates_of_key(host):
        cert = db.session.get(SSHCertificate, cert_id)
        if successor is not None and cert.created_at >= successor.enrolled_at:
            continue
        if cert.created_at <= host.revoked_at or cert.source == 'renewal':
            ids.append(cert_id)
    return ids


def _sweep(host, reason, username):
    """How many of the certificates owed by the revoked *host* this call revoked."""
    from services.ssh_cert import SSHCertificateService
    swept = 0
    for cert_id in _sweepable(host):
        try:
            SSHCertificateService.revoke_certificate(cert_id, reason, username)
            swept += 1
        except ValueError:
            pass  # revoked meanwhile, or with a sibling of the same serial
    return swept


def revoke_host(host_id, reason='host revoked', username=None):
    """Every live certificate of the host key under its CA revoked (published in the KRL), the
    ones a renewal or a new enrollment replaced included, and its renewals ended for good.
    ValueError when the host was revoked already and nothing was left to revoke."""
    host = db.session.get(SSHHost, host_id)
    if not host:
        raise LookupError('SSH host not found')
    # Revoked before its certificates are looked up: a renewal signed after this point sees it
    table = SSHHost.__table__
    done = db.session.execute(update(table).where(table.c.id == host_id, table.c.revoked_at.is_(None)).values(
        revoked_at=utc_now(), auto_renew=False, challenge=None, challenge_expires_at=None))
    first = done.rowcount == 1
    db.session.commit()
    host = db.session.get(SSHHost, host_id)
    # Swept on every request: one cut short leaves the host revoked, the next revokes what it left,
    # never the certificates of a host the key was enrolled as since
    swept = _sweep(host, reason, username)
    if not first and not swept:
        raise ValueError('This host is already revoked')
    return db.session.get(SSHHost, host_id)


REVOKED_HOST_SWEEP_SECONDS = 300


def sweep_revoked_hosts():
    """Scheduled: what an interrupted host revocation or renewal left live goes to the KRL."""
    from services.audit_service import AuditService
    live = {}  # per CA, the keys holding a live certificate: one read per CA, not per host
    total = 0
    for host in SSHHost.query.filter(SSHHost.revoked_at.isnot(None)).order_by(SSHHost.id).all():
        if host.ssh_ca_id not in live:
            live[host.ssh_ca_id] = {tuple((c.public_key or '').split()[:2]) for c in SSHCertificate.query.filter(
                SSHCertificate.ssh_ca_id == host.ssh_ca_id, SSHCertificate.valid_to > utc_now(),
                or_(SSHCertificate.revoked.is_(False), SSHCertificate.revoked.is_(None)))}
        if tuple(host.public_key.split()[:2]) not in live[host.ssh_ca_id]:
            continue
        host_id, name = host.id, host.name
        try:
            swept = _sweep(host, 'host revoked', 'system')
        except Exception as e:
            db.session.rollback()
            logger.error(f'Revoked host {name}: its certificates left live could not be revoked: {e}')
            continue
        if swept:
            total += swept
            AuditService.log_action(
                action='ssh_host_revocation_finished', resource_type='ssh_host', resource_id=str(host_id),
                resource_name=name, username='system', success=True,
                details=f'SSH host revocation finished: {swept} certificate(s) left live revoked')
    return total


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


# --- renewal: proof of possession of the certified host key (PROTOCOL.sshsig)

NAMESPACE = 'ucm-ssh-host-renewal'
CHALLENGE_SECONDS = 300
SEEN_EVERY_SECONDS = 60


class RenewalRefused(EnrollmentRefused):
    """*state* names a refusal the agent waits out (``disabled``) or stops on (anything else);
    *audited* is False for an expected answer repeated at every sync."""

    def __init__(self, status, public, reason=None, state='refused', audited=True):
        super().__init__(status, public, reason)
        self.state, self.audited = state, audited


def _renewal_window(cert, percent):
    """When a certificate enters its last *percent* of the lifetime it was issued with."""
    lifetime = cert.valid_to - (cert.created_at or cert.valid_from)
    return cert.valid_to - lifetime * (percent / 100)


def _renewable_host(host_refid):
    host = SSHHost.query.filter_by(refid=host_refid).first() if isinstance(host_refid, str) else None
    if host is None:
        raise RenewalRefused(404, 'unknown host', f'no host {str(host_refid)[:40]}', state='unknown')
    if host.revoked_at:
        raise RenewalRefused(403, 'this host is revoked: enroll it again', f'host {host.name} is revoked',
                             state='revoked')
    if not host.auto_renew:
        raise RenewalRefused(403, 'renewal is disabled for this host', f'host {host.name}: renewal disabled',
                             state='disabled', audited=False)
    cert = host.certificate
    if cert is None or cert.revoked:
        raise RenewalRefused(403, 'the host certificate is revoked: enroll again',
                             f'host {host.name}: its certificate is revoked', state='revoked')
    if cert.is_expired:
        raise RenewalRefused(403, 'the host certificate has expired: enroll again',
                             f'host {host.name}: its certificate has expired', state='expired')
    # The key signing the proof is the key this certificate certifies, nothing stored beside it
    if cert.public_key.split()[:2] != host.public_key.split()[:2]:
        raise RenewalRefused(403, 'the host certificate does not certify the enrolled key',
                             f'host {host.name}: certificate and key differ', state='revoked')
    return host, cert


def challenge(host_refid):
    """{'due': 0, 'renew_after'} while the certificate is young, else {'due': 1, 'challenge'}."""
    host, cert = _renewable_host(host_refid)
    now = utc_now()
    if host.last_seen_at is None or (now - host.last_seen_at).total_seconds() >= SEEN_EVERY_SECONDS:
        host.last_seen_at = now
    window = _renewal_window(cert, host.renew_percent or RENEW_PERCENT_DEFAULT)
    if now < window:
        db.session.commit()
        return {'due': 0, 'renew_after': window}
    # A pending challenge is handed out again: a stranger asking for one cannot void the host's
    if not host.challenge or not host.challenge_expires_at or host.challenge_expires_at <= now:
        host.challenge = secrets.token_urlsafe(32)
        host.challenge_expires_at = now + timedelta(seconds=CHALLENGE_SECONDS)
    db.session.commit()
    return {'due': 1, 'challenge': host.challenge, 'namespace': NAMESPACE}


def renew(host_refid, answered, signature):
    """(host, new certificate): *signature* is an SSH signature of the pending challenge
    *answered*, made with the key the current, unrevoked certificate certifies."""
    from services.ssh_cert import SSHCertificateService
    from utils import sshsig
    host, cert = _renewable_host(host_refid)
    now = utc_now()
    pending = host.challenge
    if (not isinstance(answered, str) or not pending or not host.challenge_expires_at
            or host.challenge_expires_at <= now or not secrets.compare_digest(answered, pending)):
        raise RenewalRefused(403, 'unknown or expired challenge', f'host {host.name}: no such pending challenge')
    try:
        sshsig.verify(signature, answered.encode(), NAMESPACE, cert.public_key)
    except sshsig.SignatureError as e:
        raise RenewalRefused(403, 'the signature does not prove the host key', f'host {host.name}: {e}') from None
    # Spent before the signature: one challenge, one certificate
    table = SSHHost.__table__
    spent = db.session.execute(update(table).where(table.c.id == host.id, table.c.challenge == pending)
                               .values(challenge=None, challenge_expires_at=None))
    if spent.rowcount != 1:
        db.session.rollback()
        raise RenewalRefused(403, 'unknown or expired challenge', f'host {host.name}: challenge spent meanwhile')
    db.session.commit()
    names = host.get_principals()
    try:
        new = SSHCertificateService.sign_certificate(
            ca_id=host.ssh_ca_id, public_key_data=host.public_key, cert_type='host', principals=names,
            validity_seconds=host.validity_seconds, descr=f"Host cert for {', '.join(names)}",
            source='renewal', username='ssh-host-renewal')
    except ValueError as e:
        raise RenewalRefused(400, str(e), f'host {host.name}: {e}') from None
    host = db.session.get(SSHHost, host.id)
    db.session.refresh(host)
    if host.revoked_at:
        # Revoked while this certificate was signed: it goes to the KRL, never to the host. The
        # host keeps no reason of its own; a failure here leaves it to the next host revocation
        name, new_id = host.name, new.id
        try:
            SSHCertificateService.revoke_certificate(new_id, 'host revoked', 'ssh-host-renewal')
        except ValueError:
            pass  # revoked by the host's revocation itself
        except Exception as e:
            db.session.rollback()
            logger.error(f'Host {name} was revoked during its renewal, but its new certificate '
                         f'{new_id} could not be revoked ({e}): the revoked host sweep will revoke it')
        raise RenewalRefused(403, 'this host is revoked: enroll it again',
                             f'host {name} was revoked during its renewal', state='revoked')
    host.certificate_id = new.id
    host.last_renewed_at = host.last_seen_at = utc_now()
    db.session.commit()
    return host, new


def krl_pulled(host_refid):
    """The agent of this host downloaded a KRL: recorded at most once a minute, as it claims."""
    if not isinstance(host_refid, str) or not re.fullmatch(r'[A-Za-z0-9-]{1,36}', host_refid):
        return
    now = utc_now()
    table = SSHHost.__table__
    try:
        db.session.execute(update(table).where(
            table.c.refid == host_refid, table.c.revoked_at.is_(None),
            (table.c.last_krl_sync_at.is_(None))
            | (table.c.last_krl_sync_at < now - timedelta(seconds=SEEN_EVERY_SECONDS))
        ).values(last_krl_sync_at=now))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.warning(f'Could not record the KRL download of host {host_refid}: {e}')
