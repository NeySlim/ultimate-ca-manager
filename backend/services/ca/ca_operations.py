"""
CA certificate operations (chain, serial).

CRL generation lives in ``services/crl/generation.py`` (``CRLService``);
this mixin no longer carries a local CRL implementation.
"""
import logging
from typing import List

from models import CA, db
from .helpers import get_ca_cert_pem

logger = logging.getLogger(__name__)


class CAOperationsMixin:

    @staticmethod
    def apply_persisted_revocation(ca: CA) -> bool:
        """Mark *ca* revoked from the record its parent still holds (#343).

        Called when a CA row is created from an imported certificate: a CA
        deleted after its revocation and imported again keeps its revoked
        state instead of coming back as active. No commit; returns whether
        a record applied."""
        record = ca.persisted_revocation()
        if record is None:
            return False
        ca.revoked = True
        ca.revoked_at = record.revoked_at
        ca.revoke_reason = record.revoke_reason
        ca.invalidity_at = record.invalidity_at
        return True

    @staticmethod
    def revoke_ca(
        ca_id: int,
        reason: str = 'unspecified',
        username: str = 'system',
        invalidity_at=None,
    ):
        """Revoke an intermediate CA from its parent (#343).

        The serial goes to the parent's revoked_serials, which its CRL and
        OCSP responder already consult, so relying parties see the
        revocation through the parent; the CA itself is marked revoked and
        every issuance path refuses it (get_ca_signing_key). Permanent, as
        for certificates. A root CA is not revocable here (self-signed:
        relying parties drop it from their trust stores), nor is a CA whose
        issuer is not held in UCM (revoke it at that root).

        Returns (ca, warnings): the revocation is recorded even when the
        parent's CRL could not be regenerated (offline or key-less parent),
        and the caller must surface that, since the CRL served until the
        next successful generation does not carry the serial yet.
        """
        import base64
        from datetime import timedelta
        from cryptography import x509
        from models import RevokedSerial
        from utils.datetime_utils import utc_now

        ca = db.session.get(CA, ca_id)
        if not ca:
            raise ValueError("CA not found")
        if ca.revoked:
            raise ValueError("CA is already revoked")
        if ca.is_pending or not ca.crt:
            raise ValueError("CA is awaiting its certificate")
        if ca.is_root or not ca.caref:
            raise ValueError(
                "A root CA cannot be revoked: relying parties remove it from their trust stores"
            )
        parent = CA.query.filter_by(refid=ca.caref).first()
        if not parent:
            raise ValueError(
                "The issuing CA is not held in UCM: revoke this CA at that root "
                "(its CRL can then be served from UCM)"
            )

        # The serial as the certificate carries it: the stored column may be
        # empty on an imported CA
        cert = x509.load_pem_x509_certificate(base64.b64decode(ca.crt))
        serial_decimal = str(cert.serial_number)
        if not ca.serial_number:
            ca.serial_number = serial_decimal

        now = utc_now()
        ca.revoked = True
        ca.revoked_at = now
        ca.revoke_reason = reason
        ca.invalidity_at = invalidity_at
        valid_to = ca.valid_to or cert.not_valid_after_utc.replace(tzinfo=None)

        existing = RevokedSerial.query.filter_by(
            caref=parent.refid, serial_number=ca.serial_number
        ).first()
        if existing:
            existing.revoked_at = now
            existing.revoke_reason = reason
            existing.invalidity_at = invalidity_at
            existing.valid_to = valid_to
        else:
            db.session.add(RevokedSerial(
                caref=parent.refid,
                serial_number=ca.serial_number,
                revoked_at=now,
                revoke_reason=reason,
                invalidity_at=invalidity_at,
                valid_to=valid_to,
                certificate_id=None,
            ))

        try:
            db.session.commit()
        except Exception as _commit_err:
            db.session.rollback()
            logger.error(f"Revocation failed for CA {ca_id}: {_commit_err}", exc_info=True)
            raise RuntimeError(f"Revocation failed for CA {ca_id}: {_commit_err}") from _commit_err

        from services.audit_service import AuditService
        AuditService.log_ca(
            'ca_revoked', ca,
            f'Revoked CA: {ca.descr} - Reason: {reason} (issuer: {parent.descr})',
            username=username,
        )

        # The parent publishes the revocation: CRL now, OCSP on next answer
        warnings = []
        if parent.cdp_enabled:
            from services.crl_service import CRLService
            try:
                CRLService.generate_crl(parent.id, username=username)
            except Exception as e:
                logger.warning(
                    f"CRL of CA {parent.descr} not regenerated after revoking CA {ca.descr}: {e}"
                )
                AuditService.log_ca(
                    'crl_auto_generation_failed', parent,
                    f'Failed to auto-generate CRL after revoking CA {ca.descr}: {e}',
                    success=False,
                )
                warnings.append(
                    f"The CRL of the parent CA '{parent.descr}' could not be regenerated "
                    f"({e}): the CRL currently served does not list this CA yet. "
                    f"Regenerate it once the parent can sign again."
                )
        else:
            warnings.append(
                f"CDP is disabled on the parent CA '{parent.descr}': no CRL publishes this "
                f"revocation; relying parties learn it through OCSP only."
            )
        from services.ocsp_service import OCSPService
        OCSPService.invalidate_cached_responses(ca.serial_number, ca_id=parent.id)
        return ca, warnings
    """CA certificate operations"""

    @staticmethod
    def increment_serial(ca_id: int) -> int:
        """
        Increment CA serial number.

        Args:
            ca_id: CA ID

        Returns:
            New serial number

        Raises:
            ValueError: If CA not found
        """
        ca = db.session.get(CA, ca_id)
        if not ca:
            raise ValueError("CA not found")

        ca.serial = (ca.serial or 0) + 1
        try:
            db.session.commit()
        except Exception as _commit_err:
            db.session.rollback()
            logger.error(f"Commit failed in services/ca/ca_operations.py:41: {_commit_err}", exc_info=True)
            raise

        return ca.serial

    @staticmethod
    def get_ca_chain(ca_id: int) -> List[bytes]:
        """
        Get CA certificate chain from leaf to root.

        Args:
            ca_id: CA ID

        Returns:
            List of certificate PEMs (leaf to root)
        """
        chain = []
        ca = db.session.get(CA, ca_id)

        while ca:
            cert_pem = get_ca_cert_pem(ca)
            if cert_pem:
                chain.append(cert_pem)

            # Get parent CA
            if ca.caref:
                ca = CA.query.filter_by(refid=ca.caref).first()
            else:
                break

        return chain

    @staticmethod
    def get_certificate_chain(refid: str) -> List[str]:
        """
        Get CA certificate chain by refid (wrapper returning strings).

        Args:
            refid: CA reference ID

        Returns:
            List of PEM strings (leaf to root)

        Raises:
            ValueError: If CA not found
        """
        ca = CA.query.filter_by(refid=refid).first()
        if not ca:
            raise ValueError(f"CA not found: {refid}")

        chain_bytes = CAOperationsMixin.get_ca_chain(ca.id)
        return [pem.decode('utf-8') if isinstance(pem, bytes) else pem
                for pem in chain_bytes]
