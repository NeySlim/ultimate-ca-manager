"""FIPS readiness: what a standard instance holds that FIPS mode will refuse.

Every detector reads, none writes. Key types come from stored types and
encodings (certificate SPKI, OpenSSH type names), never from loading a
private key: an EdDSA key fails to load on a FIPS provider without EdDSA.
EdDSA and ML-DSA count as approved only when the module FIPS mode runs on approves
them (fips_mode.switch_approves: before the switch, the -fips image's module as queried
at build; elsewhere none, so they are listed). On an HSM they never count: it signs
outside the module, so only RSA 2048+ and NIST curves pass there.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import warnings
from typing import Iterable, List, Optional, Tuple

from cryptography import x509
from cryptography.utils import CryptographyDeprecationWarning
from flask import current_app

import fips_mode
from models import (CA, Certificate, CertificatePolicy, CertificateTemplate, DeployTarget,
                    DnsProvider, AcmeClientOrder, HsmKey, HsmProvider, MicrosoftCA,
                    SSHCertificate, SSHCertificateAuthority, SystemConfig, User)
from security import encryption
from security.encryption import decrypt_text
from services.backup import container
from services.backup.backup_service import _ARGON2_AVAILABLE
from services.backup.schedule import _existing_archives
from services.backup.settings_contract import scheduled_kdf
from services.compliance_signer import softhsm_provider
from services.preflight_core import (BLOCKER, INFO, MAX_EXAMPLES, SEVERITIES, WARNING,  # noqa: F401
                                     Detector, registry_detector,
                                     run_detectors)
from services.tsa_service import tsa_is_enabled
from utils import key_algorithms
from utils.datetime_utils import utc_now
from utils.db_url import postgres_gssenc_problem, postgres_tls_problem
from utils.key_codec import eddsa_key_name

logger = logging.getLogger(__name__)

_EDDSA_OIDS = {'1.3.101.112': 'Ed25519', '1.3.101.113': 'Ed448'}

DETECTORS: List[Detector] = []
detector = registry_detector(DETECTORS)


# --- key helpers ------------------------------------------------------------

def stored_label_approved(text) -> bool:
    """Whether a stored key spelling ('RSA 1024', 'EC-P256', 'Ed25519') is FIPS approved."""
    if not text:
        return False
    alg = key_algorithms.get(text)
    if alg is not None:
        return alg.fips_static or (alg.fips_by_module and fips_mode.switch_approves(alg.label))
    match = re.fullmatch(r'\s*RSA[\s:_-]*(\d+)\s*', str(text), re.IGNORECASE)
    return bool(match) and int(match.group(1)) >= 2048


def certificate_key(cert) -> Tuple[str, bool]:
    """(display, approved) of a certificate's or CSR's key; EdDSA and post-quantum
    keys are told by their OID, unloaded."""
    oid = cert.public_key_algorithm_oid.dotted_string
    if oid in _EDDSA_OIDS:
        return _EDDSA_OIDS[oid], fips_mode.switch_approves(_EDDSA_OIDS[oid])
    post_quantum = key_algorithms.post_quantum_info(oid)
    if post_quantum is not None:
        # SLH-DSA stays unapproved: pyca cannot load it, whatever the module approves
        approved = post_quantum.family == 'ML-DSA' and fips_mode.switch_approves(post_quantum.label)
        return post_quantum.label, approved
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
    from models import WindowsEnrollmentProfile
    row = SystemConfig.query.filter_by(key='est_password').first()
    found = {'EST'} if row is not None and (row.value or '').startswith('scrypt:') else set()
    for profile in WindowsEnrollmentProfile.query.all():
        for label, value in (('WSTEP', profile.wstep_password), ('XCEP', profile.xcep_password)):
            if (value or '').startswith('scrypt:'):
                found.add(label)
    return sorted(found)


def _ca_keys():
    for ca in CA.query.with_entities(CA.id, CA.descr, CA.crt, CA.hsm_key_id).order_by(CA.id).all():
        cert = load_stored_certificate(ca.crt)
        if cert is None:
            continue
        name, approved = certificate_key(cert)
        # An HSM signs outside the module: what only the module approves stays unapproved there
        registered = key_algorithms.get(name)
        if ca.hsm_key_id and registered is not None and registered.fips_by_module:
            approved = False
        yield ca, (name, approved)


@detector('ca.eddsa_key', BLOCKER,
          'Certificate authorities with an Ed25519 or Ed448 key: they cannot sign in FIPS mode '
          'on an HSM, or on a module that does not approve EdDSA',
          'Create an RSA or ECDSA (P-256/P-384/P-521) authority and move issuance to it '
          'before the switch; an authority key cannot be converted.')
def _ca_eddsa():
    return [_named(ca.descr, ca.id, name) for ca, (name, approved) in _ca_keys()
            if name in _EDDSA_OIDS.values() and not approved]


def _is_mldsa(name) -> bool:
    # Named whether or not this build can use ML-DSA: the registry holds it only when it can
    info = key_algorithms.post_quantum_info(name)
    return info is not None and info.family == 'ML-DSA'


@detector('ca.weak_key', BLOCKER,
          'Certificate authorities with a DSA key, RSA under 2048 bits or a curve other than P-256/384/521',
          'Create an authority with RSA 2048+ or ECDSA P-256/P-384/P-521 and move issuance to it.')
def _ca_weak():
    return [_named(ca.descr, ca.id, name) for ca, (name, approved) in _ca_keys()
            if not approved and name not in _EDDSA_OIDS.values() and not _is_mldsa(name)]


@detector('ca.unapproved_algorithm', BLOCKER,
          'Certificate authorities with an ML-DSA key: they cannot sign in FIPS mode on an HSM, '
          'or on a module that does not approve ML-DSA',
          'Create an RSA 2048+ or ECDSA P-256/P-384/P-521 authority and move issuance to it '
          'before the switch, or keep FIPS mode off while ML-DSA issuance is needed.')
def _ca_unapproved_algorithm():
    return [_named(ca.descr, ca.id, name) for ca, (name, approved) in _ca_keys()
            if _is_mldsa(name) and not approved]


def _ssh_eddsa(key_type, public_key) -> Optional[str]:
    """'Ed25519' or 'Ed448' for an SSH key the loaded module does not approve, else None."""
    if str(key_type or '').lower() in ('ed25519', 'ed448'):
        name = 'Ed25519' if str(key_type).lower() == 'ed25519' else 'Ed448'
    else:
        name = eddsa_key_name(public_key)
    return None if name is None or fips_mode.switch_approves(name) else name


@detector('ssh_ca.eddsa_key', BLOCKER,
          'SSH certificate authorities with an Ed25519 key: they cannot sign in FIPS mode '
          'on a module that does not approve EdDSA',
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
    return [_named(r.key_id, r.id) for r in rows if _ssh_cert_key_refused(r.key_type)]


def _ssh_cert_key_refused(key_type) -> bool:
    """Whether an SSH certificate's stored key type ('ed25519') is EdDSA the module does not approve."""
    text = str(key_type or '').lower()
    if not text.startswith('ed'):
        return False
    return not fips_mode.switch_approves('ED448' if '448' in text else 'ED25519')


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


@detector('deploy.ssh_eddsa_host_key', BLOCKER,
          'Deployment targets pinned to an Ed25519 host key: deployments fail in FIPS mode '
          'until the pin is reset',
          'Make sure each host also has an ECDSA or RSA host key, then reset the pinned host key '
          'of the target: the next connection pins that key.')
def _deploy_eddsa_host_key():
    rows = DeployTarget.query.with_entities(DeployTarget.id, DeployTarget.name, DeployTarget.host_key)
    return [_named(r.name, r.id) for r in rows.order_by(DeployTarget.id).all()
            if str(r.host_key or '').startswith('ssh-ed25519 ')]


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
          'Delegated OCSP responders with an Ed25519/Ed448, ML-DSA or weak key: the CA signs instead',
          'Issue a new RSA or ECDSA responder certificate and select it in the CA settings.')
def _ocsp_responders():
    found = []
    for _row, cert in _configured_certificate('ocsp_responder_cert_', 'id'):
        name, approved = _stored_cert_key(cert.key_algo, cert.crt)
        if not approved:
            found.append(_named(cert.descr or cert.subject_cn, cert.id, name))
    return found


@detector('tsa.signer_unapproved_key', BLOCKER,
          'The timestamping certificate has an Ed25519/Ed448, ML-DSA or weak key: timestamps fail in FIPS mode',
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
          'Active certificates with an Ed25519/Ed448 or ML-DSA key, RSA under 2048 bits or another curve',
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
          'Active policies that allow key types FIPS mode removes (Ed25519, Ed448, ML-DSA, short RSA...)',
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


def _csr_unapproved_key(csr_pem) -> Optional[str]:
    try:
        csr = x509.load_pem_x509_csr(csr_pem.encode() if isinstance(csr_pem, str) else csr_pem)
    except Exception:
        return None
    name, approved = certificate_key(csr)
    return None if approved else name


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
            name = _csr_unapproved_key(order.csr_pem)
        elif order.key_type and not stored_label_approved(order.key_type):
            name = order.key_type
        if name:
            found.append(_named(order.primary_domain, order.id, name))
    return found


@detector('hsm.softhsm', WARNING,
          'SoftHSM providers: SoftHSM is not a validated module, keys on it are not FIPS protected',
          'Move the keys to a validated HSM, or accept SoftHSM as a test setup only.')
def _softhsm():
    rows = HsmProvider.query.filter_by(type='pkcs11').order_by(HsmProvider.id).all()
    return [_named(p.name, p.id) for p in rows if softhsm_provider(p)]


@detector('hsm.gcp_grpc', WARNING,
          'Google Cloud KMS providers: their client uses gRPC with its own TLS, outside the FIPS module',
          'Prefer a PKCS#11, Azure Key Vault or OpenBao provider for keys that must stay in FIPS scope.')
def _gcp():
    rows = HsmProvider.query.filter_by(type='google-kms').order_by(HsmProvider.id).all()
    return [_named(p.name, p.id) for p in rows]


# HSM keys sign outside the loaded module: EdDSA, ML-DSA and Brainpool stay refused whatever it approves
_HSM_UNAPPROVED = ('ED25519', 'ED448', 'EDDSA', 'EDWARDS', 'ML-DSA', 'EC-BP', 'BRAINPOOL', 'CHACHA')


def _hsm_unapproved_words():
    return _HSM_UNAPPROVED


@detector('hsm.unapproved_keys', WARNING,
          'HSM keys of an algorithm outside FIPS mode (Ed25519, Ed448, ML-DSA, Brainpool, ChaCha20-Poly1305)',
          'Replace them with RSA, ECDSA or AES keys; in FIPS mode, OpenBao and Vault Transit '
          'keys of these types are no longer listed.')
def _hsm_keys():
    # Only algorithms known to be refused: UNKNOWN or provider-specific types stay out.
    rows = HsmKey.query.with_entities(HsmKey.id, HsmKey.label, HsmKey.algorithm).order_by(HsmKey.id)
    words = _hsm_unapproved_words()
    return [_named(r.label, r.id, r.algorithm) for r in rows.all()
            if any(word in str(r.algorithm or '').upper() for word in words)]


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


def _short_tsig_secret(text) -> bool:
    try:
        secret = base64.b64decode(str(text or '').strip(), validate=True)
    except ValueError:
        return False
    return 0 < len(secret) < fips_mode.MIN_HMAC_KEY_BYTES


@detector('hmac.short_secret', WARNING,
          'Webhook secrets or RFC 2136 TSIG keys under 14 bytes: the FIPS module does not approve '
          'HMAC keys this short, and FIPS mode refuses to save them',
          'Regenerate the webhook secrets and create TSIG keys of at least 14 bytes '
          '(hmac-sha256 keys of 32 bytes are the usual size), then update the receivers and DNS servers.')
def _short_hmac_secrets():
    from services.webhook_service import WebhookEndpoint
    from utils.encryption import decrypt_if_needed
    found = []
    for endpoint in WebhookEndpoint.query.order_by(WebhookEndpoint.id).all():
        try:
            secret = decrypt_if_needed(endpoint.secret) if endpoint.secret else ''
        except Exception:
            continue
        if secret and len(secret.encode()) < fips_mode.MIN_HMAC_KEY_BYTES:
            found.append(_named(endpoint.name, endpoint.id, 'webhook secret'))
    for provider in DnsProvider.query.filter_by(provider_type='rfc2136').order_by(DnsProvider.id).all():
        try:
            credentials = json.loads(provider.credentials or '{}')
        except (TypeError, ValueError):
            continue
        if isinstance(credentials, dict) and _short_tsig_secret(credentials.get('tsig_key_secret')):
            found.append(_named(provider.name, provider.id, 'TSIG key'))
    return found


@detector('msca.winrm_ntlm', BLOCKER,
          'Microsoft CA connections whose WinRM channel uses NTLM: the channel is refused in FIPS mode',
          'Turn off the WinRM channel of these connections. Kerberos replaces NTLM only on a '
          'native install with pywinrm[kerberos] and a Kerberos library built on the system '
          'OpenSSL (RHEL); the Docker image has neither.')
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
          'Enable TLS on the server and add sslmode=require (or verify-full) to DATABASE_URL; '
          'for a server on the same host, connect through its Unix socket instead: '
          'postgresql://ucm:<password>@/ucm?host=/var/run/postgresql')
def _database():
    problem = postgres_tls_problem(current_app.config.get('SQLALCHEMY_DATABASE_URI') or '')
    return [f'DATABASE_URL: {problem}'] if problem else []


@detector('database.postgres_gssenc', BLOCKER,
          'PostgreSQL is set to use GSSAPI encryption, which runs in the Kerberos library '
          'outside the FIPS module: UCM refuses to start in FIPS mode',
          'Remove gssencmode from DATABASE_URL and PGGSSENCMODE from the environment, or set '
          'them to disable: TLS then protects the connection.')
def _database_gssenc():
    problem = postgres_gssenc_problem(current_app.config.get('SQLALCHEMY_DATABASE_URI') or '')
    return [f'DATABASE_URL: {problem}'] if problem else []


@detector('keys.no_master_key', WARNING,
          'Private keys are stored unencrypted (no master key, or encryption disabled)',
          'Enable private key encryption in Settings > Security, or provide '
          '/etc/ucm/master.key or KEY_ENCRYPTION_KEY; with UCM_REQUIRE_KEY_ENCRYPTION=true, '
          'UCM then refuses to start without one.')
def _no_master_key():
    from security.dek_rotation import shown_as_enabled
    # As the encryption status: a disable in its grace keeps its DEKs but encrypts nothing
    if shown_as_enabled():
        return []
    return [f'{encryption.MASTER_KEY_PATH}, KEY_ENCRYPTION_KEY']


@detector('https.unapproved_key', BLOCKER,
          'The HTTPS certificate has an Ed25519/Ed448, ML-DSA or weak key: the web server cannot use it in FIPS mode',
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
    result = run_detectors(DETECTORS if detectors is None else detectors, label='FIPS preflight')
    return {'fips_active': fips_mode.enabled(),
            'ready': not result['summary'][BLOCKER] and not result['errors'],
            'summary': result['summary'], 'findings': result['findings'],
            'errors': result['errors'], 'checked': result['checked']}
