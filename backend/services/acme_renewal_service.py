"""
ACME Auto-Renewal Service
Automatically renews Let's Encrypt certificates before expiry.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Default: renew 30 days before expiry
DEFAULT_RENEWAL_DAYS = 30
MAX_RENEWAL_FAILURES = 5


def scheduled_acme_renewal():
    """
    Scheduled task to check and renew ACME certificates.
    Called by scheduler service.
    """
    from flask import current_app
    from models import db
    from models.acme_models import AcmeClientOrder, DnsProvider
    
    logger.info("Starting ACME auto-renewal check...")
    
    try:
        # Get renewal threshold from settings or use default
        renewal_days = DEFAULT_RENEWAL_DAYS
        
        # Calculate threshold date
        threshold_date = datetime.utcnow() + timedelta(days=renewal_days)
        
        # Find orders that need renewal:
        # - renewal_enabled = True
        # - status = 'issued'
        # - expires_at <= threshold_date
        # - renewal_failures < MAX_RENEWAL_FAILURES
        orders_to_renew = AcmeClientOrder.query.filter(
            AcmeClientOrder.renewal_enabled == True,
            AcmeClientOrder.status == 'issued',
            AcmeClientOrder.expires_at <= threshold_date,
            AcmeClientOrder.renewal_failures < MAX_RENEWAL_FAILURES
        ).all()
        
        if not orders_to_renew:
            logger.info("No certificates need renewal")
            return
        
        logger.info(f"Found {len(orders_to_renew)} certificate(s) to renew")
        
        for order in orders_to_renew:
            try:
                renew_certificate(order)
            except Exception as e:
                logger.error(f"Failed to renew order {order.id}: {e}")
                order.renewal_failures += 1
                order.last_error_at = datetime.utcnow()
                order.error_message = str(e)
                db.session.commit()
        
        logger.info("ACME auto-renewal check completed")
        
    except Exception as e:
        logger.error(f"ACME auto-renewal task failed: {e}")


def renew_certificate(order) -> bool:
    """
    Renew a single certificate order.
    
    Args:
        order: AcmeClientOrder to renew
        
    Returns:
        True if renewal succeeded
    """
    from models import db
    from models.acme_models import DnsProvider
    from services.acme.acme_client_service import AcmeClientService
    from services.acme.dns_providers import create_provider
    import json
    import time
    
    logger.info(f"Renewing certificate for {order.primary_domain} (order {order.id})")
    
    # Save old certificate ID for potential revocation
    old_certificate_id = order.certificate_id
    
    # Get DNS provider
    dns_provider_model = DnsProvider.query.get(order.dns_provider_id)
    if not dns_provider_model:
        raise Exception("DNS provider not found")
    
    credentials = json.loads(dns_provider_model.credentials) if dns_provider_model.credentials else {}
    dns_provider = create_provider(dns_provider_model.provider_type, credentials)
    
    # Initialize ACME client
    acme_client = AcmeClientService(environment=order.environment)
    
    # Create new order for same domains
    domains = order.domains_list
    
    # Register/get account
    success, account_url, message = acme_client.register_account(order.account_url)
    if not success:
        raise Exception(f"Account registration failed: {message}")
    
    # Create new ACME order
    success, result = acme_client.create_order(domains)
    if not success:
        raise Exception(f"Order creation failed: {result}")
    
    new_order_url = result['order_url']
    new_finalize_url = result['finalize_url']
    authorizations = result['authorizations']
    
    # Setup DNS challenges
    for authz in authorizations:
        domain = authz['domain']
        
        # Get DNS-01 challenge
        dns_challenge = None
        for challenge in authz.get('challenges', []):
            if challenge['type'] == 'dns-01':
                dns_challenge = challenge
                break
        
        if not dns_challenge:
            raise Exception(f"No DNS-01 challenge for {domain}")
        
        # Calculate challenge response
        token = dns_challenge['token']
        key_auth = acme_client._get_key_authorization(token)
        dns_value = acme_client._get_dns_challenge_value(key_auth)
        
        # Create DNS record
        record_name = f"_acme-challenge.{domain.lstrip('*.')}"
        success, msg = dns_provider.create_txt_record(
            domain=domain.lstrip('*.'),
            record_name=record_name,
            record_value=dns_value,
            ttl=300
        )
        
        if not success:
            raise Exception(f"Failed to create DNS record for {domain}: {msg}")
    
    # Wait for DNS propagation
    logger.info("Waiting for DNS propagation...")
    time.sleep(30)
    
    # Submit challenges for validation
    for authz in authorizations:
        for challenge in authz.get('challenges', []):
            if challenge['type'] == 'dns-01':
                success, msg = acme_client._submit_challenge(challenge['url'])
                if not success:
                    logger.warning(f"Challenge submission warning: {msg}")
    
    # Wait for validation
    logger.info("Waiting for ACME validation...")
    time.sleep(20)
    
    # Finalize order
    success, cert_result = acme_client.finalize_order(
        order_url=new_order_url,
        finalize_url=new_finalize_url,
        domains=domains
    )
    
    if not success:
        raise Exception(f"Order finalization failed: {cert_result}")
    
    cert_pem = cert_result['certificate']
    key_pem = cert_result['private_key']
    
    # Import new certificate
    cert_id = acme_client._import_certificate(
        cert_pem=cert_pem,
        key_pem=key_pem,
        domains=domains,
        source='acme_renewal'
    )
    
    if not cert_id:
        raise Exception("Certificate import failed")
    
    # Update order with new certificate
    order.certificate_id = cert_id
    order.order_url = new_order_url
    order.last_renewal_at = datetime.utcnow()
    order.renewal_failures = 0
    order.error_message = None
    order.last_error_at = None
    
    # Update expiry from new certificate
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    cert = x509.load_pem_x509_certificate(cert_pem.encode(), default_backend())
    order.expires_at = cert.not_valid_after_utc
    
    db.session.commit()
    
    # Cleanup DNS records
    for authz in authorizations:
        domain = authz['domain']
        record_name = f"_acme-challenge.{domain.lstrip('*.')}"
        dns_provider.delete_txt_record(
            domain=domain.lstrip('*.'),
            record_name=record_name
        )
    
    logger.info(f"Successfully renewed certificate for {order.primary_domain} (new cert ID: {cert_id})")
    
    # Revoke old certificate if setting is enabled
    if old_certificate_id and old_certificate_id != cert_id:
        try:
            from models import SystemConfig
            revoke_setting = SystemConfig.query.filter_by(key='acme.client.revoke_on_renewal').first()
            if revoke_setting and revoke_setting.value == 'true':
                from services.cert_service import CertificateService
                CertificateService.revoke_certificate(
                    cert_id=old_certificate_id,
                    reason='superseded',
                    username='system'
                )
                logger.info(f"Revoked superseded certificate {old_certificate_id}")
        except Exception as e:
            logger.warning(f"Failed to revoke old certificate {old_certificate_id}: {e}")
    
    return True
