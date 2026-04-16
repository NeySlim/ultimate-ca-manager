"""
ACME Auto-Renewal Service
Automatically renews Let's Encrypt certificates before expiry.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional
from utils.datetime_utils import utc_now

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
        threshold_date = utc_now() + timedelta(days=renewal_days)
        
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
                order.last_error_at = utc_now()
                order.error_message = str(e)
                db.session.commit()
        
        logger.info("ACME auto-renewal check completed")
        
    except Exception as e:
        logger.error(f"ACME auto-renewal task failed: {e}")


def renew_certificate(order) -> tuple:
    """
    Renew a single certificate order.
    
    Args:
        order: AcmeClientOrder to renew
        
    Returns:
        Tuple of (success: bool, message: str)
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
    
    # Get email from settings (same source as manual order creation)
    from models import SystemConfig
    email_cfg = SystemConfig.query.filter_by(key='acme.client.email').first()
    email = email_cfg.value if email_cfg else None
    if not email:
        raise Exception("ACME client email not configured — cannot renew")
    
    # Create new ACME order
    success, message, new_order = acme_client.create_order(
        domains=domains,
        email=email,
        challenge_type=order.challenge_type or 'dns-01',
        dns_provider_id=order.dns_provider_id
    )
    if not success:
        raise Exception(f"Order creation failed: {message}")
    
    new_order_url = new_order.order_url
    new_finalize_url = new_order.finalize_url
    challenges = new_order.challenges_dict
    
    # Setup DNS challenges using data already computed by create_order
    for domain, challenge_info in challenges.items():
        dns_value = challenge_info.get('dns_txt_value')
        record_name = challenge_info.get('dns_txt_name', f"_acme-challenge.{domain.lstrip('*.')}")
        
        if not dns_value:
            raise Exception(f"No DNS challenge value for {domain}")
        
        # Create DNS record
        success_dns, msg = dns_provider.create_txt_record(
            domain=domain.lstrip('*.'),
            record_name=record_name,
            record_value=dns_value,
            ttl=300
        )
        
        if not success_dns:
            raise Exception(f"Failed to create DNS record for {domain}: {msg}")
    
    # Wait for DNS propagation
    logger.info("Waiting for DNS propagation...")
    time.sleep(30)
    
    # Submit challenges for validation
    for domain in challenges.keys():
        success_ch, msg = acme_client.verify_challenge(new_order, domain)
        if not success_ch:
            logger.warning(f"Challenge submission warning for {domain}: {msg}")
    
    # Wait for validation
    logger.info("Waiting for ACME validation...")
    time.sleep(20)
    
    # Finalize order — finalize_order handles CSR generation, cert download, and import
    success_fin, message_fin, cert_id = acme_client.finalize_order(new_order)
    
    if not success_fin:
        raise Exception(f"Order finalization failed: {message_fin}")
    
    if not cert_id:
        raise Exception("Certificate import failed during finalization")
    
    # Update original order with new certificate reference
    order.certificate_id = cert_id
    order.order_url = new_order_url
    order.last_renewal_at = utc_now()
    order.renewal_failures = 0
    order.error_message = None
    order.last_error_at = None
    
    # Update expiry from new certificate
    from models import Certificate
    new_cert = Certificate.query.get(cert_id)
    if new_cert and new_cert.not_after:
        order.expires_at = new_cert.not_after
    
    db.session.commit()
    
    # Cleanup DNS records
    for domain, challenge_info in challenges.items():
        record_name = challenge_info.get('dns_txt_name', f"_acme-challenge.{domain.lstrip('*.')}")
        dns_provider.delete_txt_record(
            domain=domain.lstrip('*.'),
            record_name=record_name
        )
    
    logger.info(f"Successfully renewed certificate for {order.primary_domain} (new cert ID: {cert_id})")
    
    # Revoke old certificate if setting is enabled
    if old_certificate_id and old_certificate_id != cert_id:
        try:
            from models import SystemConfig
            revoke_setting = SystemConfig.query.filter_by(key='acme.revoke_on_renewal').first()
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
    
    return True, f"Successfully renewed (new certificate ID: {cert_id})"
