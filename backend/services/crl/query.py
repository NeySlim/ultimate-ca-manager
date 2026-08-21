import logging
from typing import List, Optional
from models import db, CA, Certificate, RevokedSerial
from models.crl import CRLMetadata
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class CRLQueryMixin:

    @staticmethod
    def get_revoked_certificates(ca_id: int) -> List:
        """Return revoked certificates for CRL generation.

        Merges two sources:
        1. Certificate rows with revoked=True (live certs)
        2. RevokedSerial rows whose certificate_id is no longer present
           (deleted certs whose revocation must persist until expiry)

        Deduplicates by serial_number — a live Certificate row always wins
        over a RevokedSerial fallback so there's a single source of truth.

        Per RFC 5280, expired certificates are excluded — clients reject
        them on validity alone, so they don't need CRL entries.
        """
        ca = db.session.get(CA, ca_id)
        if not ca:
            raise ValueError(f"CA with id {ca_id} not found")

        now = utc_now()

        # Live revoked certs that haven't expired yet
        live_certs = Certificate.query.filter(
            Certificate.caref == ca.refid,
            Certificate.revoked == True,
            Certificate.valid_to > now
        ).all()

        # Collect serials that have a live certificate row
        live_serials = {c.serial_number for c in live_certs}

        # Fallback: RevokedSerial entries for certs that were deleted
        # (certificate_id is NULL or the row no longer exists).
        # Only include entries that haven't expired yet.
        revoked_serials = RevokedSerial.query.filter(
            RevokedSerial.caref == ca.refid,
            RevokedSerial.valid_to > now
        ).all()

        orphan_serials = []
        for rs in revoked_serials:
            if rs.serial_number in live_serials:
                continue
            # Skip if the certificate row still exists and is not revoked
            if rs.certificate_id:
                existing = db.session.get(Certificate, rs.certificate_id)
                if existing and not existing.revoked:
                    continue
            orphan_serials.append(rs)

        return live_certs + orphan_serials

    @staticmethod
    def purge_stale_revoked_serials(ca_id: int) -> int:
        """Delete RevokedSerial entries whose valid_to has passed.

        Once the original certificate has expired, its serial no longer
        needs to appear on the CRL — the cert is rejected on validity
        alone. Returns the number of purged entries.
        """
        ca = db.session.get(CA, ca_id)
        if not ca:
            return 0

        now = utc_now()
        stale = RevokedSerial.query.filter(
            RevokedSerial.caref == ca.refid,
            RevokedSerial.valid_to < now
        ).all()

        count = len(stale)
        for rs in stale:
            db.session.delete(rs)

        if count:
            try:
                db.session.commit()
                logger.info(f"Purged {count} stale revoked_serials for CA {ca.descr}")
            except Exception as e:
                db.session.rollback()
                logger.warning(f"Failed to purge stale revoked_serials: {e}")
                return 0

        return count

    @staticmethod
    def is_auto_delete_enabled() -> bool:
        """Check if auto-delete of expired revoked certificates is enabled.

        Reads the 'crl_auto_delete_expired_revoked' system config key.
        Defaults to False (off) — expired revoked certs remain in the
        database as historical records unless an admin enables this.
        """
        from models.system_config import SystemConfig
        row = SystemConfig.query.filter_by(
            key='crl_auto_delete_expired_revoked'
        ).first()
        if not row or not row.value:
            return False
        return row.value.lower() in ('true', '1', 'yes', 'on')

    @staticmethod
    def purge_expired_revoked_certificates(ca_id: int) -> int:
        """Delete expired+revoked Certificate rows for this CA.

        Only deletes certificates that are BOTH revoked AND past valid_to.
        The RevokedSerial table is the authoritative revocation record —
        deleting the cert row here is safe because the revocation data
        persists independently.

        Uses CertificateService.delete_certificate to ensure cert/key/csr
        files on disk are also cleaned up and audit logs are written.

        Gated by the 'crl_auto_delete_expired_revoked' system setting.
        Returns the number of deleted certificate rows.
        """
        ca = db.session.get(CA, ca_id)
        if not ca:
            return 0

        now = utc_now()
        expired_revoked = Certificate.query.filter(
            Certificate.caref == ca.refid,
            Certificate.revoked == True,
            Certificate.valid_to < now
        ).all()

        count = 0
        for cert in expired_revoked:
            try:
                from services.cert_service import CertificateService
                if CertificateService.delete_certificate(cert_id=cert.id, username='system'):
                    count += 1
            except Exception as e:
                logger.warning(f"Failed to auto-delete expired revoked cert {cert.id}: {e}")

        if count:
            logger.info(
                f"Auto-deleted {count} expired revoked certificates for CA {ca.descr}"
            )

        return count

    @staticmethod
    def get_latest_crl(ca_id: int) -> Optional[CRLMetadata]:
        return CRLMetadata.query.filter_by(
            ca_id=ca_id, is_delta=False
        ).order_by(CRLMetadata.crl_number.desc()).first()

    @staticmethod
    def get_latest_crl_by_refid(ca_refid: str) -> Optional[CRLMetadata]:
        ca = CA.query.filter_by(refid=ca_refid).first()
        if not ca:
            return None
        return CRLQueryMixin.get_latest_crl(ca.id)

    @staticmethod
    def get_crl_pem(ca_refid: str) -> Optional[str]:
        crl = CRLQueryMixin.get_latest_crl_by_refid(ca_refid)
        return crl.crl_pem if crl else None

    @staticmethod
    def get_crl_der(ca_refid: str) -> Optional[bytes]:
        crl = CRLQueryMixin.get_latest_crl_by_refid(ca_refid)
        return crl.crl_der if crl else None

    @staticmethod
    def get_latest_delta_crl(ca_id: int) -> Optional[CRLMetadata]:
        return CRLMetadata.query.filter_by(
            ca_id=ca_id, is_delta=True
        ).order_by(CRLMetadata.crl_number.desc()).first()

    @staticmethod
    def get_latest_base_crl(ca_id: int) -> Optional[CRLMetadata]:
        return CRLMetadata.query.filter_by(
            ca_id=ca_id, is_delta=False
        ).order_by(CRLMetadata.crl_number.desc()).first()
