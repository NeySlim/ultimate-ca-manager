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

Only a certificate whose private key the server holds can be renewed here
(a device-held key renews through its enrollment protocol). The callers
differ in the key strategy:

``rekey=True``   UCM generates a fresh key pair matching the original's
                 algorithm and size (manual and bulk renewal).
``rekey=False``  the held key pair is re-signed (scheduled auto-renewal),
                 so exports made from the previous certificate keep working.
"""
import base64
import json
import logging
from datetime import timedelta

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed448, ed25519, rsa
from cryptography.x509.oid import ExtensionOID, NameOID

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
from utils.x509_aki import authority_key_identifier_from_issuer
from utils.ca_pointer_extensions import add_ca_pointer_extensions
from utils.leaf_key_usage import constrain_builder_key_usage
from utils.datetime_utils import cert_not_before


_SCT_LIST_OID = x509.ObjectIdentifier('1.3.6.1.4.1.11129.2.4.2')
_ISSUER_OWNED_EXTENSION_OIDS = frozenset({
    ExtensionOID.AUTHORITY_KEY_IDENTIFIER,
    ExtensionOID.SUBJECT_KEY_IDENTIFIER,
    ExtensionOID.CRL_DISTRIBUTION_POINTS,
    ExtensionOID.AUTHORITY_INFORMATION_ACCESS,
    ExtensionOID.CERTIFICATE_POLICIES,
    _SCT_LIST_OID,
})


class RenewalError(Exception):
    """Renewal could not be completed.

    ``status`` carries the HTTP status the API layer should surface; service
    callers can ignore it and just use ``message``.
    """

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def resolve_issuing_ca(cert: Certificate):
    """Find the CA that signed ``cert``: by refid, else by signature.

    Names alone used to decide (subject, then the issuer's Common Name
    among every CA): a homonymous CA after a rotation, or a local CA merely
    sharing the CN of an external issuer, re-signed the certificate. The
    CAs carrying the issuer's name are tried first, then every other, and
    only the one whose key verifies the certificate's signature qualifies.
    """
    ca = CA.query.filter_by(refid=cert.caref).first() if cert.caref else None
    if ca:
        return ca
    if not cert.crt:
        return None
    try:
        leaf = x509.load_pem_x509_certificate(base64.b64decode(cert.crt), default_backend())
    except Exception:
        return None
    from utils.cert_issuer import authority_key_identifier_hex, certificate_signed_by
    named = CA.query.filter(CA.subject == cert.issuer).all() if cert.issuer else []
    others = [c for c in CA.query.all() if c not in named]
    leaf_aki = authority_key_identifier_hex(leaf)
    verified = []
    for candidate in named + others:
        if not candidate.crt:
            continue
        try:
            ca_cert = x509.load_pem_x509_certificate(
                base64.b64decode(candidate.crt), default_backend())
            if certificate_signed_by(leaf, ca_cert):
                verified.append((candidate, ca_cert))
        except Exception:
            continue
    if not verified:
        return None
    # Several CA records for one key (a cross-signed or re-issued CA): the
    # one whose SKI the certificate names as its AKI is the real issuer
    if leaf_aki:
        for candidate, ca_cert in verified:
            try:
                ski = ca_cert.extensions.get_extension_for_oid(
                    ExtensionOID.SUBJECT_KEY_IDENTIFIER).value.key_identifier
            except x509.ExtensionNotFound:
                continue
            if ski.hex(':').upper() == str(leaf_aki).upper():
                return candidate
    return verified[0][0]


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


def check_renewable(cert: Certificate) -> None:
    """Raise :class:`RenewalError` when ``cert`` cannot be renewed at all
    (no certificate, revoked, issued by a Microsoft CA, key not held by the
    server). Shared by the renewal itself and by the routes, which check it
    before queueing a renewal for approval: a request no renewal could honour
    must not wait for an approver."""
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

    if not cert.prv:
        # The key lives on the device (SCEP, EST, WSTEP, ACME enrolment,
        # certificate imported without its key): a certificate re-signed
        # here could never reach it, and superseding the serial the device
        # still presents only got that device refused by OCSP and the CRL
        raise RenewalError(
            'The server does not hold the private key of this certificate; '
            'renew it through its enrollment protocol, sign a new request or '
            'issue a new certificate',
            409,
        )


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
        rekey: generate a new key pair (True) or re-sign the held key pair
            (False, scheduled auto-renewal).
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
    check_renewable(cert)
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
    # Same floor as issuance (a re-signed RSA-1024 is still RSA-1024)
    from utils.key_type import validate_enrollment_public_key
    key_error = validate_enrollment_public_key(public_key)
    if key_error:
        raise RenewalError(f'Cannot renew: {key_error}', 400)

    # Same duration as the original, starting now, clamped to 1..3650 days and
    # to the CA's own expiry.
    orig_duration = orig_cert.not_valid_after_utc - orig_cert.not_valid_before_utc
    validity_days = orig_duration.days if orig_duration.days > 0 else DEFAULT_RENEWAL_DAYS
    validity_days = min(validity_days, MAX_RENEWAL_DAYS)
    # Issuance policy rules (#335) bind a renewal as they bind an issuance
    from services.policy_service import PolicyEvaluationService
    cn_attrs = orig_cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    try:
        orig_dns = list(orig_cert.extensions.get_extension_for_oid(
            ExtensionOID.SUBJECT_ALTERNATIVE_NAME).value.get_values_for_type(x509.DNSName))
    except x509.ExtensionNotFound:
        orig_dns = []
    key_label = (str(public_key.key_size) if isinstance(public_key, rsa.RSAPublicKey)
                 else public_key.curve.name if isinstance(public_key, ec.EllipticCurvePublicKey)
                 else None)
    violations, validity_days = PolicyEvaluationService.enforce_rules(
        PolicyEvaluationService.applicable_policies(
            ca.id, getattr(cert, 'template_id', None),
            cn_attrs[0].value if cn_attrs else None, orig_dns),
        key_type=key_label, dns_name_count=len(set(orig_dns)), validity_days=validity_days)
    if violations:
        raise RenewalError('Policy violation: ' + '; '.join(violations), 400)
    not_before = cert_not_before()
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

    # Carry the original extensions across, except those the issuer sets:
    # SKI/AKI (regenerated below), CDP/AIA/CPS (rebuilt from the CA's
    # current configuration, as on issuance -- a changed public URL or a
    # disabled CRL must not stay frozen in renewed certificates) and the
    # embedded SCTs (signed for the old certificate's bytes, meaningless on
    # the new one; the CT policy below embeds fresh ones when configured).
    for ext in orig_cert.extensions:
        if ext.oid in _ISSUER_OWNED_EXTENSION_OIDS:
            continue
        try:
            builder = builder.add_extension(ext.value, ext.critical)
        except Exception as exc:
            raise RenewalError(
                f'Cannot carry extension {ext.oid.dotted_string} over to the '
                f'renewed certificate: {exc}', 400,
            ) from exc
    builder = add_ca_pointer_extensions(builder, ca)
    # A Key Usage the key type cannot honour (#327) is corrected here as it
    # is on every issuance path, whatever the original certificate carried
    builder = constrain_builder_key_usage(builder)
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
    # The issuer's own SKI, as on every issuance path (RFC 5280 §4.2.1.1);
    # an AKI derived from the key differs from it for an imported or
    # HSM-generated CA and breaks chain building
    builder = builder.add_extension(
        authority_key_identifier_from_issuer(ca_cert), critical=False
    )

    new_cert = builder.sign(ca_key, signing_hash_for(ca_key), default_backend())
    try:
        from utils.ct_client import apply_ct_policy
        new_cert, _ = apply_ct_policy(new_cert, ca_cert, ca_key)
    except ValueError as exc:
        raise RenewalError(f'Cannot renew: {exc}', 400) from exc

    new_cert_pem = new_cert.public_bytes(serialization.Encoding.PEM).decode('utf-8')
    new_key_pem = None
    if rekey:
        new_key_pem = private_key_to_pem(new_key).decode('utf-8')

    cert_id = cert.id
    old_serial = cert.serial_number
    old_valid_to = cert.valid_to
    # The serial being superseded belongs to the CA that really signed the
    # certificate (resolved above; a row naming a CA record that no longer
    # exists is re-linked to the real one)
    old_caref = ca.refid
    new_serial_hex = format(new_cert.serial_number, 'x')

    # Two workers renewing the same row would each supersede the serial
    # they read and the second would overwrite the first's certificate,
    # leaving a signed certificate neither stored nor revocable: only the
    # worker that still sees the serial it started from may proceed
    claimed = db.session.query(Certificate).filter(
        Certificate.id == cert_id,
        Certificate.serial_number == old_serial,
    ).update({Certificate.serial_number: new_serial_hex}, synchronize_session=False)
    if claimed != 1:
        db.session.rollback()
        raise RenewalError(
            'Certificate was renewed by another request; reload it and retry', 409,
        )

    # --- Stage the superseded serial, then the in-place row update ---
    _record_superseded_serial(cert, old_serial, old_caref, old_valid_to, now)
    cert.caref = ca.refid

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
