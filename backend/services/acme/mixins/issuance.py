"""Certificate issuance mixin for ACME service"""
import ipaddress
import json
import logging
from typing import Optional, Tuple, List

from models import db
from models.acme_models import AcmeOrder
from utils.datetime_utils import utc_now
from utils.csr_extensions import csr_extensions

logger = logging.getLogger(__name__)


def _is_ip_text(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


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
        ca_refid: str = None,
        approval=None,
    ) -> Tuple[bool, Optional[str]]:
        """Finalize order and issue certificate
        
        Args:
            order_id: Order identifier
            csr_pem: PEM-encoded Certificate Signing Request
            ca_refid: CA to sign with (optional, resolved from domain config → global default → first available)
            approval: the approved request this issuance carries out (the
                approval gate is then passed)
            
        Returns:
            Tuple of (success, error_message); success with
            ``self._pending_approval`` set when a policy holds the order for
            approval (it stays ``processing``).
        """
        self._pending_approval = None
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

        # Reject any SAN entry that is not one of the validated identifiers.
        # The per-type extractors above only look at DNSName/IPAddress, so an
        # rfc822Name, otherName/UPN, URI or dirName would otherwise sail past
        # validation and be copied verbatim into the signed certificate by
        # sign_csr — letting a client that only proved control of a DNS name
        # obtain a cert asserting an email address or a Windows UPN it never
        # proved. ACME only ever proves DNS/IP control, so anything else is
        # unauthorized by construction.
        san_ok, san_err = self._validate_csr_san_types(
            csr, order_domains_norm, order_ips_norm
        )
        if not san_ok:
            return False, san_err

        # The SAN check above does not cover the subject, but two subject
        # attributes still reach the issued certificate: sign_csr SYNTHESIZES a
        # SAN from the CN/emailAddress when the CSR carries no SAN extension, and
        # the whole subject is copied verbatim onto the leaf while finalize only
        # ever validated the FIRST CN. Require every CN to be a validated order
        # identifier and forbid any emailAddress RDN.
        subject_ok, subject_err = self._validate_csr_subject(
            csr, order_domains_norm, order_ips_norm
        )
        if not subject_ok:
            return False, subject_err

        # The profile's template may restrict the SAN types (DNS, IP)
        from services.acme import profiles as acme_profiles
        from models.certificate_template import CertificateTemplate
        from services.template_service import allowed_san_types, san_type_refusal
        tpl_id = acme_profiles.issuance_params(getattr(order, 'profile', None)).get('template_id')
        template = db.session.get(CertificateTemplate, tpl_id) if tpl_id else None
        if template is not None:
            refusal = san_type_refusal(
                allowed_san_types(template),
                ['dns'] * bool(order_domains_norm) + ['ip'] * bool(order_ips_norm), template.name)
            if refusal:
                return False, refusal

        # CAA record check (RFC 6844 + RFC 8555 §8.1) - only for DNS identifiers
        if order_domains:
            caa_enforce = False
            try:
                from utils.caa_checker import check_caa_for_domains
                from models import SystemConfig
                
                from services.acme.caa_identities import caa_identities
                caa_identifiers = caa_identities()

                # DNS lookup errors are soft-fail by default (pre-2.200
                # behaviour): air-gapped/split-horizon deployments cannot
                # resolve CAA and were fully broken by fail-closed. Setting
                # acme_caa_enforce=true restores strict semantics.
                try:
                    enforce_cfg = SystemConfig.query.filter_by(key='acme_caa_enforce').first()
                    caa_enforce = bool(enforce_cfg and str(enforce_cfg.value).lower() == 'true')
                except Exception:
                    pass

                account_url, validation_methods = self._caa_request_context(order)
                caa_allowed, caa_reason = check_caa_for_domains(
                    order_domains,
                    caa_identifiers,
                    account_url=account_url,
                    validation_methods=validation_methods,
                    fail_hard=caa_enforce,
                )
                if not caa_allowed:
                    logger.warning(f"CAA check failed for order {order_id}: {caa_reason}")
                    return False, f"CAA check failed: {caa_reason}"
                logger.debug(f"CAA check passed for {order_domains}: {caa_reason}")
            except ImportError:
                if caa_enforce:
                    logger.error("CAA check unavailable: dns.resolver import failed")
                    return False, "CAA check failed (DNS error): resolver unavailable"
                logger.error(
                    "CAA check unavailable (dns.resolver import failed); "
                    "proceeding without CAA check (soft-fail)"
                )
            except Exception as e:
                if caa_enforce:
                    logger.warning(f"CAA check error: {e}")
                    return False, "CAA check failed (DNS error): lookup error"
                logger.warning(f"CAA check error (non-blocking): {e}")
        
        # Resolve CA: domain-specific → global default → first available
        # IP-only orders have no domains: skips the per-domain mappings and
        # resolves straight to the global default (acme.issuing_ca_id)
        if not ca_refid:
            ca_refid = self._resolve_ca_for_domains(order_domains)

        if approval is None:
            held, gate_error = self._approval_gate(order, csr, csr_pem, ca_refid)
            if gate_error:
                self._last_finalize_error_type = 'serverInternal'
                return False, gate_error
            if held is not None:
                self._pending_approval = held
                return True, None

        # Sign certificate with UCM CA
        self._last_signing_exception = None
        success, cert_id, error = self._sign_certificate_with_ca(
            order=order,
            csr_pem=csr_pem,
            ca_refid=ca_refid
        )
        
        if not success:
            if not self._is_request_failure(getattr(self, '_last_signing_exception', None)):
                # Nothing wrong with the request (CA offline or outside its
                # window, signing key unavailable...): the order goes back to
                # `ready` (restore_processing_order) so the client may retry,
                # and the error is reported as serverInternal, not badCSR
                self._last_finalize_error_type = 'serverInternal'
                return False, error
            from services.acme.requested_validity import RequestedValidityError
            self._last_finalize_error_type = (
                'malformed' if isinstance(self._last_signing_exception, RequestedValidityError)
                else 'badCSR')
            order.status = "invalid"
            order.error = json.dumps({
                "type": f"urn:ietf:params:acme:error:{self._last_finalize_error_type}",
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

        # The certificate.issued webhook was emitted by the certificate
        # service when it stored the row (a second emission from here sent
        # every ACME issuance twice)

        return True, None
    
    def _approval_gate(self, order, csr, csr_pem, ca_refid):
        """``(approval, None)`` when a policy holds the order for approval
        (its CSR kept on it, the order left ``processing``), ``(None, None)``
        to issue now, ``(None, error)`` when the policies cannot be read."""
        from services import protocol_approval
        ca = self._select_signing_ca(ca_refid, warn=False)
        if ca is None:
            return None, None  # the signer reports the missing CA
        from services.acme import profiles as acme_profiles
        template_id = acme_profiles.issuance_params(getattr(order, 'profile', None)).get('template_id')
        cn, dns = protocol_approval.csr_names(csr)
        try:
            approval = protocol_approval.gate_protocol_issuance(
                'acme', ca=ca, template_id=template_id, cn=cn, san_list=dns, csr_pem=csr_pem,
                identity=f'account {order.account_id}', protocol_ref=order.order_id,
                extra={'order_id': order.order_id, 'account_id': order.account_id,
                       'base_url': self.base_url,
                       'identifiers': json.loads(order.identifiers)})
        except protocol_approval.ApprovalGateUnavailable as e:
            return None, str(e)
        if approval is None:
            return None, None
        db.session.refresh(order)
        order.csr = csr_pem
        db.session.commit()
        logger.info("ACME order %s held for approval #%s", order.order_id, approval.id)
        return approval, None

    def _select_signing_ca(self, ca_refid, warn=True):
        """The CA *ca_refid* names, else the first CA able to sign."""
        from models import CA
        if ca_refid:
            return CA.query.filter_by(refid=ca_refid).first()
        # No issuing CA configured: the fallback must be a CA able to
        # sign (a key that is not an empty sentinel, not offline), chosen
        # deterministically rather than in database order
        candidates = CA.query.filter(
            ((CA.prv.isnot(None) & (CA.prv != '')) | CA.hsm_key_id.isnot(None)),
            CA.crt.isnot(None), CA.crt != '',
            CA.offline.is_(False),
        ).order_by(CA.id.asc()).all()
        ca = next((c for c in candidates if not c.revoked_in_chain), None)
        if ca is not None and warn:
            logger.warning(
                "ACME: no issuing CA configured, falling back to CA %s (%s)",
                ca.id, ca.descr,
            )
        return ca

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
                        # The replaced certificate only: its pair partner may be the new one
                        CertificateService.revoke_certificate(
                            cert_id=cert.id,
                            reason='superseded',
                            username='system',
                            revoke_related=False,
                        )
                        logger.info(f"Auto-superseded certificate {cert.id} (replaced by {new_cert_id})")
                    except Exception as e:
                        logger.warning(f"Failed to supersede certificate {cert.id}: {e}")
        except Exception as e:
            logger.warning(f"Auto-supersede check failed: {e}")
    
    @staticmethod
    def _validate_csr_san_types(
        csr, allowed_domains: set, allowed_ips: set
    ) -> Tuple[bool, Optional[str]]:
        """Reject SAN entries the ACME order never authorized.

        ``allowed_domains`` / ``allowed_ips`` are the already-validated,
        normalized order identifiers. Every general name in the CSR's SAN must
        be a DNSName or IPAddress drawn from those sets; any other general-name
        type (rfc822Name, otherName/UPN, URI, dirName, registeredID, ...) is
        rejected outright because no ACME challenge can prove control of it.

        Returns (True, None) when the SAN is acceptable, else (False, reason).
        """
        from cryptography import x509

        try:
            san_ext = csr_extensions(csr).get_extension_for_oid(
                x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
            )
        except x509.ExtensionNotFound:
            return True, None
        except Exception as exc:
            return False, f"Unable to parse CSR SubjectAlternativeName: {exc}"

        for name in san_ext.value:
            if isinstance(name, x509.DNSName):
                if name.value.lower().rstrip('.') not in allowed_domains:
                    return False, (
                        f"CSR SAN dNSName {name.value!r} is not an authorized "
                        "order identifier"
                    )
            elif isinstance(name, x509.IPAddress):
                if str(name.value) not in allowed_ips:
                    return False, (
                        f"CSR SAN iPAddress {name.value} is not an authorized "
                        "order identifier"
                    )
            else:
                # otherName (incl. UPN), rfc822Name, URI, dirName, ...
                type_name = type(name).__name__
                detail = ''
                if isinstance(name, x509.OtherName):
                    detail = f" (type-id {name.type_id.dotted_string})"
                return False, (
                    f"CSR SAN contains unauthorized general name type "
                    f"{type_name}{detail}; ACME may only certify the DNS and IP "
                    "identifiers validated by the order"
                )

        return True, None

    @staticmethod
    def _validate_csr_subject(
        csr, allowed_domains: set, allowed_ips: set
    ) -> Tuple[bool, Optional[str]]:
        """Reject subject Distinguished-Name identities the order never proved.

        ``_validate_csr_san_types`` guards the SAN extension, but two subject
        attributes leak into the issued certificate independently of it:

        * ``sign_csr`` SYNTHESIZES a SAN from the subject when the CSR carries no
          SAN extension — a DNSName/IPAddress/RFC822Name from the CN, plus an
          rfc822Name for every ``emailAddress`` RDN — so a CSR with no SAN and
          ``emailAddress=ceo@victim.com`` still yields a leaf asserting that
          address, which email-based client-certificate identity mapping
          (mTLS, EAP-TLS, VPN) keys on.
        * The subject is copied VERBATIM onto the leaf, and finalize only ever
          compared the FIRST CN to the order, so a second ``CN=admin.victim.com``
          rode along unvalidated — and because the stored ``subject_cn`` is the
          first CN of the RFC 4514 (reversed) DN, it even became the
          certificate's displayed identity.

        CN and emailAddress are the only two subject attribute types ``sign_csr``
        turns into SAN general names, so the check is scoped to them: every CN
        must be a validated order identifier and no ``emailAddress`` may appear.
        Other DN attributes (O, OU, L, ST, C, ...) are never synthesized into
        SANs and are not treated as validated identities, so they are left
        untouched to avoid breaking legitimate OV-style subjects.

        Returns (True, None) when the subject is acceptable, else (False, reason).
        """
        from cryptography import x509

        subject = csr.subject

        # No ACME challenge proves control of an e-mail address; an emailAddress
        # RDN is synthesized into an rfc822Name SAN on a no-SAN CSR and is copied
        # onto the leaf subject regardless.
        email_attrs = subject.get_attributes_for_oid(
            x509.oid.NameOID.EMAIL_ADDRESS
        )
        if email_attrs:
            return False, (
                f"CSR subject contains an emailAddress attribute "
                f"({str(email_attrs[0].value)!r}); ACME may only certify the DNS "
                "and IP identifiers validated by the order"
            )

        # Every commonName — not just the first — must be a validated order
        # identifier (a DNS name or, for RFC 8738 orders, an IP).
        for attr in subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME):
            cn = str(attr.value)
            cn_norm = cn.lower().rstrip('.')
            if _is_ip_text(cn):
                cn_norm = str(ipaddress.ip_address(cn))
            if (
                cn_norm in allowed_domains
                or cn_norm in allowed_ips
                or cn in allowed_ips
            ):
                continue
            return False, (
                f"CSR subject commonName {cn!r} is not an authorized order "
                "identifier"
            )

        return True, None

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
        
        # Get CN from subject; an IP in the CN is an IP identifier, judged by
        # _validate_csr_subject (RFC 8738 orders, lego v4 puts it there)
        try:
            cn = csr.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value
            if not _is_ip_text(cn):
                domains.append(cn)
        except Exception:
            pass
        
        # Get SANs
        try:
            san_ext = csr_extensions(csr).get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
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
    
    @staticmethod
    def _is_request_failure(exc) -> bool:
        """Whether a signing failure is the request's fault (badCSR, order
        invalid) rather than the server's (order retryable)."""
        if exc is None:
            return True
        from services.policy_service import PolicyViolation
        if isinstance(exc, PolicyViolation):
            return True
        from utils.ca_signing_window import IssuerWindowError
        try:
            from services.ca.ca_signing import CAOfflineError
        except Exception:  # pragma: no cover - defensive import
            CAOfflineError = ()
        from utils.custom_extensions import TemplateConfigError
        if isinstance(exc, (IssuerWindowError, CAOfflineError, TemplateConfigError)):
            return False
        # Only messages our own CA/key code emits, never a name or a subject
        # the client chose (a name constraint refusal quoting "hsm.example")
        text = str(exc)
        if any(word in text for word in ('signing key', 'HSM', 'No CA available',
                                         'awaiting its certificate', 'has no private key',
                                         'KEY_ENCRYPTION_KEY')):
            return False
        return isinstance(exc, ValueError)

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
        from cryptography import x509
        import secrets
        import base64
        
        # Get CA (use first available if not specified)
        ca = self._select_signing_ca(ca_refid)
        
        if not ca:
            self._last_signing_exception = RuntimeError("No CA available for signing")
            return False, None, "No CA available for signing"
        
        if not ca.has_private_key:
            self._last_signing_exception = RuntimeError("CA has no private key")
            return False, None, f"CA {ca.refid} has no private key"
        
        if not ca.crt:
            self._last_signing_exception = RuntimeError("CA is awaiting its certificate")
            return False, None, f"CA {ca.refid} is awaiting its certificate"
        
        from services.acme import profiles as acme_profiles
        params = acme_profiles.issuance_params(getattr(order, 'profile', None))

        # RFC 8555 §7.4: the order's dates, within the profile and the CA, or no certificate
        not_before = getattr(order, 'not_before', None)
        not_after = getattr(order, 'not_after', None)
        if not_before or not_after:
            from services.acme.requested_validity import RequestedValidityError, window_error
            from utils.ca_signing_window import issuer_window
            try:
                ca_cert = x509.load_pem_x509_certificate(base64.b64decode(ca.crt))
            except Exception:
                ca_cert = None
            refusal = window_error(
                not_before, not_after, params['validity_days'],
                ca_window=issuer_window(ca_cert) if ca_cert is not None else None)
            if refusal:
                self._last_signing_exception = RequestedValidityError(refusal)
                return False, None, refusal

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
                    san_ext = csr_extensions(csr).get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
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
            
            # Issuance parameters come from the order's selected ACME profile
            # (draft-ietf-acme-profiles); with no profile these are UCM's
            # historical ACME defaults (90 days, sha256, no template). A
            # profile may bind a certificate template whose KU/EKU then
            # govern the leaf (#327 follow-up).
            signed_cert = CertificateService.sign_csr(
                cert_id=cert.id,
                caref=ca.refid,
                cert_type='server_cert',
                validity_days=params['validity_days'],
                # No digest configured: the CA key's
                digest=params['digest'] if params.get('digest_explicit', True) else None,
                digest_explicit=params.get('digest_explicit', True),
                username='acme',
                template_id=params.get('template_id'),
                not_before=not_before,
                not_after=not_after,
            )
            
            return True, signed_cert.id, None
            
        except Exception as e:
            db.session.rollback()
            self._last_signing_exception = e
            from utils.custom_extensions import TemplateConfigError
            if isinstance(e, TemplateConfigError):
                # The template's name stays in the log, not in the client's error
                logger.error("ACME: order %s not signed: %s", order.order_id, e)
                return False, None, f"Certificate signing failed: {e.public_message}"
            return False, None, f"Certificate signing failed: {str(e)}"
