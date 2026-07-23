"""
Delegated OCSP Responder Auto-Renewal
Re-issues delegated OCSP responder certificates before they expire and
rebinds the responder configuration to the renewed certificate, so a
short-lived (e.g. 90-day) OCSP signing certificate rotates without manual
action (issue #226 follow-up).

The renewal reuses the responder's existing key pair and copies the old
certificate's extensions verbatim (KU, OCSPSigning EKU, id-pkix-ocsp-nocheck),
so the renewed certificate always passes the delegated-responder checks in
OCSPService._get_delegated_responder.
"""
import base64
import logging
import uuid
from datetime import timedelta

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed448, ed25519
from cryptography.x509.oid import ExtensionOID

from models import CA, AuditLog, Certificate, SystemConfig, db
from utils.datetime_utils import cert_not_before, utc_now
from utils.key_codec import load_pem_bytes

logger = logging.getLogger(__name__)

RESPONDER_KEY_PREFIX = 'ocsp_responder_cert_'
DEFAULT_RENEW_DAYS = 30


def _get_config(key, default=None):
    row = SystemConfig.query.filter_by(key=key).first()
    return row.value if row else default


def _renew_threshold_days(lifetime_days: int) -> int:
    """Days-before-expiry threshold, bounded so short-lived responders don't
    renew immediately after issuance (never earlier than 1/3 of lifetime left).
    """
    try:
        configured = int(_get_config('ocsp_responder_renew_days', DEFAULT_RENEW_DAYS))
    except (TypeError, ValueError):
        configured = DEFAULT_RENEW_DAYS
    return max(1, min(configured, max(1, lifetime_days // 3)))


def _renew_responder_cert(ca: CA, cert: Certificate):
    """Re-issue *cert* with the same key pair and extensions, signed by *ca*.

    Returns the new Certificate row (committed) or raises.
    """
    old_cert = x509.load_pem_x509_certificate(
        base64.b64decode(cert.crt), default_backend()
    )
    key_pem = load_pem_bytes(cert.prv, context=f"certificate {cert.id}")
    private_key = serialization.load_pem_private_key(
        key_pem, password=None, backend=default_backend()
    )

    ca_cert = x509.load_pem_x509_certificate(
        base64.b64decode(ca.crt), default_backend()
    )
    from services.hsm.ca_key_loader import get_ca_signing_key
    ca_key = get_ca_signing_key(ca)

    lifetime_days = max(1, (cert.valid_to - cert.valid_from).days) \
        if cert.valid_from and cert.valid_to else 90

    not_before = cert_not_before()
    not_after = utc_now() + timedelta(days=lifetime_days)
    ca_not_after = ca_cert.not_valid_after_utc.replace(tzinfo=None)
    if not_after > ca_not_after:
        not_after = ca_not_after

    builder = (
        x509.CertificateBuilder()
        .subject_name(old_cert.subject)
        .issuer_name(ca_cert.subject)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
    )

    # Copy extensions verbatim (same key => same SKI); the AKI is rebuilt from
    # the CA certificate in case the CA was re-keyed since original issuance.
    for ext in old_cert.extensions:
        if ext.oid == ExtensionOID.AUTHORITY_KEY_IDENTIFIER:
            continue
        builder = builder.add_extension(ext.value, critical=ext.critical)
    builder = builder.add_extension(
        x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_cert.public_key()),
        critical=False,
    )

    if isinstance(ca_key, (ed25519.Ed25519PrivateKey, ed448.Ed448PrivateKey)):
        new_cert = builder.sign(ca_key, None, default_backend())
    else:
        new_cert = builder.sign(ca_key, hashes.SHA256(), default_backend())

    cert_pem = new_cert.public_bytes(serialization.Encoding.PEM).decode()

    db_cert = Certificate(
        refid=str(uuid.uuid4())[:8],
        descr=cert.descr,
        caref=ca.refid,
        crt=base64.b64encode(cert_pem.encode()).decode(),
        prv=cert.prv,  # same key pair, same stored (possibly encrypted) form
        cert_type=cert.cert_type,
        subject=new_cert.subject.rfc4514_string(),
        subject_cn=cert.subject_cn,
        issuer=new_cert.issuer.rfc4514_string(),
        serial_number=str(new_cert.serial_number),
        aki=cert.aki,
        ski=cert.ski,
        key_algo=cert.key_algo,
        valid_from=not_before,
        valid_to=not_after,
        source=cert.source,
        template_id=cert.template_id,
        created_by='system:ocsp-renewal',
    )
    db.session.add(db_cert)
    db.session.flush()  # need the new id to rebind the responder pointer
    return db_cert


def run_ocsp_responder_renewal():
    """Scheduled task: renew delegated OCSP responder certs nearing expiry."""
    if _get_config('ocsp_responder_auto_renew', 'true') != 'true':
        logger.debug("OCSP responder auto-renewal is disabled")
        return {'renewed': 0, 'failed': 0, 'skipped': 0}

    stats = {'renewed': 0, 'failed': 0, 'skipped': 0}

    bindings = SystemConfig.query.filter(
        SystemConfig.key.like(f'{RESPONDER_KEY_PREFIX}%')
    ).all()

    for binding in bindings:
        try:
            ca_id = int(binding.key[len(RESPONDER_KEY_PREFIX):])
            cert_id = int(binding.value)
        except (TypeError, ValueError):
            stats['skipped'] += 1
            continue

        cert = db.session.get(Certificate, cert_id)
        if not cert or not cert.crt or not cert.prv or cert.revoked:
            stats['skipped'] += 1
            continue

        if not cert.valid_to:
            stats['skipped'] += 1
            continue

        lifetime_days = max(1, (cert.valid_to - cert.valid_from).days) \
            if cert.valid_from else 90
        threshold = utc_now() + timedelta(days=_renew_threshold_days(lifetime_days))
        # An already-expired responder is renewed too: same-key re-issuance is
        # safe and restores OCSP service instead of leaving it degraded.
        if cert.valid_to > threshold:
            stats['skipped'] += 1
            continue

        ca = db.session.get(CA, ca_id)
        if not ca or not ca.crt or not ca.has_private_key or ca.offline:
            logger.warning(
                "OCSP responder renewal: CA %s unavailable for cert %s; skipping",
                ca_id, cert_id,
            )
            stats['skipped'] += 1
            continue

        try:
            new_row = _renew_responder_cert(ca, cert)
            binding.value = str(new_row.id)
            cert.archived = True
            db.session.add(AuditLog(
                action='ocsp_responder.auto_renewed',
                resource_type='ca',
                resource_id=ca_id,
                resource_name=ca.descr,
                details=(
                    f'Delegated OCSP responder cert {cert.id} renewed as '
                    f'{new_row.id} (valid to {new_row.valid_to})'
                ),
            ))
            db.session.commit()
            stats['renewed'] += 1
            logger.info(
                "OCSP responder renewed for CA %s: cert %s -> %s",
                ca_id, cert.id, new_row.id,
            )
        except Exception as e:
            db.session.rollback()
            stats['failed'] += 1
            logger.error(
                "OCSP responder renewal failed for CA %s cert %s: %s",
                ca_id, cert_id, e, exc_info=True,
            )
            try:
                db.session.add(AuditLog(
                    action='ocsp_responder.auto_renewal_failed',
                    resource_type='ca',
                    resource_id=ca_id,
                    details=f'Delegated OCSP responder renewal failed: {e}',
                ))
                db.session.commit()
            except Exception:
                db.session.rollback()

    if stats['renewed'] or stats['failed']:
        logger.info(
            "OCSP responder renewal complete: %s renewed, %s failed, %s skipped",
            stats['renewed'], stats['failed'], stats['skipped'],
        )
    return stats
