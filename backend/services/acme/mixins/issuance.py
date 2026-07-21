"""Certificate issuance mixin for ACME service"""
import json
import logging
from typing import Optional, Tuple, List

from models import db
from models.acme_models import AcmeOrder
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class IssuanceMixin:
    def _caa_request_context(self, order):
        """Return the RFC 8657 account URL and validation method per DNS authz."""
        account_url = f"{self.base_url}/acme/acct/{order.account_id}"
        validation_methods = {}

        for authorization in order.authorizations:
            identifier = authorization.identifier_obj
            if identifier.get('type') != 'dns':
                continue

            domain = identifier.get('value', '')
            if authorization.wildcard and not domain.startswith('*.'):
                domain = f"*.{domain}"

            valid_methods = {
                challenge.type.lower()
                for challenge in authorization.challenges
                if challenge.status == 'valid' and challenge.type
            }
            validation_methods[domain] = (
                next(iter(valid_methods)) if len(valid_methods) == 1 else None
            )
            if len(valid_methods) != 1:
                logger.warning(
                    "Cannot determine a unique ACME validation method for %s",
                    domain,
                )

        return account_url, validation_methods

    def finalize_order(
        self,
        order_id: str,
        csr_pem: str,
        ca_refid: str = None
    ) -> Tuple[bool, Optional[str]]:
        """Finalize order and issue certificate
        
        Args:
            order_id: Order identifier
            csr_pem: PEM-encoded Certificate Signing Request
            ca_refid: CA to sign with (optional, resolved from domain config → global default → first available)
            
        Returns:
            Tuple of (success, error_message)
        """
        order = self.get_order(order_id)
        
        if not order:
            return False, "Order not found"
        
        if order.status != "ready":
            return False, f"Order status is {order.status}, must be 'ready'"
        
        # Parse CSR
        try:
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            
            csr = x509.load_pem_x509_csr(csr_pem.encode(), default_backend())
        except Exception as e:
            return False, f"Invalid CSR: {str(e)}"
        
        # Validate CSR matches order identifiers (RFC 4343: DNS names case-insensitive, RFC 8738: IP identifiers)
        csr_domains = self._extract_domains_from_csr(csr)
        csr_ips = self._extract_ips_from_csr(csr)
        order_identifiers = json.loads(order.identifiers)
        order_domains = [id['value'] for id in order_identifiers if id.get('type') == 'dns']
        order_ips = [id['value'] for id in order_identifiers if id.get('type') == 'ip']

        # Validate DNS identifiers
        csr_domains_norm = {d.lower().rstrip('.') for d in csr_domains}
        order_domains_norm = {d.lower().rstrip('.') for d in order_domains}
        if csr_domains_norm != order_domains_norm:
            return False, f"CSR domains {sorted(csr_domains_norm)} don't match order domains {sorted(order_domains_norm)}"
        
        # Validate IP identifiers (RFC 8738)
        csr_ips_norm = {ip for ip in csr_ips}
        order_ips_norm = {ip for ip in order_ips}
        if csr_ips_norm != order_ips_norm:
            return False, f"CSR IPs {sorted(csr_ips_norm)} don't match order IPs {sorted(order_ips_norm)}"
        
        # CAA record check (RFC 6844 + RFC 8555 §8.1) - only for DNS identifiers
        if order_domains:
            try:
                from utils.caa_checker import check_caa_for_domains
                from models import SystemConfig
                
                caa_identifiers = []
                try:
                    caa_cfg = SystemConfig.query.filter_by(key='acme_caa_identifiers').first()
                    if caa_cfg and caa_cfg.value:
                        caa_identifiers = [v.strip() for v in caa_cfg.value.split(',') if v.strip()]
                except Exception:
                    pass
                
                if not caa_identifiers:
                    # Default CAA identity = the public hostname the directory
                    # advertises (configured acme_public_vhost, else request host)
                    from flask import request as flask_request
                    from utils.acme_public_url import get_acme_public_host
                    try:
                        caa_identifiers = [get_acme_public_host(flask_request)]
                    except Exception:
                        pass
                
                account_url, validation_methods = self._caa_request_context(order)
                caa_allowed, caa_reason = check_caa_for_domains(
                    order_domains,
                    caa_identifiers,
                    account_url=account_url,
                    validation_methods=validation_methods,
                )
                if not caa_allowed:
                    logger.warning(f"CAA check failed for order {order_id}: {caa_reason}")
                    return False, f"CAA check failed: {caa_reason}"
                logger.debug(f"CAA check passed for {order_domains}: {caa_reason}")
            except ImportError:
                # dnspython is a hard dependency; if it's genuinely missing we
                # cannot check CAA, and silently skipping would let issuance
                # proceed against a CAA record that forbids it. Fail closed.
                logger.error("CAA check unavailable: dns.resolver import failed")
                return False, "CAA check failed: DNS resolver unavailable"
            except Exception as e:
                logger.warning(f"CAA check error: {e}")
                return False, "CAA check failed: DNS lookup error"
        
        # Resolve CA: domain-specific → global default → first available
        # IP-only orders have no domains: skips the per-domain mappings and
        # resolves straight to the global default (acme.issuing_ca_id)
        if not ca_refid:
            ca_refid = self._resolve_ca_for_domains(order_domains)
        
        # Sign certificate with UCM CA
        success, cert_id, error = self._sign_certificate_with_ca(
            order=order,
            csr_pem=csr_pem,
            ca_refid=ca_refid
        )
        
        if not success:
            order.status = "invalid"
            order.error = json.dumps({
                "type": "urn:ietf:params:acme:error:serverInternal",
                "detail": error
            })
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                logger.error(f"DB commit failed: {e}")
                raise
            return False, error
        
        # Update order status
        order.status = "valid"
        order.csr = csr_pem
        order.certificate_id = cert_id
        order.certificate_url = f"{self.base_url}/acme/cert/{order.order_id}"
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"DB commit failed: {e}")
            raise
        
        # Auto-supersede: revoke previous certs for same domains if enabled
        self._auto_supersede(order, cert_id)

        try:
            from models import Certificate
            from services.webhook_service import emit_cert_issued
            issued = db.session.get(Certificate, cert_id)
            if issued:
                emit_cert_issued(issued.to_dict(), ca_refid=issued.caref)
        except Exception as e:
            logger.error(f"Webhook emit (ACME issuance) failed: {e}")

        return True, None
    
    def _auto_supersede(self, new_order, new_cert_id: int):
        """Revoke previous certificates for the same domains if revoke_on_renewal is enabled."""
        try:
            from models import SystemConfig, Certificate
            from models.acme_models import AcmeOrder
            
            setting = SystemConfig.query.filter_by(key='acme.revoke_on_renewal').first()
            if not setting or setting.value != 'true':
                return
            
            # Find previous orders with same identifiers and account
            previous_orders = AcmeOrder.query.filter(
                AcmeOrder.account_id == new_order.account_id,
                AcmeOrder.identifiers == new_order.identifiers,
                AcmeOrder.certificate_id.isnot(None),
                AcmeOrder.certificate_id != new_cert_id,
                AcmeOrder.status == 'valid'
            ).all()
            
            if not previous_orders:
                return
            
            from services.cert_service import CertificateService
            for prev_order in previous_orders:
                cert = db.session.get(Certificate, prev_order.certificate_id)
                if cert and not cert.revoked:
                    try:
                        CertificateService.revoke_certificate(
                            cert_id=cert.id,
                            reason='superseded',
                            username='system'
                        )
                        logger.info(f"Auto-superseded certificate {cert.id} (replaced by {new_cert_id})")
                    except Exception as e:
                        logger.warning(f"Failed to supersede certificate {cert.id}: {e}")
        except Exception as e:
            logger.warning(f"Auto-supersede check failed: {e}")
    
    def _extract_ips_from_csr(self, csr) -> List[str]:
        """Extract IP addresses from CSR Subject Alternative Names (RFC 8738)
        
        Args:
            csr: x509.CertificateSigningRequest object
            
        Returns:
            List of IP address strings
        """
        from utils.acme_ip import extract_ip_from_csr_san
        return extract_ip_from_csr_san(csr)
    
    def _extract_domains_from_csr(self, csr) -> List[str]:
        """Extract domain names from CSR
        
        Args:
            csr: x509.CertificateSigningRequest object
            
        Returns:
            List of domain names
        """
        from cryptography import x509
        
        domains = []
        
        # Get CN from subject
        try:
            cn = csr.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value
            domains.append(cn)
        except Exception:
            pass
        
        # Get SANs
        try:
            san_ext = csr.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
            for name in san_ext.value:
                if isinstance(name, x509.DNSName):
                    if name.value not in domains:
                        domains.append(name.value)
        except Exception:
            pass
        
        return domains
    
    def _resolve_ca_for_domains(self, domains: list) -> Optional[str]:
        """Resolve which CA should sign for the given domains.
        
        Resolution order:
        1. Local ACME domain mapping (acme_local_domains table)
        2. DNS domain-specific CA (acme_domains.issuing_ca_id)
        3. Global default from acme.issuing_ca_id config
        4. None (will fall back to first available CA in _sign_certificate_with_ca)
        """
        from api.v2.acme_local_domains import find_local_domain_ca
        from api.v2.acme_domains import find_provider_for_domain
        from models import SystemConfig, CA
        
        # Check local ACME domain mapping first
        for domain in domains:
            ca_id = find_local_domain_ca(domain)
            if ca_id:
                ca = db.session.get(CA, ca_id)
                if ca and ca.has_private_key:
                    return ca.refid
        
        # Check DNS domain-specific CA
        for domain in domains:
            result = find_provider_for_domain(domain)
            if result and result.get('issuing_ca_id'):
                ca = db.session.get(CA, result['issuing_ca_id'])
                if ca and ca.has_private_key:
                    return ca.refid
        
        # Fall back to global default
        ca_id_cfg = SystemConfig.query.filter_by(key='acme.issuing_ca_id').first()
        if ca_id_cfg and ca_id_cfg.value:
            ca = CA.query.filter_by(refid=ca_id_cfg.value).first()
            if not ca:
                try:
                    ca = db.session.get(CA, int(ca_id_cfg.value))
                except (ValueError, TypeError):
                    pass
            if ca and ca.has_private_key:
                return ca.refid
        
        return None
    
    def _sign_certificate_with_ca(
        self,
        order: AcmeOrder,
        csr_pem: str,
        ca_refid: str = None
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        """Sign CSR with UCM CA
        
        Args:
            order: AcmeOrder object
            csr_pem: PEM-encoded CSR
            ca_refid: CA refid (optional)
            
        Returns:
            Tuple of (success, certificate_id, error_message)
        """
        from models import CA, Certificate
        import secrets
        import base64
        
        # Get CA (use first available if not specified)
        if ca_refid:
            ca = CA.query.filter_by(refid=ca_refid).first()
        else:
            # Find first CA with a usable signing key (local or HSM)
            ca = CA.query.filter(
                CA.prv.isnot(None) | CA.hsm_key_id.isnot(None)
            ).first()
        
        if not ca:
            return False, None, "No CA available for signing"
        
        if not ca.has_private_key:
            return False, None, f"CA {ca.refid} has no private key"
        
        # Extract CN from CSR for better description
        descr = f"ACME Certificate - Order {order.order_id}"
        try:
            from cryptography.hazmat.backends import default_backend
            from cryptography import x509
            csr_bytes = csr_pem.encode() if isinstance(csr_pem, str) else csr_pem
            csr = x509.load_pem_x509_csr(csr_bytes, default_backend())
            
            # Try to get CN from subject
            cn = None
            for attr in csr.subject:
                if attr.oid == x509.oid.NameOID.COMMON_NAME:
                    cn = attr.value
                    break
            
            # If no CN, try first DNS name from SAN
            if not cn:
                try:
                    san_ext = csr.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
                    for name in san_ext.value:
                        if isinstance(name, x509.DNSName):
                            cn = name.value
                            break
                except Exception:
                    pass
            
            # Use CN as description if found
            if cn:
                descr = cn
        except Exception as e:
            # Keep default description if extraction fails
            pass
        
        # Create certificate record with CSR
        cert = Certificate(
            refid=secrets.token_urlsafe(16),
            descr=descr,
            caref=ca.refid,
            csr=base64.b64encode(csr_pem.encode()).decode('utf-8'),
            cert_type='server_cert',
            source='acme',
            created_by='acme'
        )
        db.session.add(cert)
        db.session.flush()  # Get cert.id
        
        # Sign CSR using existing CertificateService
        try:
            from services.cert_service import CertificateService
            
            signed_cert = CertificateService.sign_csr(
                cert_id=cert.id,
                caref=ca.refid,
                cert_type='server_cert',
                validity_days=90,  # ACME certificates typically 90 days
                digest='sha256',
                username='acme'
            )
            
            return True, signed_cert.id, None
            
        except Exception as e:
            db.session.rollback()
            return False, None, f"Certificate signing failed: {str(e)}"
