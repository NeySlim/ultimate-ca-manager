import fnmatch
import ipaddress
import json
import logging
import time
import uuid
from datetime import datetime, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.serialization import ssh as ssh_serialization
from sqlalchemy.exc import IntegrityError

from models import db
from models.ssh import SSHCertificateAuthority, SSHCertificate
from services.ssh_ca_service import (DEFAULT_HOST_TTL, DEFAULT_USER_TTL, SSHCAService,
                                     normalize_key_type)
from utils import ssh_serials as SSHSerials
from .utils import SSHCertificateUtilsMixin

logger = logging.getLogger(__name__)

BACKDATE_SECONDS = 300
MAX_VALIDITY_SECONDS = 10 * 365 * 24 * 3600  # 10 years
# PROTOCOL.certkeys: the critical options OpenSSH defines, all for user certificates
USER_CRITICAL_OPTIONS = ('force-command', 'source-address', 'verify-required')


def _checked_critical_options(cert_type, options):
    """The options to sign, or ValueError: a verifier refuses a certificate whose
    critical option it does not recognise, and none is defined for hosts."""
    if not options:
        return options
    if cert_type != 'user':
        raise ValueError("Critical options are not defined for host certificates")
    checked = {}
    for name, value in options.items():
        value = value if isinstance(value, str) else ''
        if name not in USER_CRITICAL_OPTIONS and '@' not in name.strip('@'):
            raise ValueError(f"Unknown critical option: {name} "
                             f"(allowed: {', '.join(USER_CRITICAL_OPTIONS)} or name@domain)")
        if name == 'force-command' and not value.strip():
            raise ValueError("force-command needs a command")
        if name == 'verify-required' and value:
            raise ValueError("verify-required takes no value")
        if name == 'source-address':
            entries = [entry.strip() for entry in value.split(',')]
            try:
                for entry in entries:
                    if '/' in entry and not entry.partition('/')[2].isdigit():
                        raise ValueError(entry)     # OpenSSH reads prefix lengths only
                    ipaddress.ip_network(entry, strict=True)
            except ValueError:
                raise ValueError(f"source-address must list addresses or networks "
                                 f"in CIDR form, comma-separated: {value!r}")
            value = ','.join(entries)
        checked[name] = value
    return checked


class SSHSerialConflict(Exception):
    """The serial taken is held by another certificate of the CA, after one retry: 409."""


def _serial_held(ca_id, serial):
    """Another certificate of the CA holds this non-zero serial: the unique index refused it."""
    return db.session.query(SSHCertificate.id).filter_by(ssh_ca_id=ca_id, serial=serial).first() is not None


class SSHCertificateSigningMixin:

    @staticmethod
    def sign_certificate(ca_id, public_key_data, cert_type, principals,
                         validity_seconds=None, key_id=None,
                         extensions=None, critical_options=None,
                         descr=None, source='web', username=None,
                         owner_group_id=None, valid_from=None, valid_to=None):
        ca = db.session.get(SSHCertificateAuthority, ca_id)
        if not ca:
            raise ValueError(f"SSH CA not found: {ca_id}")

        if cert_type not in SSHCertificate.VALID_CERT_TYPES:
            raise ValueError(f"Invalid certificate type: {cert_type}")

        if ca.ca_type != cert_type:
            raise ValueError(
                f"SSH {ca.ca_type} CA cannot sign {cert_type} certificates"
            )
        SSHCAService.refuse_unusable_ca(ca)  # before a serial is spent

        if not principals or not isinstance(principals, list):
            raise ValueError("At least one principal is required")

        principals = [p.strip() for p in principals if p and p.strip()]
        if not principals:
            raise ValueError("At least one non-empty principal is required")

        allowed = ca.get_allowed_principals()
        if not allowed and not ca.allow_any_principal:
            raise ValueError(
                "This SSH CA lists no allowed principals: add some, or allow any principal"
            )
        if allowed:
            for principal in principals:
                if not any(
                    fnmatch.fnmatchcase(principal, pattern)
                    for pattern in allowed
                ):
                    raise ValueError(
                        f"Principal '{principal}' is not in the CA's allowed principals list"
                    )

        # sshd logs the key ID as the holder's identity: the CA names it unless told otherwise
        default_key_id = f"{','.join(principals)}@{ca.descr}"
        key_id = key_id.strip() if isinstance(key_id, str) else key_id
        if key_id and key_id != default_key_id and not ca.allow_custom_key_id:
            raise ValueError(
                "This SSH CA sets the key ID itself: leave key_id out, "
                "or tick \"Let requesters set the key ID\" on the CA"
            )
        key_id = key_id or default_key_id
        # before a serial is spent
        named_by_ca = not ca.allow_custom_key_id
        SSHSerials.refuse_revoked_key_id(ca_id, key_id, named_by_ca=named_by_ca)

        public_key = SSHCertificateUtilsMixin._parse_public_key(public_key_data)
        subject_key_type = SSHCertificateUtilsMixin._detect_key_type(public_key)
        subject_fingerprint = SSHCertificateUtilsMixin._compute_fingerprint(public_key)

        # Backdated so a server whose clock lags behind still accepts it at once
        now_ts = int(time.time())
        max_ttl = int(ca.max_ttl) if ca.max_ttl else 0
        if valid_to is not None:
            # A typed range is applied as given, or refused: never truncated
            if valid_from is not None and valid_from < now_ts - BACKDATE_SECONDS:
                raise ValueError('valid_from is in the past')
            if valid_to <= now_ts:
                raise ValueError('valid_to is in the past')
            if valid_to > now_ts + MAX_VALIDITY_SECONDS:
                raise ValueError(f'valid_to is more than {MAX_VALIDITY_SECONDS} seconds from now')
            start = valid_from if valid_from is not None else now_ts
            span = valid_to - start
            if span < 60 or span > MAX_VALIDITY_SECONDS:
                raise ValueError(
                    f'The range from valid_from to valid_to must last between 60 and {MAX_VALIDITY_SECONDS} seconds')
            if max_ttl > 0 and span > max_ttl:
                raise ValueError(f"The range exceeds this CA's max_ttl ({max_ttl} seconds)")
            valid_after = valid_from if valid_from is not None else now_ts - BACKDATE_SECONDS
            valid_before = valid_to
        else:
            if validity_seconds is None:
                # An emptied default is the creation default of the CA type
                validity_seconds = int(ca.default_ttl) if ca.default_ttl else (
                    DEFAULT_USER_TTL if ca.ca_type == 'user' else DEFAULT_HOST_TTL)
            if max_ttl > 0 and validity_seconds > max_ttl:
                validity_seconds = max_ttl
            valid_after = now_ts - BACKDATE_SECONDS
            valid_before = now_ts + validity_seconds

        critical_options = _checked_critical_options(cert_type, critical_options)

        ca_private_key = SSHCAService.get_private_key_object(ca_id)

        def _signed(serial):
            nonlocal descr
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
                    # Caller-supplied extensions were previously applied verbatim,
                    # so a requester could grant itself permit-port-forwarding /
                    # permit-agent-forwarding (etc.) regardless of the CA's policy —
                    # the CA's configured list was consulted only when the caller
                    # omitted extensions entirely. Constrain them the same way
                    # principals are constrained, against the CA's own list.
                    # get_default_extensions() distinguishes "unset" (NULL column —
                    # standard OpenSSH set, preserving pre-existing CAs) from an
                    # explicitly empty policy ('[]' — nothing may be requested).
                    allowed_exts = set(ca.get_default_extensions())
                    invalid = [e for e in ext_dict if e not in allowed_exts]
                    if invalid:
                        raise ValueError(
                            "Extension(s) not permitted by this CA: "
                            f"{', '.join(sorted(invalid))}"
                        )
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
            # The embedded verification key must equal the stored anchor before it is trusted.
            SSHCAService.check_signing_public_key(ca, cert.signature_key())
            try:
                cert.verify_cert_signature()
            except InvalidSignature:
                raise ValueError('SSH certificate signature verification failed against the published CA key') from None
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
            return ssh_cert

        # A counter that trails the certificates of its CA (2.254 data, a restore, an import made
        # elsewhere) meets the unique index: raised past them, the signature is tried once more
        for attempt in (1, 2):
            serial = SSHCAService.get_next_serial(ca_id)
            ssh_cert = _signed(serial)
            try:
                # Explicit, so the guard does not rest on the lock the foreign key takes at the INSERT
                SSHCAService.lock_ca(ca_id)
                db.session.add(ssh_cert)
                db.session.flush()
                # Under the CA row, and after the write (SQLite's write lock): a revocation of
                # the key ID that committed meanwhile is seen here
                SSHSerials.refuse_revoked_key_id(ca_id, key_id, named_by_ca=named_by_ca)
                db.session.commit()
                break
            except SSHSerials.RevokedKeyId:
                db.session.rollback()
                raise
            except IntegrityError as e:
                db.session.rollback()
                if not _serial_held(ca_id, serial):
                    logger.error(f"Failed to store SSH certificate: {e}")
                    raise
                if attempt == 2:
                    raise SSHSerialConflict(
                        f"SSH CA serial {serial} is already held by another certificate of this CA, "
                        "even after its counter was raised: try again") from None
                logger.warning(f"SSH CA {ca_id}: serial {serial} already held, counter raised")
                SSHCAService.raise_serial_counter(ca_id)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                logger.error(f"Failed to store SSH certificate: {e}")
                raise

        logger.info(f"Issued SSH {cert_type} certificate #{serial} for "
                    f"{', '.join(principals)} (CA: {ca.descr})")
        return ssh_cert

    @staticmethod
    def generate_and_sign(ca_id, cert_type, principals, key_type=None,
                          validity_seconds=None, key_id=None,
                          extensions=None, critical_options=None,
                          descr=None, source='web', username=None,
                          owner_group_id=None, valid_from=None, valid_to=None):
        from cryptography.hazmat.primitives.serialization import (
            Encoding, NoEncryption, PrivateFormat,
        )

        private_key = SSHCAService._generate_key(normalize_key_type(key_type))
        public_key = private_key.public_key()
        pub_openssh = ssh_serialization.serialize_ssh_public_key(public_key).decode('utf-8')

        ssh_cert = SSHCertificateSigningMixin.sign_certificate(
            ca_id=ca_id,
            public_key_data=pub_openssh,
            cert_type=cert_type,
            principals=principals,
            validity_seconds=validity_seconds,
            valid_from=valid_from,
            valid_to=valid_to,
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
