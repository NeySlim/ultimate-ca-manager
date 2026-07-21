"""
ACME Auto-Renewal Service
Automatically renews Let's Encrypt certificates before expiry.
"""
import json
import logging
import time
from datetime import timedelta

from models import Certificate, DnsProvider, SystemConfig, db
from models.acme_models import AcmeClientOrder
from services.acme import dns_providers
from services.acme.acme_client_service import AcmeClientService
from services.acme.dns_selfcheck import dns_propagation_timeout, wait_for_challenges
from services.cert_service import CertificateService
from utils.acme_debug import acme_log
from utils.datetime_utils import utc_now
from utils.db_transaction import commit_or_rollback

logger = logging.getLogger(__name__)

# Default: renew 30 days before expiry
DEFAULT_RENEWAL_DAYS = 30
MAX_RENEWAL_FAILURES = 5

# Successful ARI responses are cached until the upstream Retry-After time.
# The scheduler is process-local, so this is sufficient to prevent repeated
# polling on each scheduler tick without adding persistent schema state.
_ARI_CACHE = {}


def _cached_renewal_info(order, certificate, now):
    """Return upstream ARI data while honoring Retry-After."""
    cache_key = (order.acme_client_account_id, certificate.id)
    cached = _ARI_CACHE.get(cache_key)
    if cached and cached.get('retry_after') and now < cached['retry_after']:
        return cached['info']

    client = AcmeClientService.for_order(order)
    info = client.get_renewal_info(certificate)
    if info and info.get('retry_after') and info['retry_after'] > now:
        _ARI_CACHE[cache_key] = {
            'info': info,
            'retry_after': info['retry_after'],
        }
    else:
        _ARI_CACHE.pop(cache_key, None)
    return info


def _order_is_due(order, now, fallback_threshold):
    """Decide renewal timing from ARI, falling back to the fixed threshold."""
    certificate = db.session.get(Certificate, order.certificate_id)
    if certificate is not None:
        try:
            info = _cached_renewal_info(order, certificate, now)
            if info:
                window = info['suggested_window']
                return now >= window['start']
        except Exception as exc:
            logger.warning(
                "Could not retrieve upstream renewal information for order %s: %s",
                order.id,
                exc,
            )

    return bool(order.expires_at and order.expires_at <= fallback_threshold)


def _revoke_replaced_certificate(acme_client, certificate):
    """Best-effort local and upstream revocation after successful renewal."""
    try:
        revoke_setting = SystemConfig.query.filter_by(
            key='acme.revoke_on_renewal'
        ).first()
    except Exception as exc:
        logger.warning("Could not read ACME renewal revocation setting: %s", exc)
        return
    if not revoke_setting or revoke_setting.value != 'true':
        return

    try:
        CertificateService.revoke_certificate(
            cert_id=certificate.id,
            reason='superseded',
            username='system',
        )
        logger.info(f"Revoked superseded certificate {certificate.id}")
    except Exception as exc:
        logger.warning(
            "Failed to revoke old certificate %s locally: %s",
            certificate.id,
            exc,
        )

    try:
        upstream = acme_client.revoke_certificate(certificate, reason=4)
        if not 200 <= upstream.status_code < 300:
            logger.warning(
                "Upstream revocation of certificate %s failed with HTTP %s",
                certificate.id,
                upstream.status_code,
            )
    except Exception as exc:
        logger.warning(
            "Upstream revocation of certificate %s failed: %s",
            certificate.id,
            exc,
        )


def scheduled_acme_renewal():
    """
    Scheduled task to check and renew ACME certificates.
    Called by scheduler service.
    """
    logger.info("Starting ACME auto-renewal check...")
    
    try:
        # Get renewal threshold from settings or use default
        renewal_days = DEFAULT_RENEWAL_DAYS
        
        now = utc_now()
        threshold_date = now + timedelta(days=renewal_days)

        # ARI may request renewal earlier than the local 30-day fallback, so
        # evaluate every eligible issued order rather than pre-filtering by
        # expires_at in SQL.
        eligible_orders = AcmeClientOrder.query.filter(
            AcmeClientOrder.renewal_enabled == True,
            AcmeClientOrder.status == 'issued',
            AcmeClientOrder.renewal_failures < MAX_RENEWAL_FAILURES,
        ).all()
        orders_to_renew = [
            order for order in eligible_orders
            if _order_is_due(order, now, threshold_date)
        ]
        
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
                commit_or_rollback(
                    logger,
                    f"Failed to persist renewal failure for order {order.id}",
                )
        
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
    logger.info(f"Renewing certificate for {order.primary_domain} (order {order.id})")
    
    # Save the old certificate for RFC 9773 `replaces` and optional revocation.
    old_certificate_id = order.certificate_id
    old_certificate = (
        db.session.get(Certificate, old_certificate_id)
        if old_certificate_id else None
    )
    
    # Get DNS provider
    dns_provider_model = db.session.get(DnsProvider, order.dns_provider_id)
    if not dns_provider_model:
        raise Exception("DNS provider not found")
    
    credentials = json.loads(dns_provider_model.credentials) if dns_provider_model.credentials else {}
    dns_provider = dns_providers.create_provider(
        dns_provider_model.provider_type,
        credentials,
    )
    
    # Initialize ACME client for the same CA that issued the original order
    acme_client = AcmeClientService.for_order(order)
    
    # Create new order for same domains
    domains = order.domains_list
    
    # Get email from settings (same source as manual order creation)
    email_cfg = SystemConfig.query.filter_by(key='acme.client.email').first()
    email = email_cfg.value if email_cfg else None
    if not email:
        raise Exception("ACME client email not configured — cannot renew")
    
    # RFC 9773 §5: identify the certificate being replaced when the CA
    # advertises ARI. Failure to build a CertID must not block renewal.
    replaces = None
    try:
        if old_certificate and acme_client._fetch_directory().get('renewalInfo'):
            replaces = acme_client.certificate_identifier(old_certificate)
    except Exception as exc:
        logger.warning(
            "Could not build ARI replaces identifier for order %s: %s",
            order.id,
            exc,
        )

    # Create new ACME order
    success, message, new_order = acme_client.create_order(
        domains=domains,
        email=email,
        challenge_type=order.challenge_type or 'dns-01',
        dns_provider_id=order.dns_provider_id,
        replaces=replaces,
    )
    if not success:
        raise Exception(f"Order creation failed: {message}")
    
    # Preserve key source across renewals (#161)
    new_order.key_source = order.key_source or 'generate'
    new_order.key_type = order.key_type
    if order.csr_pem:
        new_order.csr_pem = order.csr_pem
    if (order.key_source or 'generate') == 'reuse':
        # Prefer the cert issued by this order; fall back to the original
        # source so the key-reuse chain survives an order whose import failed.
        reuse_src = order.certificate_id or order.source_certificate_id
        if reuse_src:
            new_order.source_certificate_id = reuse_src
        else:
            logger.warning(
                f"Order {order.id} has key_source=reuse but no linked "
                f"certificate; a new key will be generated on finalize"
            )
    if not commit_or_rollback(logger, "Could not persist key source on renewal order"):
        logger.warning("Renewal will continue with the in-memory key source settings")
    
    new_order_url = new_order.order_url
    challenges = new_order.challenges_dict
    dns_txt_created = False

    def _cleanup_dns_txt_records():
        for domain, challenge_info in challenges.items():
            record_name = challenge_info.get(
                'dns_txt_name', f"_acme-challenge.{domain.lstrip('*.')}"
            )
            try:
                dns_provider.delete_txt_record(
                    domain=domain.lstrip('*.'),
                    record_name=record_name,
                )
            except Exception as exc:
                logger.warning(
                    'Failed to delete renewal DNS TXT for %s (%s): %s',
                    domain, record_name, exc,
                )

    try:
        # Setup DNS challenges using data already computed by create_order
        for domain, challenge_info in challenges.items():
            dns_value = challenge_info.get('dns_txt_value')
            record_name = challenge_info.get(
                'dns_txt_name', f"_acme-challenge.{domain.lstrip('*.')}"
            )

            if not dns_value:
                raise Exception(f"No DNS challenge value for {domain}")

            success_dns, msg = dns_provider.create_txt_record(
                domain=domain.lstrip('*.'),
                record_name=record_name,
                record_value=dns_value,
                ttl=300,
            )

            if not success_dns:
                raise Exception(f"Failed to create DNS record for {domain}: {msg}")

            dns_txt_created = True

        # Wait for DNS propagation using active self-check.
        timeout = dns_propagation_timeout('acme.client.dns_propagation_timeout')
        acme_log(
            logger,
            'Renewal DNS propagation wait: timeout=%ss, domains=%s',
            timeout, ', '.join(sorted(challenges)),
        )
        if timeout <= 0:
            logger.info("DNS propagation pre-check skipped (timeout=0)")
            check = {'ok': True, 'missing': [], 'waited': 0}
        else:
            check = wait_for_challenges(challenges, timeout)
        if not check['ok']:
            # Soft-fail: our local resolver may not see the record (split-horizon,
            # filtered egress DNS) even though the CA can. Warn and let the CA be
            # the authority — do NOT abort before submitting the challenge.
            logger.warning(
                "DNS propagation not confirmed locally after %ss for: %s — "
                "submitting to the CA anyway",
                timeout, ', '.join(check['missing']),
            )
        else:
            logger.info("DNS propagation confirmed after %ss", check['waited'])

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
        new_cert = db.session.get(Certificate, cert_id)
        if new_cert and new_cert.valid_to:
            order.expires_at = new_cert.valid_to

        if not commit_or_rollback(logger, "Failed to persist renewed certificate"):
            raise RuntimeError("Failed to persist renewed certificate")

        logger.info(
            f"Successfully renewed certificate for {order.primary_domain} (new cert ID: {cert_id})"
        )

        if old_certificate is not None:
            _ARI_CACHE.pop(
                (order.acme_client_account_id, old_certificate.id),
                None,
            )

        # Revoke the replaced certificate locally and upstream when enabled.
        if old_certificate and old_certificate_id != cert_id:
            _revoke_replaced_certificate(acme_client, old_certificate)

        return True, f"Successfully renewed (new certificate ID: {cert_id})"
    finally:
        if dns_txt_created:
            _cleanup_dns_txt_records()
