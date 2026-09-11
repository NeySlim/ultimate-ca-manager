"""CSR generation and signing mixin"""
import base64
import uuid
import json
import logging
from typing import Dict, List, Optional

from cryptography import x509
from cryptography.hazmat.backends import default_backend

from models import db, CA, Certificate
from services.file_regen_service import mirror_private_key
from services.trust_store import TrustStoreService
from utils.dn_parse import subject_common_name
from utils.file_naming import cert_cert_path, cert_key_path, cert_csr_path, ca_cert_path, ca_key_path

logger = logging.getLogger(__name__)


def _csr_key_type_label(public_key):
    """The CSR key in the form compute_template_overrides normalizes: an RSA
    size ('2048'), an OpenSSL curve name ('secp256r1') or an Edwards curve
    ('ed25519', 'ed448'), the key types enrollment accepts; None otherwise."""
    from cryptography.hazmat.primitives.asymmetric import ec, ed448, ed25519, rsa
    if isinstance(public_key, rsa.RSAPublicKey):
        return str(public_key.key_size)
    if isinstance(public_key, ec.EllipticCurvePublicKey):
        return public_key.curve.name
    if isinstance(public_key, ed25519.Ed25519PublicKey):
        return 'ed25519'
    if isinstance(public_key, ed448.Ed448PublicKey):
        return 'ed448'
    return None

# CSRs generated before 2.225 were described as "CSR for <CN>"
_LEGACY_CSR_DESCR_PREFIX = 'CSR for '


def settle_csr_descr(descr, cn):
    """The name a CSR record keeps once it holds a certificate.

    The certificates list shows a record by its description, so a CSR
    described as "CSR for <CN>" appeared under that wording once signed
    (#342). Drop the prefix; fall back to the CN when nothing is left."""
    if descr and descr.startswith(_LEGACY_CSR_DESCR_PREFIX):
        descr = descr[len(_LEGACY_CSR_DESCR_PREFIX):].strip()
    return descr or cn or 'Certificate'


def _spki_der(public_key) -> bytes:
    from cryptography.hazmat.primitives import serialization
    return public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _csr_pem_bytes(stored: str) -> bytes:
    """A stored CSR column holds base64 PEM, or raw PEM on old records."""
    if stored.startswith('-----BEGIN'):
        return stored.encode('utf-8')
    return base64.b64decode(stored)


try:
    from security.encryption import decrypt_private_key, encrypt_private_key
    from utils.key_codec import load_pem_bytes
    HAS_ENCRYPTION = True
except ImportError:
    HAS_ENCRYPTION = False

    def decrypt_private_key(data):
        return data

    def encrypt_private_key(data):
        return data

    def load_pem_bytes(prv, *, context="private key"):
        return base64.b64decode(prv) if prv else b''


class CSRMixin:

    @staticmethod
    def generate_csr(
        descr: str,
        dn: Dict[str, str],
        key_type: str = '2048',
        digest: str = 'sha256',
        san_dns: Optional[List[str]] = None,
        san_ip: Optional[List[str]] = None,
        san_email: Optional[List[str]] = None,
        san_uri: Optional[List[str]] = None,
        san_upn: Optional[List[str]] = None,
        username: str = 'system'
    ) -> Certificate:
        """
        Generate a Certificate Signing Request

        Args:
            descr: Description
            dn: Distinguished Name
            key_type: Key type
            digest: Hash algorithm
            san_dns: DNS SANs
            san_ip: IP SANs
            san_email: Email SANs
            san_uri: URI SANs
            san_upn: UPN SANs (Microsoft User Principal Name, OID 1.3.6.1.4.1.311.20.2.3)
            username: User generating CSR

        Returns:
            Certificate record with CSR
        """
        # Build subject
        subject = TrustStoreService.build_subject(dn)

        # Generate CSR
        csr_pem, key_pem = TrustStoreService.generate_csr(
            subject=subject,
            key_type=key_type,
            digest=digest,
            san_dns=san_dns,
            san_ip=san_ip,
            san_email=san_email,
            san_uri=san_uri,
            san_upn=san_upn
        )

        # Parse CSR
        csr = x509.load_pem_x509_csr(csr_pem, default_backend())

        # Encrypt private key at rest if encryption is enabled.
        # Without this, generated CSR keys (and any future intermediate CA
        # promoted from this record) sit base64-only in the DB.
        prv_encoded = base64.b64encode(key_pem).decode('utf-8')
        try:
            from security.encryption import key_encryption
            if key_encryption.is_enabled:
                prv_encoded = key_encryption.encrypt(prv_encoded)
        except ImportError:
            pass

        # Create certificate record (CSR only, no cert yet)
        certificate = Certificate(
            refid=str(uuid.uuid4()),
            descr=descr,
            caref=None,  # Not signed yet
            csr=base64.b64encode(csr_pem).decode('utf-8'),
            prv=prv_encoded,
            subject=csr.subject.rfc4514_string(),
            san_dns=json.dumps(san_dns) if san_dns else None,
            san_ip=json.dumps(san_ip) if san_ip else None,
            san_email=json.dumps(san_email) if san_email else None,
            san_uri=json.dumps(san_uri) if san_uri else None,
            san_upn=json.dumps(san_upn) if san_upn else None,
            imported_from='csr_generated',
            created_by=username
        )

        db.session.add(certificate)
        try:
            db.session.commit()
        except Exception as _commit_err:
            db.session.rollback()
            logger.error(f"Commit failed in services/cert/mixins/csr.py:103: {_commit_err}", exc_info=True)
            raise

        # Audit log
        from services.audit_service import AuditService
        AuditService.log_csr('csr_generated', certificate, f'Generated CSR: {descr}')

        # Save files
        csr_path = cert_csr_path(certificate)
        with open(csr_path, 'wb') as f:
            f.write(csr_pem)

        mirror_private_key(
            cert_key_path(certificate),
            key_pem,
            context=f"CSR certificate {certificate.id}",
        )

        return certificate

    @staticmethod
    def sign_csr(
        cert_id: int,
        caref: str,
        cert_type: str = 'server_cert',
        validity_days: int = 397,
        digest: str = 'sha256',
        username: str = 'system',
        extra_ekus: list = None,
        allow_sensitive_ekus: bool = False,
        template_id: int = None,
    ) -> Certificate:
        """
        Sign a CSR with a CA

        Args:
            cert_id: Certificate ID (with CSR)
            caref: CA refid to sign with
            cert_type: Certificate type
            validity_days: Validity in days
            digest: Hash algorithm
            username: User signing
            extra_ekus: Additional EKU OIDs
            template_id: Certificate template bound to the issuance context
                (an ACME profile): its KU/EKU govern the leaf and the
                certificate records the link, as on the issue form

        Returns:
            Updated Certificate with signed cert (or new CA record for intermediate_ca)
        """
        # Get certificate with CSR
        certificate = db.session.get(Certificate, cert_id)
        if not certificate:
            raise ValueError("Certificate not found")

        if not certificate.csr:
            raise ValueError("Certificate has no CSR")

        if certificate.crt:
            raise ValueError("Certificate already signed")

        # Get CA
        ca = CA.query.filter_by(refid=caref).first()
        if not ca:
            raise ValueError(f"CA not found: {caref}")

        if not ca.has_private_key:
            raise ValueError("CA has no private key")

        if not ca.crt:
            raise ValueError("CA is awaiting its certificate")

        if ca.offline:
            raise ValueError("CA is offline")

        if ca.revoked_in_chain:
            raise ValueError("CA is revoked and can no longer sign")

        # Load CA cert and key
        ca_cert_pem = base64.b64decode(ca.crt)
        ca_cert = x509.load_pem_x509_certificate(ca_cert_pem, default_backend())

        from services.hsm.ca_key_loader import get_ca_signing_key
        ca_private_key = get_ca_signing_key(ca)

        # Load CSR - handle both raw PEM and base64-encoded PEM
        csr_data = certificate.csr
        if csr_data.startswith('-----BEGIN'):
            csr_pem = csr_data.encode('utf-8')
        else:
            csr_pem = base64.b64decode(csr_data)

        # RFC 2986 §4.2 — validate the CSR's self-signature before signing.
        # cryptography.load_pem_x509_csr does NOT verify the signature, so a
        # tampered/forged CSR (POP failure) would otherwise be silently signed.
        try:
            csr_obj = x509.load_pem_x509_csr(csr_pem, default_backend())
            if not csr_obj.is_signature_valid:
                raise ValueError("CSR signature is invalid (proof-of-possession failed)")
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Failed to verify CSR signature: {e}")

        # Sign CSR
        cdp_urls = [url.replace('{ca_refid}', ca.url_ref) for url in ca.get_cdp_urls()] if ca.cdp_enabled else None
        ocsp_urls = ca.get_ocsp_urls() if ca.ocsp_enabled else None
        aia_ca_issuers_urls = [url.replace('{ca_refid}', ca.url_ref) for url in ca.get_aia_urls()] if ca.aia_ca_issuers_enabled else None
        cps_uri = ca.cps_uri if ca.cps_enabled and ca.cps_uri else None
        cps_oid = ca.cps_oid if cps_uri else None

        # A template bound to the issuance context (ACME profile, #327
        # follow-up). A template deleted after being bound must not break
        # issuance: it is simply not applied, like a removed ACME profile.
        template = None
        template_ext = None
        if template_id:
            from models.certificate_template import CertificateTemplate
            from services.template_service import template_extensions
            template = db.session.get(CertificateTemplate, template_id)
            if template is None:
                logger.warning(
                    "sign_csr: template %s no longer exists, signing without it",
                    template_id,
                )
            else:
                template_ext = template_extensions(template)

        cert_pem = TrustStoreService.sign_csr(
            csr_pem=csr_pem,
            ca_cert=ca_cert,
            ca_private_key=ca_private_key,
            validity_days=validity_days,
            digest=digest,
            cert_type=cert_type,
            cdp_urls=cdp_urls,
            ocsp_urls=ocsp_urls,
            aia_ca_issuers_urls=aia_ca_issuers_urls,
            cps_uri=cps_uri,
            cps_oid=cps_oid,
            ocsp_must_staple=getattr(certificate, 'ocsp_must_staple', False) or False,
            extra_ekus=extra_ekus,
            allow_sensitive_ekus=allow_sensitive_ekus,
            template_ext=template_ext,
        )

        # Parse signed certificate
        cert = x509.load_pem_x509_certificate(cert_pem, default_backend())

        # Extract subject and SANs
        subject_str = cert.subject.rfc4514_string() if cert.subject else None

        # From the subject OBJECT -- see utils.dn_parse.subject_common_name for
        # why splitting rfc4514_string() picked the WRONG commonName.
        cn_value = subject_common_name(cert.subject)

        # Extract SANs
        san_dns_list = []
        san_ip_list = []
        san_email_list = []
        try:
            san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
            for name in san_ext.value:
                if isinstance(name, x509.DNSName):
                    san_dns_list.append(name.value)
                elif isinstance(name, x509.IPAddress):
                    san_ip_list.append(str(name.value))
                elif isinstance(name, x509.RFC822Name):
                    san_email_list.append(name.value)
        except x509.ExtensionNotFound:
            pass

        # Fallback: use first SAN DNS as CN for sorting if no CN in subject
        if not cn_value and san_dns_list:
            cn_value = san_dns_list[0]
        if not cn_value and certificate.descr:
            cn_value = certificate.descr

        # Update certificate record
        certificate.caref = caref
        # Only the request that still sees the row unsigned may store the
        # certificate: two workers signing the same CSR would otherwise both
        # issue, the second overwriting the first's certificate
        claimed = db.session.query(Certificate).filter(
            Certificate.id == certificate.id,
            (Certificate.crt.is_(None)) | (Certificate.crt == ''),
        ).update({Certificate.crt: base64.b64encode(cert_pem).decode('utf-8')},
                 synchronize_session=False)
        if claimed != 1:
            db.session.rollback()
            raise ValueError('CSR was signed by another request')
        certificate.crt = base64.b64encode(cert_pem).decode('utf-8')
        certificate.cert_type = cert_type
        certificate.descr = settle_csr_descr(certificate.descr, cn_value)
        certificate.subject = subject_str if subject_str else None
        certificate.subject_cn = cn_value
        certificate.issuer = cert.issuer.rfc4514_string()
        certificate.serial_number = str(cert.serial_number)
        certificate.valid_from = cert.not_valid_before
        certificate.valid_to = cert.not_valid_after

        # Keep the template link and record the divergences from its
        # defaults (#258), as the issue form and approval paths do. The key
        # is the requester's own, so it diverges whenever it is not the
        # template's declared type.
        if template is not None:
            from services.template_service import compute_template_overrides
            certificate.template_id = template.id
            certificate.template_overrides = compute_template_overrides(
                template,
                key_type=_csr_key_type_label(csr_obj.public_key()),
                validity_days=validity_days,
                digest=digest,
            )

        # Store SANs
        if san_dns_list:
            certificate.san_dns = json.dumps(san_dns_list)
        if san_ip_list:
            certificate.san_ip = json.dumps(san_ip_list)
        if san_email_list:
            certificate.san_email = json.dumps(san_email_list)

        # Increment CA serial
        ca.serial = (ca.serial or 0) + 1

        # If signing as intermediate CA, create a CA record
        new_ca = None
        if cert_type == 'intermediate_ca':
            # Get private key from the CSR certificate record (if it was generated in UCM)
            prv = certificate.prv if certificate.prv else None

            # Extract SKI from signed cert
            ski_hex = None
            try:
                ski_ext = cert.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_KEY_IDENTIFIER)
                ski_hex = ski_ext.value.digest.hex(':').upper()
            except x509.ExtensionNotFound:
                pass

            # Extract pathLength from BasicConstraints
            path_length = None
            try:
                bc_ext = cert.extensions.get_extension_for_oid(x509.oid.ExtensionOID.BASIC_CONSTRAINTS)
                path_length = bc_ext.value.path_length
            except x509.ExtensionNotFound:
                pass

            new_ca = CA(
                refid=str(uuid.uuid4()),
                descr=certificate.descr or cn_value or 'Intermediate CA',
                crt=base64.b64encode(cert_pem).decode('utf-8'),
                prv=prv,
                serial=0,
                caref=caref,
                subject=subject_str,
                issuer=cert.issuer.rfc4514_string(),
                serial_number=str(cert.serial_number),
                ski=ski_hex,
                valid_from=cert.not_valid_before,
                valid_to=cert.not_valid_after,
                path_length=path_length,
                imported_from='csr_signed',
                created_by=username,
            )
            db.session.add(new_ca)

            # Remove the certificate record — it's now a CA
            db.session.delete(certificate)

        try:
            db.session.commit()
        except Exception as _commit_err:
            db.session.rollback()
            logger.error(f"Commit failed in services/cert/mixins/csr.py:303: {_commit_err}", exc_info=True)
            raise

        # A request queued for approval and then signed directly is closed
        # as approved by the signer (no other approver could do more)
        from services.approval_gate import resolve_moot_requests
        resolve_moot_requests('csr', 'csr_id', cert_id, outcome='approved', username=username,
                              certificate_id=None if new_ca else certificate.id,
                              reason='Signed directly')
        # Audit log with centralized service
        from services.audit_service import AuditService
        if new_ca:
            AuditService.log_ca('ca_created', new_ca, f'Intermediate CA created from signed CSR: {new_ca.descr}')
            # Save CA cert file
            ca_path = ca_cert_path(new_ca)
            with open(ca_path, 'wb') as f:
                f.write(cert_pem)
            if new_ca.prv:
                key_data = load_pem_bytes(new_ca.prv, context=f"CA {new_ca.id}")
                mirror_private_key(
                    ca_key_path(new_ca), key_data, context=f"CA {new_ca.id}"
                )
            return new_ca
        else:
            AuditService.log_certificate('csr_signed', certificate, f'Signed CSR: {certificate.descr}')
            # Save signed certificate
            cert_path = cert_cert_path(certificate)
            with open(cert_path, 'wb') as f:
                f.write(cert_pem)
            from services.webhook_service import emit_cert_issued
            emit_cert_issued(certificate.to_dict(), ca_refid=certificate.caref)
            return certificate

    @staticmethod
    def complete_external_csr(
        certificate: Certificate,
        cert: x509.Certificate,
        cert_pem: bytes,
        caref: Optional[str] = None,
        descr: Optional[str] = None,
        key_pem: Optional[bytes] = None,
        username: str = 'system',
        commit: bool = True,
    ) -> Certificate:
        """Attach a certificate issued elsewhere to the pending CSR it answers.

        A CSR generated here and signed by an external CA came back as a
        separate, keyless record when the certificate was imported, since
        nothing tied the two together (#341). The certificate's public key
        must be the CSR's; the record then holds the certificate and keeps
        its private key, so the certificate exports with it. A key that
        arrives with the certificate is kept only when the record has none.

        Raises ValueError when the record is not a pending CSR or the keys
        differ. With commit=False the caller owns the transaction (smart
        import commits once for the whole bundle).
        """
        if not certificate.csr or certificate.crt:
            raise ValueError("Not a pending CSR")

        csr_obj = x509.load_pem_x509_csr(_csr_pem_bytes(certificate.csr), default_backend())
        if _spki_der(csr_obj.public_key()) != _spki_der(cert.public_key()):
            raise ValueError("Certificate public key does not match the CSR")

        cn_value = subject_common_name(cert.subject)

        san_dns_list, san_ip_list, san_email_list, san_uri_list = [], [], [], []
        try:
            san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
            for name in san_ext.value:
                if isinstance(name, x509.DNSName):
                    san_dns_list.append(name.value)
                elif isinstance(name, x509.IPAddress):
                    san_ip_list.append(str(name.value))
                elif isinstance(name, x509.RFC822Name):
                    san_email_list.append(name.value)
                elif isinstance(name, x509.UniformResourceIdentifier):
                    san_uri_list.append(name.value)
        except x509.ExtensionNotFound:
            pass
        if not cn_value and san_dns_list:
            cn_value = san_dns_list[0]

        ski_hex = aki_hex = None
        try:
            ski_hex = cert.extensions.get_extension_for_class(
                x509.SubjectKeyIdentifier).value.key_identifier.hex(':').upper()
        except x509.ExtensionNotFound:
            pass
        try:
            aki = cert.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier).value
            if aki.key_identifier:
                aki_hex = aki.key_identifier.hex(':').upper()
        except x509.ExtensionNotFound:
            pass

        # Only the request that still sees the row unsigned may store the
        # certificate: two workers signing the same CSR would otherwise both
        # issue, the second overwriting the first's certificate
        claimed = db.session.query(Certificate).filter(
            Certificate.id == certificate.id,
            (Certificate.crt.is_(None)) | (Certificate.crt == ''),
        ).update({Certificate.crt: base64.b64encode(cert_pem).decode('utf-8')},
                 synchronize_session=False)
        if claimed != 1:
            db.session.rollback()
            raise ValueError('CSR was signed by another request')
        certificate.crt = base64.b64encode(cert_pem).decode('utf-8')
        certificate.caref = caref
        certificate.descr = descr or settle_csr_descr(certificate.descr, cn_value)
        certificate.subject = cert.subject.rfc4514_string() or None
        certificate.subject_cn = cn_value or certificate.descr
        certificate.issuer = cert.issuer.rfc4514_string()
        certificate.serial_number = str(cert.serial_number)
        certificate.aki = aki_hex
        certificate.ski = ski_hex
        certificate.valid_from = cert.not_valid_before_utc.replace(tzinfo=None)
        certificate.valid_to = cert.not_valid_after_utc.replace(tzinfo=None)
        certificate.san_dns = json.dumps(san_dns_list) if san_dns_list else None
        certificate.san_ip = json.dumps(san_ip_list) if san_ip_list else None
        certificate.san_email = json.dumps(san_email_list) if san_email_list else None
        certificate.san_uri = json.dumps(san_uri_list) if san_uri_list else None
        certificate.source = 'import'
        if key_pem and not certificate.prv:
            certificate.prv = encrypt_private_key(base64.b64encode(key_pem).decode('utf-8'))
            mirror_private_key(
                cert_key_path(certificate), key_pem,
                context=f"CSR certificate {certificate.id}",
            )

        if commit:
            try:
                db.session.commit()
            except Exception as _commit_err:
                db.session.rollback()
                logger.error(
                    f"Commit failed completing CSR {certificate.id}: {_commit_err}",
                    exc_info=True,
                )
                raise

        with open(cert_cert_path(certificate), 'wb') as f:
            f.write(cert_pem)

        from services.audit_service import AuditService
        AuditService.log_certificate(
            'certificate_imported', certificate,
            f'Certificate issued externally attached to its pending CSR '
            f'(private key {"kept" if certificate.prv else "absent"})',
            username=username,
        )
        return certificate
