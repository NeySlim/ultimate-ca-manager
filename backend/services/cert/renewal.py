"""Shared in-place certificate renewal.

One implementation, three callers:

- ``POST /api/v2/certificates/<id>/renew``      (api/v2/certificates/cert_renew.py)
- ``POST /api/v2/certificates/bulk/renew``      (api/v2/certificates/bulk.py)
- ``AutoRenewalService.renew_certificate``      (services/auto_renewal_service.py)

Every renewal therefore behaves identically:

1. the superseded serial is recorded in ``revoked_serials`` (reason
   ``superseded``) so it stays on the CRL and answers ``revoked`` over OCSP
   until the old notAfter passes,
2. the ``certificates`` row is updated **in place** — ``id``, ``refid`` and
   ``created_at`` never change, ``renewed_at`` / ``renewed_times`` are
   maintained,
3. the on-disk cert/key files, the OCSP response cache, the CRL, the audit
   trail and the ``cert_renewed`` webhook are all refreshed the same way.

The only intentional difference between callers is the key strategy:

``rekey=True``   UCM generates a fresh key pair matching the original's
                 algorithm and size. Used for certificates whose private key
                 UCM holds (manual and bulk renewal).
``rekey=False``  the existing public key is re-signed. Used for
                 protocol-enrolled certificates (SCEP / EST / ACME) where the
                 private key lives on the client and UCM has no way to deliver
                 a new one — issuing a fresh key pair there would hand the
                 device a certificate it cannot use.
"""
import base64
import json
import logging
from datetime import timedelta

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed448, ed25519, rsa
from cryptography.x509.oid import ExtensionOID

from models import CA, Certificate, RevokedSerial, db
from services.file_regen_service import mirror_private_key
from services.ocsp_service import OCSPService
from utils.datetime_utils import utc_now
from utils.db_transaction import commit_or_rollback
from utils.file_naming import cert_cert_path, cert_key_path
from utils.upn_san import extract_upns_from_san_list
from utils.key_codec import private_key_to_pem
from utils.eku_validation import add_ocsp_nocheck_if_responder

logger = logging.getLogger(__name__)

try:
    from security.encryption import encrypt_private_key
except ImportError:  # encryption module unavailable — store as-is
    def encrypt_private_key(data):
        return data


# Upper bound on a renewed certificate's lifetime, mirroring issuance.
MAX_RENEWAL_DAYS = 3650
DEFAULT_RENEWAL_DAYS = 365


from utils.signing_hash import signing_hash_for


class RenewalError(Exception):
    """Renewal could not be completed.

    ``status`` carries the HTTP status the API layer should surface; service
    callers can ignore it and just use ``message``.
    """

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def _cn_of(dn: str):
    """CN component of an RFC 4514 DN string, or None."""
    if not dn or 'CN=' not in dn:
        return None
    return dn.split('CN=')[1].split(',')[0]


def resolve_issuing_ca(cert: Certificate):
    """Find the CA that signed ``cert``: by refid, then subject, then CN."""
    ca = CA.query.filter_by(refid=cert.caref).first() if cert.caref else None
    if ca:
        return ca
    if not cert.issuer:
        return None

    ca = CA.query.filter(CA.subject == cert.issuer).first()
    if ca:
        return ca

    # Last resort: the issuer string may be formatted differently than the
    # CA's stored subject — compare Common Names only.
    cert_issuer_cn = _cn_of(cert.issuer)
    if not cert_issuer_cn:
        return None
    for potential_ca in CA.query.all():
        if potential_ca.subject and _cn_of(potential_ca.subject) == cert_issuer_cn:
            return potential_ca
    return None


def _generate_matching_key(orig_pub_key):
    """A fresh private key of the same algorithm/size as the original."""
    if isinstance(orig_pub_key, rsa.RSAPublicKey):
        return rsa.generate_private_key(
            public_exponent=65537,
            key_size=orig_pub_key.key_size,
            backend=default_backend(),
        )
    if isinstance(orig_pub_key, ec.EllipticCurvePublicKey):
        return ec.generate_private_key(orig_pub_key.curve, default_backend())
    if isinstance(orig_pub_key, ed25519.Ed25519PublicKey):
        return ed25519.Ed25519PrivateKey.generate()
    if isinstance(orig_pub_key, ed448.Ed448PublicKey):
        return ed448.Ed448PrivateKey.generate()
    return rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )


def _key_algo_label(public_key) -> str:
    if isinstance(public_key, rsa.RSAPublicKey):
        return f'RSA {public_key.key_size}'
    if isinstance(public_key, ec.EllipticCurvePublicKey):
        return f'EC {public_key.curve.name}'
    if isinstance(public_key, ed25519.Ed25519PublicKey):
        return 'Ed25519'
    if isinstance(public_key, ed448.Ed448PublicKey):
        return 'Ed448'
    return 'Unknown'


def _extract_sans(certificate: x509.Certificate) -> dict:
    """SAN lists keyed by column name, ready for the Certificate row.

    x509 GeneralName objects expose no ``.type`` attribute — the canonical
    discrimination is isinstance() (see utils/cert_extensions._parse_san).
    """
    dns, ips, emails, uris = [], [], [], []
    upns = []
    try:
        san_ext = certificate.extensions.get_extension_for_oid(
            ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        )
        entries = list(san_ext.value)
        for name in entries:
            if isinstance(name, x509.DNSName):
                dns.append(name.value)
            elif isinstance(name, x509.IPAddress):
                ips.append(str(name.value))
            elif isinstance(name, x509.RFC822Name):
                emails.append(name.value)
            elif isinstance(name, x509.UniformResourceIdentifier):
                uris.append(name.value)
        # OtherName UPNs are DER-encoded UTF8Strings — decode via the shared
        # helper instead of treating the DER blob as raw UTF-8.
        upns = extract_upns_from_san_list(entries)
    except x509.ExtensionNotFound:
        pass

    return {
        'san_dns': json.dumps(dns) if dns else None,
        'san_ip': json.dumps(ips) if ips else None,
        'san_email': json.dumps(emails) if emails else None,
        'san_uri': json.dumps(uris) if uris else None,
        'san_upn': json.dumps(upns) if upns else None,
    }


def _extract_key_ids(certificate: x509.Certificate):
    """(ski, aki) as colon-separated lowercase hex, or None."""
    try:
        ski_ext = certificate.extensions.get_extension_for_oid(
            ExtensionOID.SUBJECT_KEY_IDENTIFIER
        )
        ski = ':'.join(f'{b:02x}' for b in ski_ext.value.digest)
    except x509.ExtensionNotFound:
        ski = None
    try:
        aki_ext = certificate.extensions.get_extension_for_oid(
            ExtensionOID.AUTHORITY_KEY_IDENTIFIER
        )
        aki = (':'.join(f'{b:02x}' for b in aki_ext.value.key_identifier)
               if aki_ext.value.key_identifier else None)
    except x509.ExtensionNotFound:
        aki = None
    return ski, aki


def _record_superseded_serial(cert: Certificate, old_serial, old_caref,
                              old_valid_to, when):
    """Stage the previous serial in revoked_serials (reason: superseded).

    ``certificate_id`` is preserved so every previous serial keeps a direct
    link back to the certificate row; the CRL query distinguishes the current
    serial (good) from superseded ones by comparing serial numbers.

    Staged only — the caller commits it together with the in-place row update
    so the two can never diverge.
    """
    if not (old_caref and old_serial):
        return

    existing = RevokedSerial.query.filter_by(
        caref=old_caref, serial_number=old_serial
    ).first()
    fallback_valid_to = old_valid_to or (when + timedelta(days=DEFAULT_RENEWAL_DAYS))

    if existing:
        existing.revoked_at = when
        existing.revoke_reason = 'superseded'
        existing.valid_to = fallback_valid_to
        existing.certificate_id = cert.id
    else:
        db.session.add(RevokedSerial(
            caref=old_caref,
            serial_number=old_serial,
            revoked_at=when,
            revoke_reason='superseded',
            valid_to=fallback_valid_to,
            certificate_id=cert.id,
        ))


def _write_cert_files(cert: Certificate, cert_pem: str, key_pem):
    """Overwrite the on-disk cert/key. Filenames are refid-based, unchanged."""
    try:
        cert_path = cert_cert_path(cert)
        cert_path.parent.mkdir(parents=True, exist_ok=True)
        cert_path.write_bytes(cert_pem.encode())
        if key_pem:
            mirror_private_key(
                cert_key_path(cert),
                key_pem.encode(),
                context=f"renewed certificate {cert.id}",
            )
    except Exception as e:
        logger.warning(f"Failed to write cert/key files for renewed cert {cert.id}: {e}")


def renew_certificate_in_place(
    cert: Certificate,
    ca=None,
    *,
    username: str = 'system',
    actor_user_id=None,
    rekey: bool = True,
    regenerate_crl: bool = True,
    trigger: str = 'manual',
) -> dict:
    """Re-issue ``cert`` on the same database row.

    Args:
        cert: the Certificate row to renew (must carry an issued certificate).
        ca: the issuing CA; resolved from the certificate when omitted.
        username: actor recorded in the audit trail and webhook.
        actor_user_id: numeric user id for the audit entry (API callers).
        rekey: generate a new key pair (True) or re-sign the existing public
            key (False — protocol enrollments keep the client's key).
        regenerate_crl: publish a fresh CRL when the CA has CDP enabled.
            Bulk callers pass False and regenerate once per CA afterwards.
        trigger: 'manual' | 'bulk' | 'auto', recorded in the audit details.

    Returns:
        dict with cert_id, old_serial, new_serial, valid_from, valid_to,
        ca_id, ca_refid, rekeyed.

    Raises:
        RenewalError: renewal was refused or could not be persisted. The
            session is left clean (rolled back) in every failure path.
    """
    if not cert.crt:
        raise RenewalError('Certificate data not available', 400)

    if cert.revoked:
        raise RenewalError(
            'Cannot renew a revoked certificate. Issue a new certificate instead.',
            409,
        )

    # Certificates issued by a Microsoft AD CS connection can't be re-signed
    # locally (the issuing CA's key lives on the Windows CA) — the caller must
    # resubmit the original CSR through the connector instead.
    if cert.source == 'msca':
        raise RenewalError(
            'Microsoft CA certificates must be renewed through the AD CS connector',
            400,
        )

    ca = ca or resolve_issuing_ca(cert)
    if not ca:
        raise RenewalError(
            'Issuing CA not found. The CA that signed this certificate is not in the system.',
            404,
        )
    if not ca.has_private_key:
        raise RenewalError(
            'CA private key not available. Cannot renew without CA private key.', 400
        )
    if not ca.crt:
        raise RenewalError('Issuing CA is awaiting its certificate', 400)
    if ca.offline:
        raise RenewalError('CA is offline; restore it before renewing', 400)
    if ca.revoked_in_chain:
        raise RenewalError('CA is revoked and can no longer renew certificates', 400)

    orig_cert = x509.load_pem_x509_certificate(
        base64.b64decode(cert.crt), default_backend()
    )
    ca_cert = x509.load_pem_x509_certificate(
        base64.b64decode(ca.crt), default_backend()
    )

    from services.hsm.ca_key_loader import get_ca_signing_key
    try:
        ca_key = get_ca_signing_key(ca)
    except Exception as e:
        logger.error(f"Failed to load signing key for CA {ca.id}: {e}", exc_info=True)
        raise RenewalError('Failed to load CA signing key', 500) from e

    now = utc_now()
    ca_not_after = ca_cert.not_valid_after_utc.replace(tzinfo=None)
    from utils.ca_signing_window import check_issuer_window
    try:
        # Expired (the clamp below would yield an already-expired cert) or
        # not yet valid: same rule as every issuance path
        check_issuer_window(ca_cert, now)
    except ValueError as e:
        raise RenewalError(str(e), 400) from e

    orig_pub_key = orig_cert.public_key()
    new_key = _generate_matching_key(orig_pub_key) if rekey else None
    public_key = new_key.public_key() if rekey else orig_pub_key

    # Same duration as the original, starting now, clamped to 1..3650 days and
    # to the CA's own expiry.
    orig_duration = orig_cert.not_valid_after_utc - orig_cert.not_valid_before_utc
    validity_days = orig_duration.days if orig_duration.days > 0 else DEFAULT_RENEWAL_DAYS
    validity_days = min(validity_days, MAX_RENEWAL_DAYS)
    not_before = now
    not_after = min(now + timedelta(days=validity_days), ca_not_after)

    # Re-validate the subject/SANs against the CA chain's NameConstraints
    # before re-issuing: the CA's constraints may have been tightened since
    # the original certificate was signed, so a renewal must not blindly
    # reproduce a now-out-of-scope name (RFC 5280 §4.2.1.10).
    try:
        renew_sans = list(
            orig_cert.extensions.get_extension_for_oid(
                ExtensionOID.SUBJECT_ALTERNATIVE_NAME
            ).value
        )
    except x509.ExtensionNotFound:
        renew_sans = None
    try:
        from services.trust_store.constraints_mixin import validate_name_constraints
        # renewal_of grants renewal-at-par: names the certificate already
        # carries stay renewable even if the CA's constraints tightened
        # (or started being enforced) after it was issued.
        validate_name_constraints(ca_cert, orig_cert.subject, renew_sans,
                                  renewal_of=orig_cert)
    except ValueError as exc:
        logger.info(f"Renewal rejected by CA NameConstraints: {exc}")
        raise RenewalError(f'Renewal violates CA name constraints: {exc}', 400) from exc

    builder = (
        x509.CertificateBuilder()
        .subject_name(orig_cert.subject)
        .issuer_name(ca_cert.subject)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
    )

    # Carry the original extensions across; SKI/AKI are regenerated below.
    for ext in orig_cert.extensions:
        if ext.oid in (ExtensionOID.AUTHORITY_KEY_IDENTIFIER,
                       ExtensionOID.SUBJECT_KEY_IDENTIFIER):
            continue
        try:
            builder = builder.add_extension(ext.value, ext.critical)
        except Exception:
            # Skip extensions that can't be copied
            pass
    # A responder certificate issued before id-pkix-ocsp-nocheck was emitted
    # gets it on renewal (idempotent when the original already carries it)
    try:
        orig_ekus = list(orig_cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value)
    except x509.ExtensionNotFound:
        orig_ekus = []
    builder = add_ocsp_nocheck_if_responder(builder, orig_ekus)

    builder = builder.add_extension(
        x509.SubjectKeyIdentifier.from_public_key(public_key), critical=False
    )
    try:
        builder = builder.add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
    except Exception:
        pass

    new_cert = builder.sign(ca_key, signing_hash_for(ca_key), default_backend())

    new_cert_pem = new_cert.public_bytes(serialization.Encoding.PEM).decode('utf-8')
    new_key_pem = None
    if rekey:
        new_key_pem = private_key_to_pem(new_key).decode('utf-8')

    cert_id = cert.id
    old_serial = cert.serial_number
    old_valid_to = cert.valid_to
    old_caref = cert.caref
    new_serial_hex = format(new_cert.serial_number, 'x')

    # --- Stage the superseded serial, then the in-place row update ---
    _record_superseded_serial(cert, old_serial, old_caref, old_valid_to, now)

    new_ski, new_aki = _extract_key_ids(new_cert)
    cert.crt = base64.b64encode(new_cert_pem.encode()).decode()
    if new_key_pem is not None:
        # Private keys are encrypted at rest with the master key, exactly as
        # at issuance (services/cert/mixins/lifecycle.py). Storing the renewed
        # key in the clear would silently downgrade an encrypted deployment.
        cert.prv = encrypt_private_key(
            base64.b64encode(new_key_pem.encode()).decode()
        )
    cert.serial_number = new_serial_hex
    cert.aki = new_aki
    cert.ski = new_ski
    cert.valid_from = not_before
    cert.valid_to = not_after
    cert.key_algo = _key_algo_label(public_key)
    cert.issuer = ca_cert.subject.rfc4514_string()
    for column, value in _extract_sans(new_cert).items():
        setattr(cert, column, value)
    cert.revoked = False
    cert.revoked_at = None
    cert.revoke_reason = None
    cert.invalidity_at = None
    cert.archived = False
    cert.renewed_at = now
    cert.renewed_times = (cert.renewed_times or 0) + 1

    # --- Atomic commit: RevokedSerial + in-place cert update together ---
    # On failure both are rolled back: the certificate keeps its old serial,
    # key and revocation state, and no revocation record is persisted.
    if not commit_or_rollback(logger, f"Failed to renew certificate {cert_id}"):
        raise RenewalError('Failed to renew certificate', 500)

    _write_cert_files(cert, new_cert_pem, new_key_pem)

    # A renewed delegated responder signs with a new certificate: the answers
    # cached under the old one would be served, old certificate embedded,
    # until they expired (self-review of #347)
    try:
        from services.ocsp_service import OCSPService
        for bound_ca_id in OCSPService.responder_cas_for_certificate(cert.id):
            OCSPService.invalidate_ca_cache(bound_ca_id)
    except Exception as e:
        logger.warning(f"OCSP cache not dropped after renewing certificate {cert.id}: {e}")

    # The old serial is now superseded; cached OCSP responses still say "good".
    try:
        OCSPService.invalidate_cached_responses(old_serial, ca_id=ca.id)
    except Exception as e:
        logger.warning(
            f"Failed to invalidate OCSP cache for old serial {old_serial}: {e}"
        )

    if regenerate_crl and ca.cdp_enabled:
        try:
            from services.crl_service import CRLService
            CRLService.generate_crl(ca.id, username=username)
        except Exception as e:
            logger.warning(f"Failed to auto-generate CRL after renewal: {e}")

    try:
        from services.audit_service import AuditService
        AuditService.log_action(
            action='certificate_renewed',
            resource_type='certificate',
            resource_id=str(cert_id),
            resource_name=cert.subject,
            details=(
                f"Renewed until {not_after.isoformat()} "
                f"(trigger: {trigger}, {'rekeyed' if rekey else 'same key'}, "
                f"old serial: {old_serial}, new serial: {new_serial_hex})"
            ),
            username=username,
            user_id=actor_user_id,
        )
    except Exception as e:
        logger.warning(f"Failed to write renewal audit entry for cert {cert_id}: {e}")

    try:
        from services.webhook_service import emit_cert_renewed
        emit_cert_renewed(cert.to_dict(), ca_refid=cert.caref, actor=username)
    except Exception as e:
        logger.warning(f"Failed to emit cert_renewed webhook for cert {cert_id}: {e}")

    logger.info(
        f"Renewed certificate {cert_id} ({trigger}): "
        f"{old_serial} -> {new_serial_hex}, valid to {not_after.isoformat()}"
    )

    return {
        'cert_id': cert_id,
        'old_serial': old_serial,
        'new_serial': new_serial_hex,
        'valid_from': not_before,
        'valid_to': not_after,
        'ca_id': ca.id,
        'ca_refid': ca.refid,
        'rekeyed': rekey,
    }
