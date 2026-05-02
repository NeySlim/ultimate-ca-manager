"""Certificate lifecycle mixin — create, revoke, delete, list, get"""
import base64
import uuid
import json
import logging
from datetime import datetime, timedelta, timezone as _tz
from typing import Dict, List, Optional

from cryptography import x509
from cryptography.hazmat.backends import default_backend

from models import db, CA, Certificate, CertificateTemplate
from services.trust_store import TrustStoreService
from utils.file_naming import cert_cert_path, cert_key_path, cert_csr_path, cleanup_old_files
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

try:
    from security.encryption import decrypt_private_key, encrypt_private_key
    HAS_ENCRYPTION = True
except ImportError:
    HAS_ENCRYPTION = False

    def decrypt_private_key(data):
        return data

    def encrypt_private_key(data):
        return data


class LifecycleMixin:

    @staticmethod
    def create_certificate(
        descr: str,
        caref: str,
        dn: Dict[str, str],
        cert_type: str = 'server_cert',
        key_type: str = '2048',
        validity_days: int = 397,
        digest: str = 'sha256',
        san_dns: Optional[List[str]] = None,
        san_ip: Optional[List[str]] = None,
        san_uri: Optional[List[str]] = None,
        san_email: Optional[List[str]] = None,
        ocsp_uri: Optional[str] = None,
        private_key_location: str = 'stored',
        template_id: Optional[int] = None,
        username: str = 'system',
        ocsp_must_staple: bool = False,
    ) -> Certificate:
        """
        Create a certificate signed by a CA

        Args:
            descr: Description
            caref: CA refid
            dn: Distinguished Name
            cert_type: usr_cert, server_cert, combined_server_client, ca_cert
            key_type: Key type
            validity_days: Validity in days
            digest: Hash algorithm
            san_dns: DNS SANs
            san_ip: IP SANs
            san_uri: URI SANs
            san_email: Email SANs
            ocsp_uri: OCSP responder URI
            private_key_location: 'stored' or 'download_only'
            template_id: Certificate template ID (optional)
            username: User creating certificate
            ocsp_must_staple: Enable OCSP Must-Staple extension

        Returns:
            Certificate model instance
        """
        # Apply template if provided
        if template_id:
            template = CertificateTemplate.query.get(template_id)
            if template:
                # Use template defaults if values not explicitly provided
                key_type = key_type if key_type != '2048' else template.key_type or key_type
                validity_days = validity_days if validity_days != 397 else template.validity_days or validity_days
                digest = digest if digest != 'sha256' else template.digest or digest

        # Validate SAN emails if provided
        if san_email:
            from services.cert.mixins.inspection import InspectionMixin
            invalid_emails = [email for email in san_email if not InspectionMixin.validate_email(email)]
            if invalid_emails:
                raise ValueError(f"Invalid email address(es) in SAN: {', '.join(invalid_emails)}")

        # Get CA
        ca = CA.query.filter_by(refid=caref).first()
        if not ca:
            raise ValueError(f"CA not found: {caref}")

        if not ca.has_private_key:
            raise ValueError("CA has no private key - cannot sign certificates")

        # Load CA certificate
        ca_cert_pem = base64.b64decode(ca.crt)
        ca_cert = x509.load_pem_x509_certificate(ca_cert_pem, default_backend())

        # Load CA signing key (local or HSM-backed)
        from services.hsm.ca_key_loader import get_ca_signing_key
        try:
            ca_private_key = get_ca_signing_key(ca)
        except Exception as e:
            raise ValueError(f"Failed to load CA signing key: {e}")

        # Build subject
        subject = TrustStoreService.build_subject(dn)

        # Prepare CDP URLs if CA has it enabled
        cdp_urls = None
        if ca.cdp_enabled:
            cdp_urls = [url.replace('{ca_refid}', ca.refid) for url in ca.get_cdp_urls()]
            if not cdp_urls:
                cdp_urls = None

        # Prepare OCSP URLs if CA has it enabled
        ocsp_urls = None
        if ca.ocsp_enabled:
            ocsp_urls = ca.get_ocsp_urls()
            if not ocsp_urls:
                ocsp_urls = None

        # Prepare AIA CA Issuers URLs if CA has it enabled
        aia_ca_issuers_urls = None
        if ca.aia_ca_issuers_enabled:
            aia_ca_issuers_urls = [url.replace('{ca_refid}', ca.refid) for url in ca.get_aia_urls()]
            if not aia_ca_issuers_urls:
                aia_ca_issuers_urls = None

        # CPS
        cps_uri = ca.cps_uri if ca.cps_enabled and ca.cps_uri else None
        cps_oid = ca.cps_oid if cps_uri else None

        # Clamp certificate validity to CA's expiry
        ca_not_after = ca_cert.not_valid_after_utc
        cert_not_after = datetime.now(_tz.utc) + timedelta(days=validity_days)
        if cert_not_after > ca_not_after:
            validity_days = max(1, (ca_not_after - datetime.now(_tz.utc)).days)
            logger.warning(f"Certificate validity clamped to {validity_days} days (CA expires sooner)")

        # Create certificate
        cert_pem, key_pem = TrustStoreService.create_certificate(
            subject=subject,
            ca_cert=ca_cert,
            ca_private_key=ca_private_key,
            cert_type=cert_type,
            validity_days=validity_days,
            digest=digest,
            key_type=key_type,
            san_dns=san_dns,
            san_ip=san_ip,
            san_uri=san_uri,
            san_email=san_email,
            ocsp_uris=ocsp_urls,
            cdp_urls=cdp_urls,
            aia_ca_issuers_urls=aia_ca_issuers_urls,
            cps_uri=cps_uri,
            cps_oid=cps_oid,
            ocsp_must_staple=ocsp_must_staple,
        )

        # Parse certificate
        cert = x509.load_pem_x509_certificate(cert_pem, default_backend())

        # Increment CA serial
        ca.serial = (ca.serial or 0) + 1

        # Encrypt private key if encryption is enabled and key is stored
        prv_encoded = None
        if private_key_location == 'stored':
            prv_encoded = base64.b64encode(key_pem).decode('utf-8')
            prv_encoded = encrypt_private_key(prv_encoded)

        # Create certificate record
        certificate = Certificate(
            refid=str(uuid.uuid4()),
            descr=descr,
            caref=caref,
            crt=base64.b64encode(cert_pem).decode('utf-8'),
            prv=prv_encoded,
            cert_type=cert_type,
            subject=cert.subject.rfc4514_string(),
            issuer=cert.issuer.rfc4514_string(),
            serial_number=str(cert.serial_number),
            valid_from=cert.not_valid_before_utc,
            valid_to=cert.not_valid_after_utc,
            # SANs
            san_dns=json.dumps(san_dns) if san_dns else None,
            san_ip=json.dumps(san_ip) if san_ip else None,
            san_email=json.dumps(san_email) if san_email else None,
            san_uri=json.dumps(san_uri) if san_uri else None,
            # OCSP and key location
            ocsp_uri=ocsp_uri,
            ocsp_must_staple=ocsp_must_staple,
            private_key_location=private_key_location,
            # Template reference
            template_id=template_id,
            # Other fields
            revoked=False,
            imported_from='generated',
            created_by=username
        )

        db.session.add(certificate)
        db.session.commit()

        # Audit log
        from services.audit_service import AuditService
        AuditService.log_certificate('cert_created', certificate, f'Created certificate: {descr}')

        # Submit to Certificate Transparency if enabled
        try:
            from models import SystemConfig
            ct_enabled = SystemConfig.query.filter_by(key='ct_enabled').first()
            ct_auto = SystemConfig.query.filter_by(key='ct_auto_submit').first()
            if ct_enabled and ct_enabled.value == 'true' and ct_auto and ct_auto.value == 'true':
                ct_log_urls_config = SystemConfig.query.filter_by(key='ct_log_urls').first()
                ct_log_urls = json.loads(ct_log_urls_config.value) if ct_log_urls_config and ct_log_urls_config.value else None

                chain = [cert_pem.decode('utf-8') if isinstance(cert_pem, bytes) else cert_pem]
                ca_pem_str = ca_cert_pem.decode('utf-8') if isinstance(ca_cert_pem, bytes) else ca_cert_pem
                chain.append(ca_pem_str)

                from utils.ct_client import collect_scts
                scts = collect_scts(chain, ct_log_urls)
                if scts:
                    config = SystemConfig(key=f'cert_scts_{certificate.id}', value=json.dumps(scts))
                    db.session.add(config)
                    try:
                        db.session.commit()
                    except Exception:
                        db.session.rollback()
                    logger.info(f"Certificate {certificate.id} submitted to {len(scts)} CT log(s)")
        except Exception as e:
            logger.warning(f"CT auto-submission failed for cert {certificate.id}: {e}")

        # Save files
        cert_path = cert_cert_path(certificate)
        with open(cert_path, 'wb') as f:
            f.write(cert_pem)

        key_path = cert_key_path(certificate)
        with open(key_path, 'wb') as f:
            f.write(key_pem)
        key_path.chmod(0o600)

        return certificate

    @staticmethod
    def revoke_certificate(
        cert_id: int,
        reason: str = 'unspecified',
        username: str = 'system'
    ) -> Certificate:
        """
        Revoke a certificate

        Args:
            cert_id: Certificate ID
            reason: Revocation reason
            username: User revoking

        Returns:
            Updated certificate
        """
        certificate = Certificate.query.get(cert_id)
        if not certificate:
            raise ValueError("Certificate not found")

        if certificate.revoked:
            raise ValueError("Certificate already revoked")

        certificate.revoked = True
        certificate.revoked_at = utc_now()
        certificate.revoke_reason = reason

        db.session.commit()

        # Audit log
        from services.audit_service import AuditService
        AuditService.log_certificate('cert_revoked', certificate, f'Revoked certificate: {certificate.descr} - Reason: {reason}')

        # Auto-generate CRL if CA has CDP enabled
        ca = CA.query.filter_by(refid=certificate.caref).first()
        if ca and ca.cdp_enabled:
            from services.crl_service import CRLService
            try:
                CRLService.generate_crl(ca.id, username=username)
            except Exception as e:
                # Log error but don't fail revocation
                AuditService.log_ca('crl_auto_generation_failed', ca, f'Failed to auto-generate CRL after revocation: {str(e)}', success=False)

        # Invalidate OCSP cache if CA has OCSP enabled
        if ca and ca.ocsp_enabled:
            try:
                from models import OCSPResponse
                # Delete cached OCSP response for this certificate
                OCSPResponse.query.filter_by(
                    ca_id=ca.id,
                    cert_serial=certificate.serial
                ).delete()
                db.session.commit()
                logger.info(f"Invalidated OCSP cache for certificate {certificate.refid}")
            except Exception as e:
                logger.error(f"Failed to invalidate OCSP cache: {e}")

        return certificate

    @staticmethod
    def delete_certificate(cert_id: int, username: str = 'system') -> bool:
        """
        Delete a certificate

        Args:
            cert_id: Certificate ID
            username: User deleting

        Returns:
            True if deleted
        """
        certificate = Certificate.query.get(cert_id)
        if not certificate:
            return False

        # Delete files (cleanup old UUID names first, then new names)
        cleanup_old_files(certificate=certificate)
        cert_path = cert_cert_path(certificate)
        csr_path = cert_csr_path(certificate)
        key_path = cert_key_path(certificate)

        for path in [cert_path, csr_path, key_path]:
            if path.exists():
                path.unlink()

        # Audit log
        from services.audit_service import AuditService
        AuditService.log_certificate('cert_deleted', certificate, f'Deleted certificate: {certificate.descr}')

        # Delete from database
        db.session.delete(certificate)
        db.session.commit()

        return True
