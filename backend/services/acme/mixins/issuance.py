"""Certificate issuance mixin for ACME service"""
import json
import logging
from typing import Optional, Tuple, List

from models import db
from models.acme_models import AcmeOrder
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class IssuanceMixin:
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
        
        # Validate CSR matches order identifiers
        csr_domains = self._extract_domains_from_csr(csr)
        order_identifiers = json.loads(order.identifiers)
        order_domains = [id['value'] for id in order_identifiers if id.get('type') == 'dns']
        
        if set(csr_domains) != set(order_domains):
            return False, f"CSR domains {csr_domains} don't match order domains {order_domains}"
        
        # CAA record check (RFC 6844 + RFC 8555 §8.1)
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
                # Use server hostname as default CAA identity
                from flask import request as flask_request
                try:
                    caa_identifiers = [flask_request.host.split(':')[0]]
                except Exception:
                    pass
            
            caa_allowed, caa_reason = check_caa_for_domains(order_domains, caa_identifiers)
            if not caa_allowed:
                logger.warning(f"CAA check failed for order {order_id}: {caa_reason}")
                return False, f"CAA check failed: {caa_reason}"
            logger.debug(f"CAA check passed for {order_domains}: {caa_reason}")
        except ImportError:
            logger.debug("dns.resolver not available, skipping CAA check")
        except Exception as e:
            logger.warning(f"CAA check error (non-blocking): {e}")
        
        # Resolve CA: domain-specific → global default → first available
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
                cert = Certificate.query.get(prev_order.certificate_id)
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
                ca = CA.query.get(ca_id)
                if ca and ca.prv:
                    return ca.refid
        
        # Check DNS domain-specific CA
        for domain in domains:
            result = find_provider_for_domain(domain)
            if result and result.get('issuing_ca_id'):
                ca = CA.query.get(result['issuing_ca_id'])
                if ca and ca.prv:
                    return ca.refid
        
        # Fall back to global default
        ca_id_cfg = SystemConfig.query.filter_by(key='acme.issuing_ca_id').first()
        if ca_id_cfg and ca_id_cfg.value:
            ca = CA.query.filter_by(refid=ca_id_cfg.value).first()
            if not ca:
                try:
                    ca = CA.query.get(int(ca_id_cfg.value))
                except (ValueError, TypeError):
                    pass
            if ca and ca.prv:
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
            # Find first CA with private key
            ca = CA.query.filter(CA.prv.isnot(None)).first()
        
        if not ca:
            return False, None, "No CA available for signing"
        
        if not ca.prv:
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
