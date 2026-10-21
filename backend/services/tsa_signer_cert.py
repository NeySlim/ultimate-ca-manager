"""One-click issuance of a dedicated RFC 3161 TSA signing certificate (#312).

The generic issue path (`api/v2/certificates/cert_create.py`) always emits the
EKU extension non-critical and merges the base profile with `extra_ekus`, so it
can never produce the critical, *exclusive* `timeStamping` EKU that RFC 3161 §2.3
wants. This helper builds the certificate's extensions itself:

- BasicConstraints CA:FALSE, critical
- KeyUsage = digitalSignature only, critical
- ExtendedKeyUsage = [id-kp-timeStamping] only, **critical**

The issued certificate is an ordinary UCM end-entity certificate
(`source='manual'`, key stored encrypted at rest) so it flows through the same
`tsa_signer_cert_refid` resolution, expiry checks and in-place renewal as any
operator-selected signer (`services/tsa_service.py`). Renewal copies extensions
across verbatim (`services/cert/renewal.py`), so a renewed signer keeps the
critical exclusive EKU.
"""
import base64
import json
import logging
import uuid
from datetime import timedelta

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.oid import ExtendedKeyUsageOID, ExtensionOID, NameOID

from models import Certificate, db
from services.trust_store.constraints_mixin import validate_name_constraints
from utils.datetime_utils import cert_not_before, utc_now
from utils.db_transaction import safe_commit
from utils import key_algorithms
from utils.key_type import parse_issue_key_type
from utils.key_codec import private_key_to_pem

logger = logging.getLogger(__name__)

DEFAULT_CN = 'UCM Timestamping Authority'
DEFAULT_VALIDITY_DAYS = 397
DEFAULT_KEY_TYPE = 'rsa'
DEFAULT_KEY_SIZE = '3072'
from utils.validity import MAX_VALIDITY_DAYS  # noqa: F401  (re-exported here)

from security.encryption import encrypt_private_key


from utils.x509_aki import authority_key_identifier_from_issuer


class TsaSignerIssueError(Exception):
    """Issuance was refused. ``status`` is the HTTP status the API should surface."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def _generate_key(key_type, key_size, curve):
    # With neither curve nor size, the RSA default size would be parsed as a curve.
    if str(key_type or '').strip().lower() in ('ec', 'ecdsa') and not key_size and not curve:
        raise TsaSignerIssueError(
            'An EC key needs a curve: pass curve (P-256, P-384 or P-521)', 400)
    try:
        normalized = parse_issue_key_type(key_type or DEFAULT_KEY_TYPE,
                                          key_size or DEFAULT_KEY_SIZE,
                                          curve=curve)
    except ValueError as exc:
        raise TsaSignerIssueError(str(exc), 400)
    return key_algorithms.generate(normalized)


def _key_algo_label(public_key) -> str:
    from utils.key_algorithms import key_algo_for_public_key
    return key_algo_for_public_key(public_key)


from utils.ca_pointer_extensions import add_ca_pointer_extensions as _copy_ca_pointer_extensions
from utils.signing_hash import rsa_padding_for


def issue_tsa_signer_certificate(*, ca, cn=None, validity_days=None,
                                 key_type=None, key_size=None, curve=None,
                                 actor='system', actor_user_id=None) -> Certificate:
    """Issue and persist a dedicated RFC 3161 timestamp signing certificate.

    Raises TsaSignerIssueError on any refusal. On success the committed
    Certificate row is returned; the caller decides whether to select it as
    ``tsa_signer_cert_refid``.
    """
    if not ca:
        raise TsaSignerIssueError('An issuing CA is required', 400)
    if not ca.has_private_key:
        raise TsaSignerIssueError('CA private key not available', 400)
    if not ca.crt:
        raise TsaSignerIssueError('CA is awaiting its certificate', 400)
    if ca.offline:
        raise TsaSignerIssueError('CA is offline; restore it before issuing', 400)
    if ca.revoked_in_chain:
        raise TsaSignerIssueError('CA is revoked and can no longer issue certificates', 400)

    if cn is not None and not isinstance(cn, str):
        raise TsaSignerIssueError('cn must be a string', 400)
    cn = (cn or DEFAULT_CN).strip() or DEFAULT_CN

    try:
        raw_validity = int(validity_days) if validity_days not in (None, '') \
            else DEFAULT_VALIDITY_DAYS
    except (TypeError, ValueError):
        raise TsaSignerIssueError('validity_days must be an integer', 400)
    if raw_validity < 1:
        raise TsaSignerIssueError('validity_days must be positive', 400)
    validity_days = min(raw_validity, MAX_VALIDITY_DAYS)

    ca_cert = x509.load_pem_x509_certificate(
        base64.b64decode(ca.crt), default_backend())
    now = utc_now()
    not_before = cert_not_before()
    from utils.ca_signing_window import check_issuer_window, clamp_not_after
    try:
        # Refused before the CA key is loaded (HSM included) or a key generated
        check_issuer_window(ca_cert, now)
    except ValueError as exc:
        raise TsaSignerIssueError(str(exc), 400)
    from services.hsm.ca_key_loader import get_ca_signing_key
    from fips_mode import FipsRestricted
    try:
        ca_key = get_ca_signing_key(ca)
    except FipsRestricted:
        raise
    except ValueError as exc:
        raise TsaSignerIssueError(f'Failed to load CA signing key: {exc}', 500)

    new_key = _generate_key(key_type, key_size, curve)
    # The operator did not choose the validity in the one-click flow, so clamp
    # to the CA's own expiry instead of refusing (cert_create.py 400s here).
    not_after = clamp_not_after(now + timedelta(days=validity_days), ca_cert)

    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    try:
        validate_name_constraints(ca_cert, subject, None)
    except ValueError as exc:
        raise TsaSignerIssueError(f'Rejected by CA name constraints: {exc}', 400)

    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(new_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=False,
                key_encipherment=False, data_encipherment=False,
                key_agreement=False, key_cert_sign=False, crl_sign=False,
                encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        # The deliberate deviation from cert_create.py: RFC 3161 §2.3 wants the
        # timeStamping EKU critical and exclusive.
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(new_key.public_key()),
            critical=False,
        )
        .add_extension(
            authority_key_identifier_from_issuer(ca_cert),
            critical=False,
        )
    )
    builder = _copy_ca_pointer_extensions(builder, ca)

    # SHA-256 by default, matching cert_create.py's non-template path. Follow the
    # CA certificate's own signature hash when it is stronger, so a SHA-384/512
    # CA does not get a weaker-signed child.
    sign_hash = hashes.SHA256()
    try:
        ca_sig_hash = ca_cert.signature_hash_algorithm
        if isinstance(ca_sig_hash, (hashes.SHA384, hashes.SHA512)):
            sign_hash = ca_sig_hash
    except Exception:
        pass
    # Issuance policies (#397): that default yields to the digests they allow
    from services.policy_service import PolicyEvaluationService, key_label_for_public_key
    sign_hash, violations = PolicyEvaluationService.checked_signing_hash(
        PolicyEvaluationService.applicable_policies(ca.id, None, cn),
        ca_key, sign_hash.name, explicit=False,
        key_type=key_label_for_public_key(new_key.public_key()),
        not_after=not_after.date(), tsa_signer=True,
        context={'operation': 'issuance', 'subject': cn, 'ca_id': ca.id})
    if violations:
        raise TsaSignerIssueError('Policy violation: ' + '; '.join(violations), 400)
    new_cert = builder.sign(ca_key, sign_hash, default_backend(),
                            rsa_padding=rsa_padding_for(ca_key, sign_hash))

    cert_pem = new_cert.public_bytes(serialization.Encoding.PEM).decode('utf-8')
    key_pem = private_key_to_pem(new_key).decode('utf-8')

    ski = aki = None
    try:
        ski = new_cert.extensions.get_extension_for_oid(
            ExtensionOID.SUBJECT_KEY_IDENTIFIER
        ).value.key_identifier.hex(':').upper()
    except Exception:
        pass
    try:
        ext = new_cert.extensions.get_extension_for_oid(
            ExtensionOID.AUTHORITY_KEY_IDENTIFIER)
        if ext.value.key_identifier:
            aki = ext.value.key_identifier.hex(':').upper()
    except Exception:
        pass

    db_cert = Certificate(
        refid=str(uuid.uuid4())[:8],
        descr=cn,
        caref=ca.refid,
        crt=base64.b64encode(cert_pem.encode()).decode(),
        # Encrypt the key at rest, exactly as renewal.py does at re-issuance;
        # storing it in the clear would silently downgrade an encrypted deployment.
        prv=encrypt_private_key(base64.b64encode(key_pem.encode()).decode()),
        cert_type='timestamping',
        source='manual',
        private_key_location='stored',
        subject=new_cert.subject.rfc4514_string(),
        subject_cn=cn,
        issuer=new_cert.issuer.rfc4514_string(),
        serial_number=format(new_cert.serial_number, 'x'),
        aki=aki,
        ski=ski,
        valid_from=not_before,
        valid_to=not_after,
        key_algo=_key_algo_label(new_key.public_key()),
        san_dns=json.dumps([]),
        san_ip=json.dumps([]),
        san_email=json.dumps([]),
        san_uri=json.dumps([]),
        created_by=actor,
    )
    db.session.add(db_cert)
    ok, _err = safe_commit(logger, 'Failed to persist TSA signer certificate')
    if not ok:
        raise TsaSignerIssueError('Failed to persist TSA signer certificate', 500)

    try:
        from services.audit_service import AuditService
        AuditService.log_action(
            action='tsa_signer_cert_issued',
            resource_type='certificate',
            resource_id=str(db_cert.id),
            resource_name=cn,
            details=(f'Issued dedicated RFC 3161 TSA signing certificate from '
                     f'CA {ca.refid} (serial {db_cert.serial_number}, '
                     f'valid to {not_after.isoformat()})'),
            user_id=actor_user_id,
        )
    except Exception:
        pass

    cert_dict = db_cert.to_dict()
    try:
        from services.webhook_service import emit_cert_issued
        emit_cert_issued(cert_dict, ca_refid=ca.refid, actor=actor)
    except Exception as exc:
        logger.warning(f'Failed to emit cert_issued for TSA signer: {exc}')

    logger.info(
        f'Issued TSA signing certificate {db_cert.refid} (CN={cn}) from CA '
        f'{ca.refid}, valid to {not_after.isoformat()}'
    )
    return db_cert
