import json
import logging
import uuid
from datetime import datetime, timezone

from cryptography.hazmat.primitives.serialization import ssh as ssh_serialization

from models import db
from models.ssh import SSHCertificateAuthority, SSHCertificate
from .utils import SSHCertificateUtilsMixin

logger = logging.getLogger(__name__)


class SSHCertificateDecodeMixin:

    @staticmethod
    def decode_certificate(cert_data):
        if isinstance(cert_data, str):
            cert_data = cert_data.strip().encode('utf-8')

        try:
            cert = ssh_serialization.load_ssh_public_identity(cert_data)
        except Exception as e:
            logger.warning(f"SSH certificate parse failed: {e}")
            raise ValueError("Invalid SSH certificate format. Provide a valid OpenSSH certificate.")

        if not hasattr(cert, 'serial'):
            raise ValueError("The provided data is a public key, not a certificate")

        cert_type = 'user' if cert.type == ssh_serialization.SSHCertificateType.USER else 'host'

        public_key = cert.public_key()
        key_type = SSHCertificateUtilsMixin._detect_key_type(public_key)
        fingerprint = SSHCertificateUtilsMixin._compute_fingerprint(public_key)

        ca_key = cert.signature_key()
        ca_fingerprint = SSHCertificateUtilsMixin._compute_fingerprint(ca_key)

        extensions = {k.decode('utf-8'): v.decode('utf-8')
                      for k, v in cert.extensions.items()}
        critical_options = {k.decode('utf-8'): v.decode('utf-8')
                            for k, v in cert.critical_options.items()}

        try:
            cert.verify_cert_signature()
            signature_valid = True
        except Exception:
            signature_valid = False

        return {
            'serial': cert.serial,
            'type': cert_type,
            'key_id': cert.key_id.decode('utf-8'),
            'principals': [p.decode('utf-8') for p in cert.valid_principals],
            'valid_after': cert.valid_after,
            'valid_before': cert.valid_before,
            'valid_from': datetime.fromtimestamp(cert.valid_after, tz=timezone.utc).isoformat(),
            'valid_to': datetime.fromtimestamp(cert.valid_before, tz=timezone.utc).isoformat(),
            'key_type': key_type,
            'fingerprint': fingerprint,
            'ca_fingerprint': ca_fingerprint,
            'extensions': extensions,
            'critical_options': critical_options,
            'signature_valid': signature_valid,
            'nonce': cert.nonce.hex(),
        }

    @staticmethod
    def import_certificate(certificate_data, descr=None, ssh_ca_id=None, username=None):
        decoded = SSHCertificateDecodeMixin.decode_certificate(certificate_data)

        ca_fingerprint = decoded['ca_fingerprint']

        matched_ca = SSHCertificateAuthority.query.filter_by(fingerprint=ca_fingerprint).first()

        if ssh_ca_id is not None:
            provided_ca = SSHCertificateAuthority.query.get(ssh_ca_id)
            if not provided_ca:
                raise ValueError(f"SSH CA not found: {ssh_ca_id}")
            if provided_ca.fingerprint != ca_fingerprint:
                raise ValueError(
                    "Provided SSH CA fingerprint does not match the certificate's signing CA"
                )
            matched_ca = provided_ca
        elif matched_ca is None:
            raise ValueError(
                "The signing CA is not in the system. Import the CA first or provide ssh_ca_id."
            )

        cert_bytes = (certificate_data.strip().encode('utf-8')
                      if isinstance(certificate_data, str)
                      else certificate_data.strip())
        cert_obj = ssh_serialization.load_ssh_public_identity(cert_bytes)
        public_key = cert_obj.public_key()
        pub_openssh = ssh_serialization.serialize_ssh_public_key(public_key).decode('utf-8')

        existing = SSHCertificate.query.filter_by(
            ssh_ca_id=matched_ca.id, serial=decoded['serial']
        ).first()
        if existing:
            raise ValueError(
                f"A certificate with serial {decoded['serial']} from this CA already exists"
            )

        principals = decoded['principals']
        cert_type = decoded['type']

        if not descr:
            descr = f"Imported {cert_type} cert for {decoded['key_id']}"

        valid_from_dt = datetime.fromtimestamp(decoded['valid_after'], tz=timezone.utc)
        valid_to_dt = datetime.fromtimestamp(decoded['valid_before'], tz=timezone.utc)

        ssh_cert = SSHCertificate(
            refid=str(uuid.uuid4()),
            descr=descr,
            ssh_ca_id=matched_ca.id,
            cert_type=cert_type,
            key_id=decoded['key_id'],
            public_key=pub_openssh,
            certificate=certificate_data.strip(),
            principals=json.dumps(principals),
            serial=decoded['serial'],
            valid_from=valid_from_dt,
            valid_to=valid_to_dt,
            key_type=decoded['key_type'],
            fingerprint=decoded['fingerprint'],
            extensions=json.dumps(decoded['extensions']) if decoded['extensions'] else None,
            critical_options=json.dumps(decoded['critical_options']) if decoded['critical_options'] else None,
            source='imported',
            created_by=username,
        )

        try:
            db.session.add(ssh_cert)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to store imported SSH certificate: {e}")
            raise

        logger.info(f"Imported SSH {cert_type} certificate #{decoded['serial']} "
                    f"(key_id: {decoded['key_id']}, CA: {matched_ca.descr})")
        return ssh_cert
