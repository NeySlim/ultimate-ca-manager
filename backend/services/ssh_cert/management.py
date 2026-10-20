import logging

from models import db
from models.ssh import SSHCertificateAuthority, SSHCertificate
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class SSHCertificateManagementMixin:

    @staticmethod
    def revoke_certificate(cert_id, reason='unspecified', username=None):
        cert = db.session.get(SSHCertificate, cert_id)
        if not cert:
            raise ValueError(f"SSH certificate not found: {cert_id}")

        if cert.revoked:
            raise ValueError("Certificate is already revoked")

        cert.revoked = True
        cert.revoked_at = utc_now()
        cert.revoke_reason = reason

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to revoke SSH certificate {cert_id}: {e}")
            raise

        logger.info(f"Revoked SSH certificate #{cert.serial} ({cert.key_id}): {reason}")
        return cert

    @staticmethod
    def delete_certificate(cert_id):
        cert = db.session.get(SSHCertificate, cert_id)
        if not cert:
            raise ValueError(f"SSH certificate not found: {cert_id}")

        # Un certificat valide (non révoqué, non expiré) ne se supprime pas.
        if not cert.revoked and cert.valid_to > utc_now():
            raise ValueError(
                "Cannot delete a valid, non-revoked SSH certificate. Revoke it first.")

        cert_name = cert.key_id
        try:
            db.session.delete(cert)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to delete SSH certificate {cert_id}: {e}")
            raise

        logger.info(f"Deleted SSH certificate '{cert_name}'")
        return cert_name

    @staticmethod
    def export_certificate(cert_id):
        cert = db.session.get(SSHCertificate, cert_id)
        if not cert:
            raise ValueError(f"SSH certificate not found: {cert_id}")

        ca = db.session.get(SSHCertificateAuthority, cert.ssh_ca_id)
        ca_pub = ca.public_key if ca else None

        return {
            'certificate': cert.certificate,
            'public_key': cert.public_key,
            'ca_public_key': ca_pub,
            'key_id': cert.key_id,
            'cert_type': cert.cert_type,
        }
