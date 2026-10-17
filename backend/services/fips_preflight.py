"""FIPS readiness: what a standard instance holds that FIPS mode will refuse.

Every detector reads, none writes. Key types come from stored types and
encodings (certificate SPKI, OpenSSH type names), never from loading a
private key: an EdDSA key fails to load once the FIPS provider answers.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import warnings
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Tuple

from cryptography import x509
from cryptography.utils import CryptographyDeprecationWarning
from flask import current_app

import fips_mode
from models import (CA, Certificate, CertificatePolicy, CertificateTemplate, DeployTarget,
                    DnsProvider, AcmeClientOrder, HsmKey, HsmProvider, MicrosoftCA,
                    SSHCertificate, SSHCertificateAuthority, SystemConfig, User, db)
from security.encryption import decrypt_text
from services.backup import container
from services.backup.backup_service import _ARGON2_AVAILABLE
from services.backup.schedule import _existing_archives
from services.backup.settings_contract import scheduled_kdf
from services.tsa_service import tsa_is_enabled
from utils import key_algorithms
from utils.datetime_utils import utc_now
from utils.db_url import postgres_tls_problem
from utils.key_codec import eddsa_key_name

logger = logging.getLogger(__name__)

BLOCKER, WARNING, INFO = 'blocker', 'warning', 'info'
SEVERITIES = (BLOCKER, WARNING, INFO)
MAX_EXAMPLES = 5

_EDDSA_OIDS = {'1.3.101.112': 'Ed25519', '1.3.101.113': 'Ed448'}


@dataclass(frozen=True)
class Detector:
    id: str
    severity: str
    title: str
    remedy: str
    find: Callable[[], List[str]]  # one name per affected object


DETECTORS: List[Detector] = []


def detector(id: str, severity: str, title: str, remedy: str):
    def register(find):
        DETECTORS.append(Detector(id, severity, title, remedy, find))
        return find
    return register


# --- key helpers ------------------------------------------------------------

def stored_label_approved(text) -> bool:
    """Whether a stored key spelling ('RSA 1024', 'EC-P256', 'Ed25519') is FIPS approved."""
    if not text:
        return False
    alg = key_algorithms.get(text)
    if alg is not None:
        return alg.fips_approved
    match = re.fullmatch(r'\s*RSA[\s:_-]*(\d+)\s*', str(text), re.IGNORECASE)
    return bool(match) and int(match.group(1)) >= 2048


def certificate_key(cert: x509.Certificate) -> Tuple[str, bool]:
    """(display, approved) of a certificate's key; EdDSA is told by its OID, unloaded."""
    oid = cert.public_key_algorithm_oid.dotted_string
    if oid in _EDDSA_OIDS:
        return _EDDSA_OIDS[oid], False
    try:
        public_key = cert.public_key()
    except Exception:
        return f'unreadable key ({oid})', False
    text = key_algorithms.key_algo_for_public_key(public_key)
    return text, stored_label_approved(text)


def load_stored_certificate(value) -> Optional[x509.Certificate]:
    """A certificate column (base64 of PEM, or PEM) as an object, None when unreadable."""
    if not value:
        return None
    data = value.encode() if isinstance(value, str) else bytes(value)
    if b'-----BEGIN' not in data:
        try:
            data = base64.b64decode(data)
        except ValueError:
            return None
    with warnings.catch_warnings():
        # Old imports carry non-positive serials: a report is no place to warn about them
        warnings.simplefilter('ignore', CryptographyDeprecationWarning)
        try:
            return x509.load_pem_x509_certificate(data)
        except ValueError:
            try:
                return x509.load_der_x509_certificate(data)
            except ValueError:
                return None


def _stored_cert_key(key_algo, crt) -> Tuple[str, bool]:
    if key_algo:
        return key_algo, stored_label_approved(key_algo)
    cert = load_stored_certificate(crt)
    return certificate_key(cert) if cert is not None else ('unknown key', True)


def _named(name, ident, detail=None) -> str:
    label = f'{name} (#{ident})' if name else f'#{ident}'
    return f'{label}: {detail}' if detail else label


def _active_certificate_filter(model):
    return (model.revoked.isnot(True), model.archived.isnot(True),
            model.crt.isnot(None), model.valid_to > utc_now())


# --- detectors --------------------------------------------------------------

@detector('users.password_scrypt', BLOCKER,
          'Local users with an scrypt password hash: they cannot sign in once FIPS mode is on',
          'Have each user sign in once before the switch: the hash is replaced by PBKDF2 '
          'automatically; otherwise an administrator resets the password.')
def _users_password_scrypt():
    rows = (User.query.with_entities(User.id, User.username, User.password_hash)
            .filter(User.auth_source == 'local', User.password_hash.like('scrypt:%'))
            .order_by(User.id).all())
    return [_named(r.username, r.id) for r in rows if (r.password_hash or '').startswith('scrypt:')]


@detector('users.backup_codes_scrypt', WARNING,
          'Users whose 2FA backup codes are scrypt hashes: those codes stop working in FIPS mode',
          'Ask these users to regenerate their backup codes before the switch.')
def _users_backup_codes_scrypt():
    rows = (User.query.with_entities(User.id, User.username, User.backup_codes)
            .filter(User.backup_codes.like('%scrypt:%')).order_by(User.id).all())
    found = []
    for r in rows:
        try:
            codes = json.loads(r.backup_codes)
        except (TypeError, ValueError):
            continue
        if isinstance(codes, list) and any(str(c).startswith('scrypt:') for c in codes):
            found.append(_named(r.username, r.id))
    return found


@detector('protocols.secret_scrypt', BLOCKER,
          'EST, WSTEP or XCEP passwords stored as scrypt hashes: clients are refused in FIPS mode',
          'Enter the password again in the protocol settings: it is then stored as a PBKDF2 hash.')
def _protocol_secrets_scrypt():
    keys = {'est_password': 'EST', 'wstep_password': 'WSTEP', 'xcep_password': 'XCEP'}
    rows = SystemConfig.query.filter(SystemConfig.key.in_(list(keys))).all()
    return sorted(keys[r.key] for r in rows if (r.value or '').startswith('scrypt:'))


def _ca_keys():
    for ca in CA.query.with_entities(CA.id, CA.descr, CA.crt).order_by(CA.id).all():
        cert = load_stored_certificate(ca.crt)
        if cert is not None:
            yield ca, certificate_key(cert)


@detector('ca.eddsa_key', BLOCKER,
          'Certificate authorities with an Ed25519 or Ed448 key: they cannot sign in FIPS mode',
          'Create an RSA or ECDSA (P-256/P-384/P-521) authority and move issuance to it '
          'before the switch; an authority key cannot be converted.')
def _ca_eddsa():
    return [_named(ca.descr, ca.id, name) for ca, (name, _) in _ca_keys()
            if name in _EDDSA_OIDS.values()]


@detector('ca.weak_key', BLOCKER,
          'Certificate authorities with a DSA key, RSA under 2048 bits or a curve other than P-256/384/521',
          'Create an authority with RSA 2048+ or ECDSA P-256/P-384/P-521 and move issuance to it.')
def _ca_weak():
    return [_named(ca.descr, ca.id, name) for ca, (name, approved) in _ca_keys()
            if not approved and name not in _EDDSA_OIDS.values()]


def _ssh_eddsa(key_type, public_key) -> Optional[str]:
    if str(key_type or '').lower() in ('ed25519', 'ed448'):
        return 'Ed25519' if str(key_type).lower() == 'ed25519' else 'Ed448'
    return eddsa_key_name(public_key)


@detector('ssh_ca.eddsa_key', BLOCKER,
          'SSH certificate authorities with an Ed25519 key: they cannot sign in FIPS mode',
          'Create an ECDSA or RSA SSH authority and distribute its public key to the hosts '
          'before the switch.')
def _ssh_ca_eddsa():
    ssh_ca = SSHCertificateAuthority
    rows = ssh_ca.query.with_entities(ssh_ca.id, ssh_ca.descr, ssh_ca.key_type, ssh_ca.public_key)
    return [_named(r.descr, r.id, name) for r in rows.order_by(ssh_ca.id).all()
            if (name := _ssh_eddsa(r.key_type, r.public_key))]


@detector('ssh_certificates.eddsa_key', INFO,
          'Active SSH certificates for Ed25519 keys: they stay valid but cannot be signed again',
          'Have their holders switch to an ECDSA or RSA key at the next renewal.')
def _ssh_cert_eddsa():
    ssh_cert = SSHCertificate
    rows = (ssh_cert.query.with_entities(ssh_cert.id, ssh_cert.key_id, ssh_cert.key_type)
            .filter(ssh_cert.revoked.isnot(True), ssh_cert.valid_to > utc_now())
            .order_by(ssh_cert.id).all())
    return [_named(r.key_id, r.id) for r in rows if str(r.key_type or '').lower().startswith('ed')]


@detector('deploy.ssh_eddsa_key', BLOCKER,
          'Deployment targets that sign in with an Ed25519 SSH key: deployments fail in FIPS mode',
          'Give each target a new ECDSA or RSA key and install its public key on the host.')
def _deploy_eddsa():
    found = []
    for target in DeployTarget.query.order_by(DeployTarget.id).all():
        name = eddsa_key_name(target.public_key)
        if name is None and not target.public_key:
            try:
                name = eddsa_key_name(decrypt_text(target.private_key))
            except Exception:
                name = None
        if name:
            found.append(_named(target.name, target.id, name))
    return found


def _configured_certificate(key: str, by: str):
    rows = SystemConfig.query.filter(SystemConfig.key.like(f'{key}%')).all()
    for row in rows:
        if not row.key.startswith(key) or not row.value:
            continue
        if by == 'id':
            try:
                cert = Certificate.query.filter_by(id=int(row.value)).first()
            except ValueError:
                continue
        else:
            cert = Certificate.query.filter_by(refid=row.value).first()
        if cert is not None:
            yield row, cert


@detector('ocsp.responder_unapproved_key', WARNING,
          'Delegated OCSP responders with an Ed25519/Ed448 or weak key: the CA signs instead',
          'Issue a new RSA or ECDSA responder certificate and select it in the CA settings.')
def _ocsp_responders():
    found = []
    for _row, cert in _configured_certificate('ocsp_responder_cert_', 'id'):
        name, approved = _stored_cert_key(cert.key_algo, cert.crt)
        if not approved:
            found.append(_named(cert.descr or cert.subject_cn, cert.id, name))
    return found


@detector('tsa.signer_unapproved_key', BLOCKER,
          'The timestamping certificate has an Ed25519/Ed448 or weak key: timestamps fail in FIPS mode',
          'Issue a new RSA or ECDSA timestamping certificate and select it in the TSA settings.')
def _tsa_signer():
    if not tsa_is_enabled():
        return []
    found = []
    for _row, cert in _configured_certificate('tsa_signer_cert_refid', 'refid'):
        name, approved = _stored_cert_key(cert.key_algo, cert.crt)
        if not approved:
            found.append(_named(cert.descr or cert.subject_cn, cert.id, name))
    return found


@detector('certificates.unapproved_key', INFO,
          'Active certificates with an Ed25519/Ed448 key, RSA under 2048 bits or another curve',
          'They stay valid; renew them with a new RSA 2048+ or ECDSA P-256/P-384/P-521 key, '
          'since renewing with the same key is refused in FIPS mode.')
def _certificates():
    rows = (Certificate.query
            .with_entities(Certificate.id, Certificate.descr, Certificate.subject_cn,
                           Certificate.key_algo)
            .filter(*_active_certificate_filter(Certificate)).order_by(Certificate.id).all())
    found = []
    for r in rows:
        if r.key_algo:
            name, approved = r.key_algo, stored_label_approved(r.key_algo)
        else:
            crt = Certificate.query.with_entities(Certificate.crt).filter_by(id=r.id).scalar()
            name, approved = _stored_cert_key(None, crt)
        if not approved:
            found.append(_named(r.subject_cn or r.descr, r.id, name))
    return found


@detector('templates.unapproved_key_type', WARNING,
          'Active templates whose key type is not FIPS approved: issuance from them is refused',
          'Change the key type of these templates to RSA 2048+ or ECDSA P-256/P-384/P-521.')
def _templates():
    template = CertificateTemplate
    rows = (template.query.with_entities(template.id, template.name, template.key_type)
            .filter(template.is_active.isnot(False)).order_by(template.id).all())
    return [_named(r.name, r.id, r.key_type) for r in rows
            if r.key_type and not stored_label_approved(r.key_type)]


@detector('policies.unapproved_key_type', WARNING,
          'Active policies that allow key types FIPS mode removes (Ed25519, Ed448, short RSA...)',
          'Remove those key types from the policies; a policy left with none allows no issuance.')
def _policies():
    found = []
    active = CertificatePolicy.is_active.isnot(False)
    for policy in CertificatePolicy.query.filter(active).order_by(CertificatePolicy.id).all():
        allowed = policy.get_rules().get('allowed_key_types') or []
        if not isinstance(allowed, list):
            continue
        refused = [str(k) for k in allowed if not stored_label_approved(k)]
        if refused:
            found.append(_named(policy.name, policy.id, ', '.join(refused)))
    return found


def _csr_eddsa(csr_pem) -> Optional[str]:
    try:
        csr = x509.load_pem_x509_csr(csr_pem.encode() if isinstance(csr_pem, str) else csr_pem)
        return _EDDSA_OIDS.get(csr.public_key_algorithm_oid.dotted_string)
    except Exception:
        return None


@detector('acme_client.unapproved_key_type', WARNING,
          'ACME client settings or renewing orders that use a key type FIPS mode refuses',
          'Set the ACME client key type to RSA or ECDSA and re-create these orders with a new key.')
def _acme_client():
    found = []
    setting = SystemConfig.query.filter_by(key='acme.client.key_type').first()
    if setting and setting.value and not stored_label_approved(setting.value):
        found.append(f'acme.client.key_type: {setting.value}')
    renewing = AcmeClientOrder.renewal_enabled.isnot(False)
    orders = AcmeClientOrder.query.filter(renewing).order_by(AcmeClientOrder.id).all()
    for order in orders:
        name = None
        if order.key_source == 'reuse' and order.source_certificate_id:
            cert = Certificate.query.filter_by(id=order.source_certificate_id).first()
            if cert is not None:
                display, approved = _stored_cert_key(cert.key_algo, cert.crt)
                name = None if approved else display
        elif order.key_source == 'csr' and order.csr_pem:
            name = _csr_eddsa(order.csr_pem)
        elif order.key_type and not stored_label_approved(order.key_type):
            name = order.key_type
        if name:
            found.append(_named(order.primary_domain, order.id, name))
    return found


@detector('hsm.softhsm', WARNING,
          'SoftHSM providers: SoftHSM is not a validated module, keys on it are not FIPS protected',
          'Move the keys to a validated HSM, or accept SoftHSM as a test setup only.')
def _softhsm():
    found = []
    for provider in HsmProvider.query.filter_by(type='pkcs11').order_by(HsmProvider.id).all():
        path = str(provider.get_config().get('module_path') or '')
        if 'softhsm' in path.lower() or 'softhsm' in (provider.name or '').lower():
            found.append(_named(provider.name, provider.id))
    return found


@detector('hsm.gcp_grpc', WARNING,
          'Google Cloud KMS providers: their client uses gRPC with its own TLS, outside the FIPS module',
          'Prefer a PKCS#11, Azure Key Vault or OpenBao provider for keys that must stay in FIPS scope.')
def _gcp():
    rows = HsmProvider.query.filter_by(type='google-kms').order_by(HsmProvider.id).all()
    return [_named(p.name, p.id) for p in rows]


_HSM_UNAPPROVED = ('ED25519', 'ED448', 'EDDSA', 'EDWARDS', 'CHACHA')


@detector('hsm.unapproved_keys', WARNING,
          'HSM keys of an algorithm outside FIPS mode (Ed25519, Ed448, ChaCha20-Poly1305)',
          'Replace them with RSA, ECDSA or AES keys; in FIPS mode, OpenBao and Vault Transit '
          'keys of these types are no longer listed.')
def _hsm_keys():
    # Only algorithms known to be refused: UNKNOWN or provider-specific types stay out.
    rows = HsmKey.query.with_entities(HsmKey.id, HsmKey.label, HsmKey.algorithm).order_by(HsmKey.id)
    return [_named(r.label, r.id, r.algorithm) for r in rows.all()
            if any(word in str(r.algorithm or '').upper() for word in _HSM_UNAPPROVED)]


@detector('dns.tsig_hmac_md5', BLOCKER,
          'RFC 2136 DNS providers signing with TSIG hmac-md5: DNS-01 updates are refused in FIPS mode',
          'Create an hmac-sha256 TSIG key on the DNS server and enter it in the provider.')
def _tsig_md5():
    found = []
    for provider in DnsProvider.query.filter_by(provider_type='rfc2136').order_by(DnsProvider.id).all():
        try:
            credentials = json.loads(provider.credentials or '{}')
        except (TypeError, ValueError):
            continue
        if isinstance(credentials, dict) and \
                str(credentials.get('tsig_algorithm') or '').strip().lower() == 'hmac-md5':
            found.append(_named(provider.name, provider.id))
    return found


@detector('msca.winrm_ntlm', BLOCKER,
          'Microsoft CA connections whose WinRM channel uses NTLM: the channel is refused in FIPS mode',
          'Switch the WinRM transport of these connections to Kerberos.')
def _msca_ntlm():
    rows = MicrosoftCA.query.filter(MicrosoftCA.winrm_enabled.is_(True)).order_by(MicrosoftCA.id).all()
    return [_named(m.name, m.id) for m in rows
            if (m.winrm_transport or 'kerberos').strip().lower() != 'kerberos']


@detector('backup.schedule_argon2id', WARNING,
          'Scheduled backups are written with Argon2id: such archives cannot be restored in FIPS mode',
          'Set the scheduled backup KDF to PBKDF2, and take a manual backup with kdf "pbkdf2" '
          'before the switch.')
def _backup_schedule():
    rows = {r.key: r.value for r in SystemConfig.query.filter(
        SystemConfig.key.in_(('auto_backup_enabled', 'backup_kdf'))).all()}
    if rows.get('auto_backup_enabled') != 'true':
        return []
    kdf = scheduled_kdf(rows.get('backup_kdf'))
    if kdf == 'argon2id' or (kdf is None and _ARGON2_AVAILABLE):
        return [f'kdf: {kdf or "auto (Argon2id)"}']
    return []


@detector('backup.archives_argon2id', WARNING,
          'Backup archives on disk encrypted with Argon2id: they cannot be restored in FIPS mode',
          'Keep them for a standard instance, and take a manual backup with kdf "pbkdf2" '
          'before the switch.')
def _backup_archives():
    found = []
    for path in sorted(_existing_archives()):
        try:
            with open(path, 'rb') as handle:
                head = handle.read(container.HEADER_PREFIX_SIZE)
        except OSError:
            continue
        if head[:4] == container.MAGIC and len(head) > 6 and head[6] == container.KDF_ARGON2ID:
            found.append(os.path.basename(path))
    return found


@detector('database.postgres_without_tls', BLOCKER,
          'The PostgreSQL connection runs over TCP without sslmode=require or stricter: '
          'UCM refuses to start in FIPS mode',
          'Enable TLS on the server and add sslmode=require (or verify-full) to DATABASE_URL.')
def _database():
    problem = postgres_tls_problem(current_app.config.get('SQLALCHEMY_DATABASE_URI') or '')
    return [f'DATABASE_URL: {problem}'] if problem else []


@detector('https.unapproved_key', BLOCKER,
          'The HTTPS certificate has an Ed25519/Ed448 or weak key: the web server cannot use it in FIPS mode',
          'Install an RSA 2048+ or ECDSA P-256/P-384/P-521 certificate in the HTTPS settings.')
def _https():
    path = current_app.config.get('HTTPS_CERT_PATH')
    if not path or not os.path.isfile(str(path)):
        return []
    try:
        with open(str(path), 'rb') as handle:
            cert = x509.load_pem_x509_certificate(handle.read())
    except (OSError, ValueError):
        return []
    name, approved = certificate_key(cert)
    return [] if approved else [f'{os.path.basename(str(path))}: {name}']


# --- run --------------------------------------------------------------------

def run(detectors: Optional[Iterable[Detector]] = None) -> dict:
    """Every detector's findings, blockers first; a detector that fails is listed in errors."""
    findings, errors, checked = [], [], []
    for item in detectors if detectors is not None else DETECTORS:
        checked.append(item.id)
        try:
            names = item.find()
        except Exception as exc:
            logger.warning('FIPS preflight check %s failed: %s', item.id, exc)
            db.session.rollback()
            errors.append({'id': item.id, 'error': f'{type(exc).__name__}: {exc}'[:300]})
            continue
        if names:
            findings.append({'id': item.id, 'severity': item.severity, 'title': item.title,
                             'count': len(names), 'examples': names[:MAX_EXAMPLES],
                             'remedy': item.remedy})
    findings.sort(key=lambda f: SEVERITIES.index(f['severity']))
    summary = {s: sum(1 for f in findings if f['severity'] == s) for s in SEVERITIES}
    return {'fips_active': fips_mode.enabled(), 'ready': not summary[BLOCKER] and not errors,
            'summary': summary, 'findings': findings, 'errors': errors, 'checked': checked}
