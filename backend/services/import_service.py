"""
Certificate Import Service - Unified parsing for CA and Certificate imports
"""
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
import re
import base64
from datetime import datetime, timezone
from utils.cert_issuer import cas_by_ski, is_self_signed
from utils.foreign_algorithms import describe_public_key, spki_der
from utils.key_codec import private_key_to_pem, refuse_eddsa_key
from utils.pkcs12_import import refuse_pkcs12_import


def parse_certificate_file(file_data, filename, password=None, import_key=True):
    """
    Parse certificate from various formats.
    Returns: (cert, private_key, format_detected)
    Raises: ValueError on parse error
    """
    # Before any parsing: the FIPS provider cannot load an EdDSA key, so the refusal must say so.
    refuse_eddsa_key(file_data, 'the imported file')
    cert = None
    private_key = None
    format_type = 'auto'
    
    # Auto-detect format
    if b'-----BEGIN' in file_data:
        format_type = 'pem'
    elif filename.endswith('.p12') or filename.endswith('.pfx'):
        format_type = 'pkcs12'
    elif filename.endswith('.p7b') or filename.endswith('.p7c'):
        format_type = 'pkcs7'
    else:
        format_type = 'der'
    
    if format_type == 'pem':
        # Extract just the PEM block if there's extra text
        pem_match = re.search(b'-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----', file_data, re.DOTALL)
        if pem_match:
            pem_data = pem_match.group(0)
        else:
            pem_data = file_data
        
        # Check if it's a PKCS7 PEM
        if b'-----BEGIN PKCS7-----' in file_data:
            try:
                from cryptography.hazmat.primitives.serialization import pkcs7
                certs = pkcs7.load_pem_pkcs7_certificates(file_data)
                if certs:
                    cert = certs[0]
            except Exception:
                pass
        
        if not cert:
            cert = x509.load_pem_x509_certificate(pem_data, default_backend())
        
        # Try to extract private key
        if import_key and b'PRIVATE KEY' in file_data:
            key_match = re.search(b'-----BEGIN.*?PRIVATE KEY-----.+?-----END.*?PRIVATE KEY-----', file_data, re.DOTALL)
            if key_match:
                try:
                    private_key = serialization.load_pem_private_key(
                        key_match.group(0), 
                        password=password.encode() if password else None, 
                        backend=default_backend()
                    )
                except Exception:
                    pass
                
    elif format_type == 'der':
        try:
            cert = x509.load_der_x509_certificate(file_data, default_backend())
        except Exception as der_err:
            # Maybe it's a PKCS7 DER
            try:
                from cryptography.hazmat.primitives.serialization import pkcs7
                certs = pkcs7.load_der_pkcs7_certificates(file_data)
                if certs:
                    cert = certs[0]
            except Exception:
                raise der_err
        
    elif format_type == 'pkcs12':
        from cryptography.hazmat.primitives.serialization import pkcs12
        refuse_pkcs12_import()
        try:
            private_key, cert, chain = pkcs12.load_key_and_certificates(
                file_data, password.encode() if password else None, default_backend()
            )
        except Exception as e:
            if 'password' in str(e).lower() or 'mac' in str(e).lower():
                raise ValueError('Invalid password for PKCS12 file')
            raise
    
    elif format_type == 'pkcs7':
        from cryptography.hazmat.primitives.serialization import pkcs7
        try:
            certs = pkcs7.load_der_pkcs7_certificates(file_data)
        except Exception:
            certs = pkcs7.load_pem_pkcs7_certificates(file_data)
        if certs:
            cert = certs[0]
    
    if not cert:
        raise ValueError('Could not parse certificate. Supported formats: PEM, DER, PKCS12 (.p12, .pfx), PKCS7 (.p7b)')
    
    return cert, private_key, format_type


def is_ca_certificate(cert):
    """Check if certificate has CA:TRUE basic constraint"""
    try:
        basic_constraints = cert.extensions.get_extension_for_oid(x509.oid.ExtensionOID.BASIC_CONSTRAINTS)
        return basic_constraints.value.ca
    except x509.extensions.ExtensionNotFound:
        return False


def extract_cert_info(cert):
    """Extract common certificate information"""
    from cryptography.x509.oid import NameOID
    from cryptography.x509.oid import ExtensionOID
    
    subject = cert.subject
    issuer = cert.issuer
    
    def get_name_attr(name_obj, oid):
        try:
            return name_obj.get_attributes_for_oid(oid)[0].value
        except Exception:
            return ''
    
    # Get serial number as hex string for comparison
    serial_hex = format(cert.serial_number, 'x').upper()
    
    # Extract SKI/AKI
    ski = None
    aki = None
    try:
        ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_KEY_IDENTIFIER)
        ski = ext.value.key_identifier.hex(':').upper()
    except Exception:
        pass
    try:
        ext = cert.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_KEY_IDENTIFIER)
        if ext.value.key_identifier:
            aki = ext.value.key_identifier.hex(':').upper()
    except Exception:
        pass
    
    # Extract SANs
    san_dns, san_ip, san_email, san_uri = [], [], [], []
    try:
        san_ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        from cryptography.x509 import DNSName, IPAddress, RFC822Name, UniformResourceIdentifier
        for name_entry in san_ext.value:
            if isinstance(name_entry, DNSName):
                san_dns.append(name_entry.value)
            elif isinstance(name_entry, IPAddress):
                san_ip.append(str(name_entry.value))
            elif isinstance(name_entry, RFC822Name):
                san_email.append(name_entry.value)
            elif isinstance(name_entry, UniformResourceIdentifier):
                san_uri.append(name_entry.value)
    except Exception:
        pass
    
    return {
        'cn': get_name_attr(subject, NameOID.COMMON_NAME),
        'org': get_name_attr(subject, NameOID.ORGANIZATION_NAME),
        'country': get_name_attr(subject, NameOID.COUNTRY_NAME),
        'subject': subject.rfc4514_string(),
        'issuer': issuer.rfc4514_string(),
        'is_self_signed': cert.subject == cert.issuer,
        'valid_from': cert.not_valid_before_utc,
        'valid_to': cert.not_valid_after_utc,
        'serial_number': cert.serial_number,
        'serial_hex': serial_hex,
        'ski': ski,
        'aki': aki,
        'san_dns': san_dns,
        'san_ip': san_ip,
        'san_email': san_email,
        'san_uri': san_uri,
    }


class AmbiguousImportTarget(ValueError):
    """Several records share the certificate's names and none can be told
    to be the one it belongs to."""

    code = None

    @property
    def details(self):
        return {'code': self.code} if self.code else None


class CrossCertificateImport(AmbiguousImportTarget):
    """The certificate re-certifies a CA's key under another issuer: applying it
    would replace the stored certificate and parent the CA under that issuer."""

    code = 'cross_certificate_detected'

    def __init__(self, message, record=None):
        super().__init__(message)
        self.record = record

    @property
    def details(self):
        details = {'code': self.code}
        if self.record is not None:
            stored = _record_identity(self.record)[0]
            details['ca_id'] = self.record.id
            details['options'] = ['attach'] if stored is not None and is_self_signed(stored) else ['attach', 'replace']
        return details


class ImportConflict(ValueError):
    """The record cannot be updated from the imported certificate; nothing was changed."""


def _spki(public_key):
    return public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _spki_of(cert_or_csr):
    """SubjectPublicKeyInfo of a certificate or CSR, also when pyca cannot load its key."""
    if describe_public_key(cert_or_csr):
        return spki_der(cert_or_csr)
    return _spki(cert_or_csr.public_key())


def _record_identity(record):
    """The record's current certificate and public key: (x509 or None, SPKI or None).

    The key comes from the certificate when the record holds one; a record
    still waiting for its certificate is known by its stored private key,
    its signing request, or the cached public key of its HSM key (read as
    stored: nothing here may reach the HSM or commit).
    """
    stored_cert = None
    if record.crt:
        try:
            stored_cert = x509.load_pem_x509_certificate(base64.b64decode(record.crt), default_backend())
            return stored_cert, _spki_of(stored_cert)
        except Exception:
            stored_cert = None
    if record.prv:
        try:
            from utils.key_codec import load_pem_bytes
            key = serialization.load_pem_private_key(
                load_pem_bytes(record.prv, context=f"{type(record).__name__} {record.id}"), password=None)
            return stored_cert, _spki(key.public_key())
        except Exception:
            pass
    csr_stored = getattr(record, 'csr', None)
    if csr_stored:
        try:
            csr_pem = csr_stored.encode('utf-8') if csr_stored.startswith('-----BEGIN') else base64.b64decode(csr_stored)
            csr = x509.load_pem_x509_csr(csr_pem, default_backend())
            return stored_cert, _spki_of(csr)
        except Exception:
            pass
    hsm_key = getattr(record, 'hsm_key', None)
    cached = getattr(hsm_key, 'public_key_pem', None) if hsm_key is not None else None
    if cached:
        try:
            public_key = serialization.load_pem_public_key(
                cached.encode() if isinstance(cached, str) else cached)
            return stored_cert, _spki(public_key)
        except Exception:
            pass
    if getattr(record, 'hsm_key_id', None):
        # Last resort, the HSM itself: the lookup caches the public key and
        # commits, which is why every caller runs before touching any record
        try:
            from services.hsm import HsmService
            pem = HsmService.get_public_key(record.hsm_key_id)
            if pem:
                public_key = serialization.load_pem_public_key(pem.encode() if isinstance(pem, str) else pem)
                return stored_cert, _spki(public_key)
        except Exception:
            pass
    return stored_cert, None


def stored_certificate_serial(record):
    """The serial number of the certificate a record holds, or None."""
    if not record.crt:
        return None
    try:
        return x509.load_pem_x509_certificate(base64.b64decode(record.crt), default_backend()).serial_number
    except Exception:
        return None


def path_length_of(cert):
    """The pathLenConstraint of a CA certificate, or None."""
    try:
        return cert.extensions.get_extension_for_class(x509.BasicConstraints).value.path_length
    except x509.ExtensionNotFound:
        return None


def relink_parent_caref(cert, current_caref, exclude_ca_id=None):
    """The caref a CA record should hold once *cert* is its certificate.

    None for a self-signed certificate; the CA whose key verifies the
    signature, found by AKI then by issuer name; *current_caref* when UCM
    holds no such CA (an external root imported later relinks it).
    """
    from models import CA
    from utils.cert_issuer import certificate_signed_by, authority_key_identifier_hex, is_self_signed
    if is_self_signed(cert):
        return None
    aki = authority_key_identifier_hex(cert)
    candidates = cas_by_ski(aki) if aki else []
    if not candidates:
        candidates = CA.query.filter(CA.subject == cert.issuer.rfc4514_string()).all()
    for parent in candidates:
        if exclude_ca_id is not None and parent.id == exclude_ca_id or not parent.crt:
            continue
        try:
            parent_cert = x509.load_pem_x509_certificate(base64.b64decode(parent.crt), default_backend())
            if certificate_signed_by(cert, parent_cert):
                return parent.refid
        except Exception:
            continue
    return current_caref


def update_ca_from_import(existing_ca, cert, cert_pem, cert_info, *, key_pem=None, encrypted_prv=None, name=None):
    """Apply an imported CA certificate to its existing record; returns whether the stored key was unbound.

    The stored key is checked before anything is changed; raises ImportConflict
    when it cannot be (HSM unreachable, key unreadable). The caller commits.
    """
    from services.ca_service import CAService
    from utils.cert_issuer import stored_private_key_matches, hsm_key_binding_matches
    # An HSM lookup may commit its public key cache, so the key is decided before the record is touched
    key_dropped = False
    if key_pem:
        # The new certificate's key arrived with it: it replaces whatever the record held
        pass
    elif existing_ca.hsm_key_id:
        # Unreachable HSM key: left untouched rather than kept or dropped on a guess
        bound = hsm_key_binding_matches(existing_ca.hsm_key_id, cert)
        if bound is None:
            raise ImportConflict('Cannot verify the HSM key bound to this CA against the new '
                                 'certificate; the HSM key is unreachable')
        key_dropped = bound is False
    elif existing_ca.prv:
        # A re-keyed certificate imported without its key would leave a pair that signs nothing verifiable
        matches = stored_private_key_matches(existing_ca.prv, cert, context=f"CA {existing_ca.id}")
        if matches is None:
            raise ImportConflict('Cannot verify the stored private key against the new '
                                 'certificate; the stored key could not be read')
        key_dropped = matches is False

    old_serial = stored_certificate_serial(existing_ca)
    existing_ca.descr = name or cert_info['cn'] or existing_ca.descr
    existing_ca.crt = base64.b64encode(cert_pem).decode('utf-8')
    if key_pem:
        existing_ca.prv = encrypted_prv
        existing_ca.hsm_key_id = None
    elif key_dropped:
        existing_ca.prv = None
        existing_ca.hsm_key_id = None
    existing_ca.issuer = cert_info['issuer']
    existing_ca.valid_from = cert_info['valid_from']
    existing_ca.valid_to = cert_info['valid_to']
    existing_ca.ski = cert_info.get('ski')
    if old_serial is not None and old_serial != cert.serial_number:
        # Revocation is per certificate (RFC 5280): the new one is not the revoked one
        existing_ca.revoked = False
        existing_ca.revoked_at = None
        existing_ca.revoke_reason = None
        existing_ca.invalidity_at = None
    existing_ca.serial_number = str(cert.serial_number)
    existing_ca.caref = relink_parent_caref(cert, existing_ca.caref, exclude_ca_id=existing_ca.id)
    existing_ca.path_length = path_length_of(cert)
    # Deleted after its revocation and imported again, or renewed into a serial its parent revoked (#343)
    CAService.apply_persisted_revocation(existing_ca)
    return key_dropped


def _issuer_identity(cert, parents_by_name):
    """What identifies the authority that signed *cert* beyond its name, or None.

    ('key', SPKI) of the CA known to UCM whose key verifies the signature;
    else ('aki', key identifier) when the certificate names its issuer's key.
    Two parents may share a name and differ by key (#347 review).
    """
    from utils.cert_issuer import certificate_signed_by
    name = cert.issuer.rfc4514_string()
    if name not in parents_by_name:
        from models import CA
        parents = []
        for parent in CA.query.filter_by(subject=name).all():
            if not parent.crt:
                continue
            try:
                parents.append(x509.load_pem_x509_certificate(base64.b64decode(parent.crt), default_backend()))
            except Exception:
                continue
        parents_by_name[name] = parents
    for parent_cert in parents_by_name[name]:
        try:
            if certificate_signed_by(cert, parent_cert):
                return ('key', _spki_of(parent_cert))
        except Exception:
            continue
    try:
        aki = cert.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier).value.key_identifier
    except x509.ExtensionNotFound:
        aki = None
    return ('aki', aki) if aki else None


def _same_issuer(stored_cert, cert, parents_by_name):
    """Whether *stored_cert* and *cert* were issued by the same authority.

    Same name first. Then, when either certificate verifies against a parent
    known to UCM, the other must verify against that same parent: every
    known parent was tried on both, so a certificate that verifies against
    none, whether it carries an authority key identifier or not, was signed
    by a different key. When neither verifies against a known parent, two
    authority key identifiers are compared; when one or both certificates
    carry none, the name is all there is: same issuer.
    """
    if stored_cert.issuer != cert.issuer:
        return False
    stored_id = _issuer_identity(stored_cert, parents_by_name)
    new_id = _issuer_identity(cert, parents_by_name)
    if (stored_id is not None and stored_id[0] == 'key') or (new_id is not None and new_id[0] == 'key'):
        return stored_id == new_id
    if stored_id is None or new_id is None:
        return True
    return stored_id[1] == new_id[1]


def _would_replace_valid_certificate(stored, new, any_validity=False):
    """Of one key (the caller checked): a self-signed certificate replaced by another, or two
    unexpired certificates from issuers of different names (whatever their validity if
    *any_validity*), is a cross-certificate. The same issuer name under a new key is a root
    rollover: the new certificate replaces the old one."""
    if is_self_signed(new):
        return False
    if is_self_signed(stored) or any_validity:
        return True
    if stored.issuer == new.issuer:
        return False
    now = datetime.now(timezone.utc)
    return stored.not_valid_after_utc > now and new.not_valid_after_utc > now


def refused_as_cross_certificate(record, stored, new, replace_cross=False, any_validity=False):
    """Whether installing *new* over *record*'s *stored* certificate is refused as a
    cross-certificate. ``replace_cross`` lets an intermediate be overwritten, a revoked
    ancestor (not a looping chain) makes the old certificate not worth keeping."""
    if not _would_replace_valid_certificate(stored, new, any_validity):
        return False
    if is_self_signed(stored):
        return True
    if replace_cross:
        return False
    return any_validity or getattr(record, 'chain_revocation', None) != 'revoked'


def _select_existing(candidates, cert, kind, replace_cross=False, any_validity=False):
    """Among *candidates*, the records sharing the certificate's names, the
    one the certificate belongs to; None when there is none (#347 review).

    The record holding the certificate's key wins: the very same certificate
    first, then the one whose certificate has the same issuer, name and key
    of the issuer (a cross-signed CA holds the same key under several
    issuers, and two issuers may share a name), then the single record
    holding the key. A renewed certificate thus lands on its own record, not
    on a homonym that happened to come first. Without a key link a single
    candidate is the record being re-keyed; several cannot be told apart,
    and the import is refused rather than applied to whichever the database
    returned.
    """
    if not candidates:
        return None
    try:
        wanted = _spki_of(cert)
    except Exception:
        raise ValueError('Unsupported public key algorithm in the certificate')
    parents_by_name = {}
    same_key, same_issuer, exact, full = [], [], [], []
    for record in candidates:
        stored_cert, spki = _record_identity(record)
        if stored_cert is not None:
            full.append(record)
        if spki != wanted:
            continue
        same_key.append(record)
        if stored_cert is None or not _same_issuer(stored_cert, cert, parents_by_name):
            continue
        same_issuer.append(record)
        if stored_cert.serial_number == cert.serial_number:
            exact.append(record)
    if exact:
        return exact[0]
    if len(same_issuer) == 1:
        return same_issuer[0]
    if same_issuer:
        raise AmbiguousImportTarget(
            f"{len(same_issuer)} existing {kind}s share this subject, hold this "
            f"certificate's key and were issued under the same issuer name, which "
            f"does not tell them apart; the record to update cannot be determined")
    if len(same_key) == 1:
        stored_cert, _ = _record_identity(same_key[0])
        if kind == 'CA' and stored_cert is not None and refused_as_cross_certificate(
                same_key[0], stored_cert, cert, replace_cross, any_validity):
            raise CrossCertificateImport(
                f"This certificate re-certifies the key of the {kind} "
                f"'{getattr(same_key[0], 'descr', '')}' under another issuer "
                f"(a cross-certificate); importing it would replace the certificate that record "
                f"holds, so it is refused", record=same_key[0])
        return same_key[0]
    if same_key:
        raise AmbiguousImportTarget(
            f"{len(same_key)} existing {kind}s share this subject and hold this "
            f"certificate's key, none under this certificate's issuer; the record "
            f"to update cannot be determined")
    # No record holds this key. A single record holding a certificate is the
    # one being re-keyed; a record still waiting for its certificate is known
    # by its key alone and cannot be re-keyed, so the certificate is a new one
    if not full:
        return None
    if len(full) == 1:
        return full[0]
    raise AmbiguousImportTarget(
        f"{len(full)} existing {kind}s share this subject and none holds this "
        f"certificate's key; the record to update cannot be determined")


def install_on_pending_ca(ca, cert_pem, username, *, encrypted_prv=None, name=None, replace_cross=False):
    """Install *cert_pem* on a CA waiting for its certificate, or holding an
    outstanding renewal request, through the same path as the dedicated
    upload (key match, validity, chain to the issuer, activation, the
    request fulfilled), and emit the lifecycle event.

    A key that arrived with the certificate (already checked to be its own)
    becomes the record's when it holds none, as after a restore without
    keys. Returns (ca_dict, warnings, superseded); raises ValueError with a
    user-safe message when the certificate is refused (#347 review).
    """
    from models import db
    from services.ca_service import CAService
    from services.webhook_service import emit_ca_updated
    if encrypted_prv and not ca.prv and not ca.hsm_key_id:
        ca.prv = encrypted_prv
    ca, warnings, superseded = CAService.complete_external_ca(
        ca, cert_pem, username=username, replace_cross=replace_cross)
    if name and name != ca.descr:
        ca.descr = name
        db.session.commit()
    # Snapshot before emit: subscribers may commit and expire the instance
    ca_dict = ca.to_dict()
    emit_ca_updated(ca_dict, actor=username, changes={'certificate': 'installed'})
    return ca_dict, warnings, superseded


def find_existing_ca(cert_info, cert, replace_cross=False, any_validity=False):
    """
    The existing CA record *cert* belongs to, by subject, or None.
    Raises AmbiguousImportTarget when several CAs share the subject and
    the certificate's key does not single one out; CrossCertificateImport
    when it would overwrite a certificate that is valid (``replace_cross``
    allows that for an intermediate, never for a self-signed root).
    """
    from models import CA
    candidates = CA.query.filter_by(subject=cert_info['subject']).order_by(CA.id).all()
    return _select_existing(candidates, cert, 'CA', replace_cross=replace_cross, any_validity=any_validity)


CROSS_MODES = ('auto', 'attach', 'replace', 'refuse')


def cross_mode_from(value):
    """The requested cross_mode, 'auto' when absent, None when unknown."""
    mode = (value or 'auto').strip().lower() if isinstance(value, str) or value is None else None
    return mode if mode in CROSS_MODES else None


def find_existing_ca_for_import(cert_info, cert, cross_mode='auto', username='system'):
    """``(existing, attached)``: find_existing_ca, with a cross-certificate handled by *cross_mode*.

    ``auto`` attaches it to a self-signed root and refuses on an intermediate; ``attach``
    attaches on either; ``replace`` lets an intermediate be overwritten; ``refuse`` never
    touches the record. *attached* is ``(row, warnings)`` once the certificate was stored
    as a cross-certificate of *existing*; the caller commits."""
    try:
        return find_existing_ca(cert_info, cert, replace_cross=cross_mode == 'replace',
                                any_validity=cross_mode in ('refuse', 'attach')), None
    except CrossCertificateImport as e:
        record = e.record
        if cross_mode in ('refuse', 'replace') or record is None:
            raise
        stored = _record_identity(record)[0]
        if cross_mode == 'auto' and not (stored is not None and is_self_signed(stored)):
            raise
        from services.ca import cross_certs
        try:
            return record, cross_certs.attach_certificate(record, cert, username, commit=False)
        except cross_certs.CrossCertError as err:
            raise ImportConflict(err.message) from err


def find_existing_certificate(cert_info, cert):
    """
    The existing certificate record *cert* belongs to, by subject + issuer,
    or None. Raises AmbiguousImportTarget when several records share them
    and the certificate's key does not single one out.
    """
    from models import Certificate
    candidates = Certificate.query.filter_by(
        subject=cert_info['subject'],
        issuer=cert_info['issuer']
    ).order_by(Certificate.id).all()
    return _select_existing(candidates, cert, 'certificate')


def find_pending_csr_for_certificate(cert):
    """
    The pending CSR record (request stored, no certificate yet) whose public
    key is this certificate's, or None (#341).

    A certificate issued by an external CA for a CSR generated here has an
    issuer the CSR record never had, so subject/issuer matching cannot find
    it; the key pair is the one thing the two share.
    """
    from models import Certificate
    wanted = _spki_of(cert)
    from utils.cert_status import pending_requests
    pending = pending_requests().order_by(Certificate.id.desc()).all()
    for record in pending:
        try:
            stored = record.csr
            csr_pem = stored.encode('utf-8') if stored.startswith('-----BEGIN') else base64.b64decode(stored)
            csr = x509.load_pem_x509_csr(csr_pem, default_backend())
            spki = _spki_of(csr)
        except Exception:
            continue
        if spki == wanted and not _issued_for_request(record.csr, cert):
            return record
    return None


def _issued_for_request(stored_csr, cert):
    """Whether a row already holds this very certificate for the same request:
    a request put back to be signed again (#389) shares that certificate's key,
    and importing the certificate again must not complete it."""
    from models import Certificate
    from utils.cert_status import signed_requests
    der = cert.public_bytes(serialization.Encoding.DER)
    for row in signed_requests().filter(Certificate.csr == stored_csr).all():
        try:
            pem = row.crt.encode('utf-8') if row.crt.startswith('-----BEGIN') else base64.b64decode(row.crt)
            issued = x509.load_pem_x509_certificate(pem, default_backend())
        except Exception:
            continue
        if issued.public_bytes(serialization.Encoding.DER) == der:
            return True
    return False


def serialize_cert_to_pem(cert):
    """Serialize certificate to PEM format"""
    return cert.public_bytes(serialization.Encoding.PEM)


def serialize_key_to_pem(private_key):
    """Serialize private key to PEM format (unencrypted)"""
    if not private_key:
        return None
    return private_key_to_pem(private_key)


def finish_cross_attach(ca, attached, username):
    """Commit a cross-certificate attached by an import and announce it; returns the response data."""
    from models import db
    from services.ca import cross_certs
    row, warnings = attached
    db.session.commit()
    cross_certs.announce(ca, 'attached', row, username)
    return {**ca.to_dict(), 'cross_certificate': row.to_dict(), 'warnings': warnings}
