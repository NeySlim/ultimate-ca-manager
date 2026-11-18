import logging

from models import db
from models.ssh import SSHCertificateAuthority, SSHCertificate
from services.ssh_ca_service import SSHCAService
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class SSHCertificateManagementMixin:

    @staticmethod
    def revoke_certificate(cert_id, reason='unspecified', username=None):
        cert = db.session.get(SSHCertificate, cert_id)
        if not cert:
            raise ValueError(f"SSH certificate not found: {cert_id}")

        # The CA row before the search: an issuance or import under it waits, then sees this
        # revocation; one that wrote first is committed when the search below reads it
        SSHCAService.lock_ca(cert.ssh_ca_id)
        cert = db.session.get(SSHCertificate, cert_id, populate_existing=True)
        if not cert:
            raise ValueError(f"SSH certificate not found: {cert_id}")
        if cert.revoked:
            raise ValueError("Certificate is already revoked")

        cert.revoked = True
        cert.revoked_at = utc_now()
        cert.revoke_reason = reason
        # The KRL revokes a non-zero serial, and the key ID of a serial 0 certificate under its CA
        # (ssh-keygen -k): every certificate it revokes is revoked; `revoked_with` names only those
        # this revocation turned from valid to revoked, `revoked_through` the KRL entry of each
        siblings, pending, through = [], [cert], {}
        while pending:
            held = pending.pop(0)
            entry = {'serial': int(held.serial)} if held.serial else {'key_id': held.key_id}
            match = (SSHCertificate.serial == held.serial if held.serial
                     else SSHCertificate.key_id == held.key_id)
            for sibling in (SSHCertificate.query.filter(SSHCertificate.ssh_ca_id == cert.ssh_ca_id, match,
                                                        SSHCertificate.id != held.id)
                            .order_by(SSHCertificate.id).populate_existing().all()):
                if sibling.revoked:
                    continue
                sibling.revoked = True
                sibling.revoked_at = cert.revoked_at
                sibling.revoke_reason = reason
                siblings.append(sibling)
                through[sibling.id] = entry
                pending.append(sibling)
        siblings.sort(key=lambda s: s.id)
        cert.revoked_with = siblings
        cert.revoked_through = through

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

        # The KRL is built from these rows: an unexpired certificate stays until it expires,
        # or a revoked one would drop out of the KRL and be accepted again
        if cert.valid_to > utc_now():
            if not cert.revoked:
                raise ValueError(
                    "Cannot delete a valid, non-revoked SSH certificate. Revoke it first.")
            raise ValueError(
                "A revoked SSH certificate stays in the KRL until it expires: "
                f"it can be deleted after {cert.valid_to:%Y-%m-%d %H:%M} UTC.")

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
