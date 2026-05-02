import json
import logging
import time
import uuid
from datetime import datetime, timezone

from cryptography.hazmat.primitives.serialization import ssh as ssh_serialization

from models import db
from models.ssh import SSHCertificateAuthority, SSHCertificate
from services.ssh_ca_service import SSHCAService
from .utils import SSHCertificateUtilsMixin

logger = logging.getLogger(__name__)


class SSHCertificateSigningMixin:

    @staticmethod
    def sign_certificate(ca_id, public_key_data, cert_type, principals,
                         validity_seconds=None, key_id=None,
                         extensions=None, critical_options=None,
                         descr=None, source='web', username=None,
                         owner_group_id=None):
        ca = SSHCertificateAuthority.query.get(ca_id)
        if not ca:
            raise ValueError(f"SSH CA not found: {ca_id}")

        if cert_type not in SSHCertificate.VALID_CERT_TYPES:
            raise ValueError(f"Invalid certificate type: {cert_type}")

        if not principals or not isinstance(principals, list):
            raise ValueError("At least one principal is required")

        principals = [p.strip() for p in principals if p and p.strip()]
        if not principals:
            raise ValueError("At least one non-empty principal is required")

        allowed = ca.get_allowed_principals()
        if allowed:
            for p in principals:
                if p not in allowed:
                    raise ValueError(
                        f"Principal '{p}' is not in the CA's allowed principals list"
                    )

        public_key = SSHCertificateUtilsMixin._parse_public_key(public_key_data)
        subject_key_type = SSHCertificateUtilsMixin._detect_key_type(public_key)
        subject_fingerprint = SSHCertificateUtilsMixin._compute_fingerprint(public_key)

        if validity_seconds is None:
            validity_seconds = ca.default_ttl or 86400

        if ca.max_ttl and ca.max_ttl > 0:
            if validity_seconds > ca.max_ttl:
                validity_seconds = ca.max_ttl

        now_ts = int(time.time())
        valid_after = now_ts
        valid_before = now_ts + validity_seconds

        serial = SSHCAService.get_next_serial(ca_id)

        if not key_id:
            key_id = f"{','.join(principals)}@{ca.descr}"

        ca_private_key = SSHCAService.get_private_key_object(ca_id)

        ssh_cert_type = (ssh_serialization.SSHCertificateType.USER
                         if cert_type == 'user'
                         else ssh_serialization.SSHCertificateType.HOST)

        builder = (ssh_serialization.SSHCertificateBuilder()
                   .public_key(public_key)
                   .serial(serial)
                   .type(ssh_cert_type)
                   .key_id(key_id.encode('utf-8'))
                   .valid_principals([p.encode('utf-8') for p in principals])
                   .valid_after(valid_after)
                   .valid_before(valid_before))

        if cert_type == 'user':
            if extensions is not None:
                if isinstance(extensions, list):
                    ext_dict = {e: '' for e in extensions}
                else:
                    ext_dict = extensions
            else:
                ext_dict = {e: '' for e in ca.get_default_extensions()}
            for ext_name, ext_value in sorted(ext_dict.items()):
                val = ext_value if isinstance(ext_value, str) else ''
                builder = builder.add_extension(
                    ext_name.encode('utf-8'),
                    val.encode('utf-8')
                )

        if critical_options:
            for opt_name, opt_value in sorted(critical_options.items()):
                val = opt_value if isinstance(opt_value, str) else ''
                builder = builder.add_critical_option(
                    opt_name.encode('utf-8'),
                    val.encode('utf-8')
                )

        cert = builder.sign(ca_private_key)
        cert_bytes = cert.public_bytes().decode('utf-8')

        pub_openssh = ssh_serialization.serialize_ssh_public_key(public_key).decode('utf-8')

        valid_from_dt = datetime.fromtimestamp(valid_after, tz=timezone.utc)
        valid_to_dt = datetime.fromtimestamp(valid_before, tz=timezone.utc)

        if not descr:
            descr = f"{cert_type.capitalize()} cert for {', '.join(principals)}"

        if extensions is not None:
            if isinstance(extensions, list):
                stored_extensions = {e: '' for e in extensions}
            else:
                stored_extensions = extensions
        elif cert_type == 'user':
            stored_extensions = {e: '' for e in ca.get_default_extensions()}
        else:
            stored_extensions = {}

        ssh_cert = SSHCertificate(
            refid=str(uuid.uuid4()),
            descr=descr,
            ssh_ca_id=ca_id,
            cert_type=cert_type,
            key_id=key_id,
            public_key=pub_openssh,
            certificate=cert_bytes,
            principals=json.dumps(principals),
            serial=serial,
            valid_from=valid_from_dt,
            valid_to=valid_to_dt,
            key_type=subject_key_type,
            fingerprint=subject_fingerprint,
            extensions=json.dumps(stored_extensions) if stored_extensions else None,
            critical_options=json.dumps(critical_options) if critical_options else None,
            source=source,
            created_by=username,
            owner_group_id=owner_group_id,
        )

        try:
            db.session.add(ssh_cert)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to store SSH certificate: {e}")
            raise

        logger.info(f"Issued SSH {cert_type} certificate #{serial} for "
                    f"{', '.join(principals)} (CA: {ca.descr})")
        return ssh_cert

    @staticmethod
    def generate_and_sign(ca_id, cert_type, principals, key_type='ed25519',
                          validity_seconds=None, key_id=None,
                          extensions=None, critical_options=None,
                          descr=None, source='web', username=None,
                          owner_group_id=None):
        from cryptography.hazmat.primitives.serialization import (
            Encoding, NoEncryption, PrivateFormat,
        )

        private_key = SSHCAService._generate_key(key_type)
        public_key = private_key.public_key()
        pub_openssh = ssh_serialization.serialize_ssh_public_key(public_key).decode('utf-8')

        ssh_cert = SSHCertificateSigningMixin.sign_certificate(
            ca_id=ca_id,
            public_key_data=pub_openssh,
            cert_type=cert_type,
            principals=principals,
            validity_seconds=validity_seconds,
            key_id=key_id,
            extensions=extensions,
            critical_options=critical_options,
            descr=descr,
            source=source,
            username=username,
            owner_group_id=owner_group_id,
        )

        prv_pem = private_key.private_bytes(
            Encoding.PEM, PrivateFormat.OpenSSH, NoEncryption()
        ).decode('utf-8')

        return {
            'certificate': ssh_cert,
            'private_key': prv_pem,
        }
