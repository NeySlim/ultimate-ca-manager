"""
SSH Key Revocation List (KRL) Service

Generates OpenSSH KRL files from revoked SSH certificates.
Uses `ssh-keygen -k` subprocess since no pure Python KRL implementation exists.

KRL files can be used in sshd_config:
    RevokedKeys /etc/ssh/revoked_keys
"""

import hashlib
import logging
import os
import subprocess
import tempfile
import time

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from models.ssh import SSHCertificateAuthority, SSHCertificate, SSHKRL
from models import db
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


def _revocation_line(cert):
    """The ssh-keygen KRL specification line of a revoked certificate. Serial 0 means "not
    numbered" (PROTOCOL.certkeys): the certificate itself is given, and ssh-keygen lists it by
    key ID under its CA, which revokes every certificate of the CA with that key ID, empty included."""
    if cert.serial:
        return f"serial: {int(cert.serial)}\n"
    certificate = ' '.join((cert.certificate or '').split()[:2])
    if not certificate:
        raise RuntimeError(f"SSH certificate #{cert.id} has serial 0 and no certificate")
    return f"{certificate}\n"


class SSHKRLService:
    """Service for generating SSH Key Revocation Lists"""

    @staticmethod
    def revocation_digest(ca):
        """SHA-256 of the CA key and its sorted revocation lines: what a KRL of *ca* holds."""
        revoked = SSHCertificate.query.filter_by(ssh_ca_id=ca.id, revoked=True).all()
        lines = sorted(_revocation_line(cert) for cert in revoked)
        material = (ca.public_key or '').strip() + '\n' + ''.join(lines)
        return hashlib.sha256(material.encode('utf-8')).hexdigest()

    @staticmethod
    def published(ca_id):
        """The stored KRL of the CA, rebuilt with a higher version when its revocations changed.
        Written with a compare-and-set on the version, which every write raises: two nodes that
        rebuild at once keep one KRL, which both then serve."""
        ca = db.session.get(SSHCertificateAuthority, ca_id)
        if not ca:
            raise ValueError(f"SSH CA not found: {ca_id}")
        table = SSHKRL.__table__
        for _ in range(3):
            row = db.session.execute(table.select().where(table.c.ssh_ca_id == ca_id)).mappings().first()
            digest = SSHKRLService.revocation_digest(ca)
            if row is not None and row['digest'] == digest:
                return {'data': bytes(row['data']), 'version': int(row['version']),
                        'updated_at': row['updated_at']}
            floor = int(row['version']) + 1 if row is not None else 0
            version = max(floor, time.time_ns() // 1_000_000)
            data = SSHKRLService.generate_krl(ca_id, version=version)
            now = utc_now()
            values = dict(version=version, digest=digest, data=data, updated_at=now)
            try:
                if row is None:
                    db.session.execute(table.insert().values(ssh_ca_id=ca_id, **values))
                else:
                    written = db.session.execute(update(table).where(
                        table.c.ssh_ca_id == ca_id, table.c.version == row['version']).values(**values))
                    if written.rowcount != 1:
                        db.session.rollback()
                        continue
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                continue
            logger.info(f"Published KRL version {version} of SSH CA '{ca.descr}'")
            return {'data': data, 'version': version, 'updated_at': now}
        raise RuntimeError("the KRL changed three times while it was being published")

    @staticmethod
    def publish(ca_id):
        """After a revocation: the stored KRL follows at once; a failure waits for the next read."""
        try:
            SSHKRLService.published(ca_id)
        except Exception as exc:
            db.session.rollback()
            logger.error(f"Failed to publish the KRL of SSH CA {ca_id}: {exc}")

    @staticmethod
    def generate_krl(ca_id, version=None):
        """Generate a KRL file containing all revoked certificates for a CA.

        Uses ssh-keygen -k to create a binary KRL.

        Args:
            ca_id: SSH CA ID

        Returns:
            bytes: KRL binary data

        Raises:
            ValueError: If CA not found
            RuntimeError: If ssh-keygen fails
        """
        ca = db.session.get(SSHCertificateAuthority, ca_id)
        if not ca:
            raise ValueError(f"SSH CA not found: {ca_id}")

        # Get all revoked certificates for this CA
        revoked_certs = SSHCertificate.query.filter_by(
            ssh_ca_id=ca_id,
            revoked=True
        ).all()

        tmpdir = tempfile.mkdtemp(prefix='ucm_krl_')
        krl_path = os.path.join(tmpdir, 'revoked_keys')
        ca_pub_path = os.path.join(tmpdir, 'ca.pub')
        revoked_serials_path = os.path.join(tmpdir, 'revoked_serials')

        try:
            # Write CA public key
            with open(ca_pub_path, 'w') as f:
                f.write(ca.public_key)

            with open(revoked_serials_path, 'w') as f:
                for cert in revoked_certs:
                    f.write(_revocation_line(cert))

            # PROTOCOL.krl: krl_version increases each time the KRL changes; without one
            # given, a generation is a new KRL and takes its time in milliseconds
            if version is None:
                version = time.time_ns() // 1_000_000
            result = subprocess.run(
                ['ssh-keygen', '-k', '-z', str(int(version)),
                 '-f', krl_path, '-s', ca_pub_path, revoked_serials_path],
                capture_output=True, text=True, timeout=30
            )

            # The caller logs the failure once, prefixed with what failed
            if result.returncode != 0:
                raise RuntimeError(f"ssh-keygen: {result.stderr.strip()}")

            # Read the generated KRL
            with open(krl_path, 'rb') as f:
                krl_data = f.read()

            logger.info(f"Generated KRL for CA '{ca.descr}' with {len(revoked_certs)} revoked cert(s)")
            return krl_data

        finally:
            # Cleanup temp files
            for path in [krl_path, ca_pub_path, revoked_serials_path]:
                try:
                    if os.path.exists(path):
                        os.unlink(path)
                except OSError:
                    pass
            try:
                os.rmdir(tmpdir)
            except OSError:
                pass
