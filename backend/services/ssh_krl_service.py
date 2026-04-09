"""
SSH Key Revocation List (KRL) Service

Generates OpenSSH KRL files from revoked SSH certificates.
Uses `ssh-keygen -k` subprocess since no pure Python KRL implementation exists.

KRL files can be used in sshd_config:
    RevokedKeys /etc/ssh/revoked_keys
"""

import logging
import os
import subprocess
import tempfile

from models.ssh import SSHCertificateAuthority, SSHCertificate

logger = logging.getLogger(__name__)


class SSHKRLService:
    """Service for generating SSH Key Revocation Lists"""

    @staticmethod
    def generate_krl(ca_id):
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
        ca = SSHCertificateAuthority.query.get(ca_id)
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

            if not revoked_certs:
                # Generate empty KRL (still valid, just revokes nothing)
                with open(revoked_serials_path, 'w') as f:
                    f.write('')

                result = subprocess.run(
                    ['ssh-keygen', '-k', '-f', krl_path, '-s', ca_pub_path, revoked_serials_path],
                    capture_output=True, text=True, timeout=30
                )
            else:
                # Write revoked serial numbers
                with open(revoked_serials_path, 'w') as f:
                    for cert in revoked_certs:
                        f.write(f"serial: {cert.serial}\n")

                result = subprocess.run(
                    ['ssh-keygen', '-k', '-f', krl_path, '-s', ca_pub_path, revoked_serials_path],
                    capture_output=True, text=True, timeout=30
                )

            if result.returncode != 0:
                logger.error(f"ssh-keygen KRL generation failed: {result.stderr}")
                raise RuntimeError(f"Failed to generate KRL: {result.stderr}")

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
