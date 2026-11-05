"""
ACME Auto-Renewal Service
Automatically renews Let's Encrypt certificates before expiry.
"""
import base64
import json
import logging
from datetime import timedelta
from types import SimpleNamespace

from models import CA, Certificate, DnsProvider, RevokedSerial, SystemConfig, db
from models.acme_models import AcmeClientOrder
from services.acme import dns_providers
from services.acme.acme_client_service import AcmeClientService
from services.acme.dns_selfcheck import dns_propagation_timeout, wait_for_challenges
from services.acme.http01 import wait_for_http01
from services.acme.client_certificates import KEY_MISMATCH
from services.acme.order_lease import BUSY, LEASE_LOST, OrderLease, RenewalInProgress
from services.audit.staging import stage_audit_entry
from services.cert_service import CertificateService
from utils.acme_debug import acme_log
from utils.datetime_utils import utc_now
from utils.san_parse import strip_wildcard
from services.acme.dns_txt_lock import txt_record_lock
from utils.db_transaction import commit_or_rollback

logger = logging.getLogger(__name__)

# Default: renew 30 days before expiry
DEFAULT_RENEWAL_DAYS = 30
MAX_RENEWAL_FAILURES = 5
# UCM serves its own HTTP-01 tokens, so the file is there at once or not at all.
HTTP01_RENEWAL_WAIT = 10


class RenewalBlocked(Exception):
    """Renewal stopped before reaching the CA; the message is meant for the operator."""

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

    if not order.expires_at:
        return False
    # A threshold near the certificate's whole life would renew it again and again
    if certificate is not None and certificate.valid_from and certificate.valid_to:
        # notAfter is inclusive (RFC 5280 §4.1.2.5): a 90-day certificate ends one second short
        lifetime = certificate.valid_to - certificate.valid_from + timedelta(seconds=1)
        if (fallback_threshold - now) * 3 > lifetime * 2:
            fallback_threshold = now + lifetime / 3
    return order.expires_at <= fallback_threshold


def _pending_http01_order(order, account_id):
    """Unexpired pending HTTP-01 order for the same names, CA account and environment.

    A blocked HTTP-01 renewal leaves its order pending; the next attempt reuses it
    instead of opening one more order per scheduler tick.
    """
    now = utc_now()
    wanted = sorted(order.domains_list)
    candidates = AcmeClientOrder.query.filter(
        AcmeClientOrder.id != order.id,
        AcmeClientOrder.challenge_type == 'http-01',
        AcmeClientOrder.status == 'pending',
        AcmeClientOrder.acme_client_account_id == account_id,
        AcmeClientOrder.environment == order.environment,
    ).order_by(AcmeClientOrder.created_at.desc()).all()
    for candidate in candidates:
        if candidate.is_proxy_order or (candidate.expires_at and candidate.expires_at <= now):
            continue
        challenges = candidate.challenges_dict
        # An order whose authorizations were never fetched cannot be answered: open a new one.
        if sorted(candidate.domains_list) == wanted and sorted(challenges) == wanted and all(
            c.get('token') and c.get('key_authorization') for c in challenges.values()
        ):
            return candidate
    return None


def _replaced_snapshot(certificate):
    """What revoking the replaced certificate needs, read before a renewal overwrites its row."""
    if certificate is None or not certificate.crt:
        return None
    return SimpleNamespace(id=certificate.id, pem=base64.b64decode(certificate.crt),
                           serial=certificate.serial_number, valid_to=certificate.valid_to,
                           caref=certificate.caref, revoked=bool(certificate.revoked))


def _record_replaced_serial(replaced):
    """Revocation record of the replaced serial, when its issuer is a CA held here."""
    ca = CA.query.filter_by(refid=replaced.caref).first() if replaced.caref else None
    if ca is None:
        return  # an external CA publishes its own revocations
    now = utc_now()
    row = RevokedSerial.query.filter_by(caref=ca.refid, serial_number=replaced.serial).first()
    if row is None:
        row = RevokedSerial(caref=ca.refid, serial_number=replaced.serial)
        db.session.add(row)
    row.revoked_at = now
    row.revoke_reason = 'superseded'
    row.valid_to = replaced.valid_to or now + timedelta(days=365)
    row.certificate_id = replaced.id
    commit_or_rollback(logger, f"Revocation record of serial {replaced.serial} not saved")


def _revoke_replaced_certificate(acme_client, replaced, in_place):
    """Best-effort local and upstream revocation after successful renewal.

    Renewed in place, the row holds the new certificate: only the old serial is recorded,
    and the CA is sent the old certificate as it was before the renewal.
    """
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
        if in_place:
            _record_replaced_serial(replaced)
            logger.info(f"Revoked superseded certificate {replaced.id} (serial {replaced.serial})")
        elif not replaced.revoked:  # a revoked row keeps the revocation it has
            CertificateService.revoke_certificate(
                cert_id=replaced.id,
                reason='superseded',
                username='system',
                revoke_related=False,
            )
            logger.info(f"Revoked superseded certificate {replaced.id} (serial {replaced.serial})")
    except Exception as exc:
        logger.warning(
            "Failed to revoke old certificate %s locally: %s",
            replaced.id,
            exc,
        )

    try:
        upstream = acme_client.revoke_certificate(replaced.pem, reason=4)
        if not 200 <= upstream.status_code < 300:
            logger.warning(
                "Upstream revocation of certificate %s failed with HTTP %s",
                replaced.id,
                upstream.status_code,
            )
    except Exception as exc:
        logger.warning(
            "Upstream revocation of certificate %s failed: %s",
            replaced.id,
            exc,
        )


def _configured_renewal_days():
    """``acme.client.renewal_days`` (1 to 60), the default when unset or invalid."""
    row = SystemConfig.query.filter_by(key='acme.client.renewal_days').first()
    try:
        days = int(row.value) if row else DEFAULT_RENEWAL_DAYS
    except (TypeError, ValueError):
        return DEFAULT_RENEWAL_DAYS
    return min(60, max(1, days))


def scheduled_acme_renewal():
    """
    Scheduled task to check and renew ACME certificates.
    Called by scheduler service.
    """
    logger.info("Starting ACME auto-renewal check...")

    # The Let's Encrypt tab's global switch; each order also has its own.
    switch = SystemConfig.query.filter_by(key='acme.client.renewal_enabled').first()
    if switch is not None and str(switch.value).lower() != 'true':
        logger.info("ACME auto-renewal is turned off")
        return

    try:
        renewal_days = _configured_renewal_days()
        
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
            order_id = order.id
            lease = OrderLease.take(order_id)
            if lease is None:
                logger.info("Order %s skipped: another renewal of it is running", order_id)
                continue
            try:
                renew_certificate(order, lease=lease)
            except RenewalInProgress as e:
                logger.info("Order %s left to another renewal: %s", order_id, e)
            except Exception as e:
                logger.error(f"Failed to renew order {order_id}: {e}")
                order.renewal_failures += 1
                order.last_error_at = utc_now()
                order.error_message = str(e)
                stage_audit_entry(
                    action='acme_order.auto_renewal_failed',
                    resource_type='acme_order',
                    resource_id=str(order_id),
                    resource_name=order.primary_domain,
                    details=f'Auto-renewal failed: {e}',
                    success=False,
                )
                commit_or_rollback(
                    logger,
                    f"Failed to persist renewal failure for order {order_id}",
                )
            finally:
                lease.release()
        
        logger.info("ACME auto-renewal check completed")
        
    except Exception as e:
        logger.error(f"ACME auto-renewal task failed: {e}")


def renew_certificate(order, lease=None) -> tuple:
    """Renew one order into the certificate row it names: ``(success, message)``.

    ``lease`` is the caller's lease on the order; without one the renewal takes its own,
    and raises RenewalInProgress while another renewal or finalization holds the order.
    """
    own_lease = lease is None
    if own_lease:
        lease = OrderLease.take(order.id)
        if lease is None:
            raise RenewalInProgress(BUSY)
    try:
        return _renew(order, lease)
    finally:
        if own_lease:
            lease.release()


def _renew(order, lease) -> tuple:
    logger.info(f"Renewing certificate for {order.primary_domain} (order {order.id})")
    
    # Save the old certificate for RFC 9773 `replaces` and optional revocation.
    old_certificate_id = order.certificate_id
    old_certificate = (
        db.session.get(Certificate, old_certificate_id)
        if old_certificate_id else None
    )
    # Read before the renewal writes the new certificate into the same row
    replaced = _replaced_snapshot(old_certificate)

    # Initialize ACME client for the same CA that issued the original order
    acme_client = AcmeClientService.for_order(order)
    # The resolved account, not the old order's column: legacy rows have none.
    account_id = getattr(acme_client.account, 'id', None)

    cert_id = _resume_kept_order(acme_client, order, account_id, lease)
    if cert_id is None:
        cert_id = _renew_with_new_order(acme_client, order, account_id, old_certificate, lease)

    logger.info(
        f"Successfully renewed certificate for {order.primary_domain} (certificate ID: {cert_id})"
    )
    # The row keeps its id: the window cached for the replaced certificate must go
    _ARI_CACHE.pop((order.acme_client_account_id, old_certificate_id), None)

    # Revoke the replaced certificate locally and upstream when enabled.
    if replaced is not None:
        _revoke_replaced_certificate(acme_client, replaced, in_place=cert_id == old_certificate_id)

    return True, f"Successfully renewed (certificate ID: {cert_id})"


# Statuses of a renewal order that may hold a finalization: kept for the next renewal.
_RESUMABLE = ('validating', 'ready', 'processing', 'valid', 'error')


def _kept_renewal_order(order, account_id):
    """The newest order whose ``renewal_of_order_id`` names ``order``, opened under this
    account and still resumable, or None."""
    return AcmeClientOrder.query.filter(
        AcmeClientOrder.renewal_of_order_id == order.id,
        AcmeClientOrder.status.in_(_RESUMABLE),
        AcmeClientOrder.acme_client_account_id == account_id,
    ).order_by(AcmeClientOrder.id.desc()).first()


def renewal_parent(order):
    """The order ``order.renewal_of_order_id`` names while ``order`` is unfinished, else None."""
    if order.renewal_of_order_id is None or order.status == 'issued':
        return None
    return db.session.get(AcmeClientOrder, order.renewal_of_order_id)


def _drop_kept_order(kept):
    db.session.delete(kept)
    if not commit_or_rollback(logger, f"Could not remove the stale renewal order {kept.id}"):
        raise RuntimeError(f"Could not remove the stale renewal order {kept.id}")


def _resume_kept_order(acme_client, order, account_id, lease):
    """Finish the order an interrupted renewal left at the CA: the certificate id, or None
    when there is none to finish (one the CA no longer completes is removed)."""
    kept = _kept_renewal_order(order, account_id)
    if kept is None:
        return None
    state = acme_client.fetch_order_state(kept)
    _key, key_error = acme_client.held_finalize_key(kept)
    if state == 'ready' or (state in ('processing', 'valid') and key_error is None):
        logger.info("Renewal of order %s resumes order %s (%s at the CA)", order.id, kept.id, state)
        ok, message, cert_id = acme_client.finalize_order(kept, renews=order, lease=lease)
        if message == LEASE_LOST:
            raise RenewalInProgress(LEASE_LOST)
        if not ok and message == KEY_MISMATCH:
            # Retrying cannot change what the CA issued: a new order replaces this one
            logger.warning("Renewal of order %s drops order %s: the certificate the CA issued "
                           "for it does not match the key kept for it; a new order is opened",
                           order.id, kept.id)
            _drop_kept_order(kept)
            return None
        if not ok:
            raise Exception(f"Order finalization failed: {message}")
        return cert_id
    logger.info("Renewal of order %s drops order %s (%s at the CA)", order.id, kept.id, state)
    _drop_kept_order(kept)
    return None


def _renew_with_new_order(acme_client, order, account_id, old_certificate, lease):
    """A renewal through an order of its own (or a pending HTTP-01 one): the certificate id."""
    challenge_type = order.challenge_type or 'dns-01'
    # HTTP-01 and TLS-ALPN-01 proofs are served by UCM itself; only DNS-01 needs a provider.
    dns_provider = None
    if challenge_type == 'dns-01':
        dns_provider_model = (
            db.session.get(DnsProvider, order.dns_provider_id) if order.dns_provider_id else None
        )
        # The manual provider publishes nothing: submitting would only invalidate the order.
        if not dns_provider_model or dns_provider_model.provider_type == 'manual':
            raise RenewalBlocked(
                'No automatic DNS provider on this DNS-01 order: a manual DNS order cannot renew automatically'
            )
        credentials = json.loads(dns_provider_model.credentials) if dns_provider_model.credentials else {}
        dns_provider = dns_providers.create_provider(
            dns_provider_model.provider_type,
            credentials,
        )
    
    # Create new order for same domains
    domains = order.domains_list
    
    # Get email from settings (same source as manual order creation)
    email_cfg = SystemConfig.query.filter_by(key='acme.client.email').first()
    email = email_cfg.value if email_cfg else None
    # Only a registration uses it: an account that exists renews without
    if not email and not acme_client._get_account_url():
        raise Exception("ACME client email not configured: cannot renew")
    
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

    new_order = _pending_http01_order(order, account_id) if challenge_type == 'http-01' else None
    reused_order = new_order is not None  # maybe the operator's own: never removed here
    if reused_order:
        logger.info("Renewal of order %s reuses pending order %s", order.id, new_order.id)
    else:
        success, message, new_order = acme_client.create_order(
            domains=domains,
            email=email,
            challenge_type=challenge_type,
            dns_provider_id=order.dns_provider_id,
            replaces=replaces,
        )
        if not success:
            raise Exception(f"Order creation failed: {message}")
        # This renewal's order: never renewed itself, resumed by the next renewal of ``order``
        new_order.renewal_enabled = False
        new_order.renewal_of_order_id = order.id
    
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
    
    challenges = new_order.challenges_dict
    dns_txt_created = False

    def _cleanup_dns_txt_records():
        for domain, challenge_info in challenges.items():
            record_name = challenge_info.get(
                'dns_txt_name', f"_acme-challenge.{strip_wildcard(domain)}"
            )
            try:
                with txt_record_lock(record_name):
                    dns_provider.delete_txt_record(
                        domain=strip_wildcard(domain),
                        record_name=record_name,
                    )
            except Exception as exc:
                logger.warning(
                    'Failed to delete renewal DNS TXT for %s (%s): %s',
                    domain, record_name, exc,
                )

    try:
        if challenge_type == 'dns-01':
            # Setup DNS challenges using data already computed by create_order
            for domain, challenge_info in challenges.items():
                dns_value = challenge_info.get('dns_txt_value')
                record_name = challenge_info.get(
                    'dns_txt_name', f"_acme-challenge.{strip_wildcard(domain)}"
                )

                if not dns_value:
                    raise Exception(f"No DNS challenge value for {domain}")

                with txt_record_lock(record_name):
                    success_dns, msg = dns_provider.create_txt_record(
                        domain=strip_wildcard(domain),
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
                    "DNS propagation not confirmed locally after %ss for: %s, "
                    "submitting to the CA anyway",
                    timeout, ', '.join(check['missing']),
                )
            else:
                logger.info("DNS propagation confirmed after %ss", check['waited'])

        elif challenge_type == 'http-01':
            probe = wait_for_http01(challenges, HTTP01_RENEWAL_WAIT)
            if not probe['ok']:
                reason = '; '.join(probe['reasons'].values())
                new_order.error_message = f'HTTP-01 file not reachable, order left pending: {reason}'
                commit_or_rollback(logger, "Could not persist HTTP-01 self-check failure")
                raise RenewalBlocked(new_order.error_message)
            new_order.error_message = None  # left by an earlier blocked attempt
            # Before the CA is called: a pending write would hold the database's write lock
            commit_or_rollback(logger, "Could not clear the HTTP-01 self-check failure")

        # The propagation wait may be long: still this renewal's order before the CA is asked
        if not lease.refresh():
            if not reused_order:
                _discard_failed_renewal_order(new_order)  # pending: no other renewal resumes it
            raise RenewalInProgress(LEASE_LOST)

        # Submit challenges for validation
        for domain in challenges.keys():
            success_ch, msg = acme_client.verify_challenge(new_order, domain)
            if not success_ch:
                logger.warning(f"Challenge submission warning for {domain}: {msg}")

        # Wait for validation
        logger.info("Waiting for ACME validation...")
        status, order_data = acme_client.wait_for_order(new_order)
        if status == 'invalid':
            raise Exception(
                f"Order became invalid: {_order_invalid_detail(acme_client, new_order, order_data)}"
            )
        if status != 'ready':
            raise Exception(f"Order not ready after polling (status: {status})")

        # Writes the certificate into the renewed row and folds new_order into ``order``
        success_fin, message_fin, cert_id = acme_client.finalize_order(new_order, renews=order, lease=lease)

        if message_fin == LEASE_LOST:
            raise RenewalInProgress(LEASE_LOST)
        if not success_fin:
            raise Exception(f"Order finalization failed: {message_fin}")

        if not cert_id:
            raise Exception("Certificate import failed during finalization")

        return cert_id
    except (RenewalBlocked, RenewalInProgress):
        raise  # a blocked HTTP-01 order stays pending; a taken-over one is its new holder's
    except Exception:
        if not reused_order:
            _discard_failed_renewal_order(new_order)
        raise
    finally:
        if dns_txt_created:
            _cleanup_dns_txt_records()


def _order_invalid_detail(acme_client, order, order_data) -> str:
    """The CA's reason for an invalid order: the order's error, else the failed authorization's."""
    error = (order_data or {}).get('error') or {}
    detail = error.get('detail') if isinstance(error, dict) else None
    if detail:
        return str(detail)
    for domain in order.challenges_dict:
        status, authz = acme_client.check_authorization_status(order, domain)
        if status == 'invalid':
            return f"{domain}: {AcmeClientService._authz_error_detail(authz) or 'authorization invalid'}"
    return 'no detail from the CA'


# Statuses a renewal order can hold before its finalize request is sent.
_NOTHING_ISSUED = ('pending', 'validating', 'ready', 'invalid')


def _discard_failed_renewal_order(new_order) -> None:
    """A renewal that failed before its finalize was sent leaves no order behind.

    Any other status is kept: the CA may still issue, and the order holds the way back to it.
    """
    try:
        if new_order.status not in _NOTHING_ISSUED:
            return
        db.session.delete(new_order)
        commit_or_rollback(logger, f"Could not remove the failed renewal order {new_order.id}")
    except Exception as exc:  # never hide the renewal's own error
        logger.warning("Could not remove the failed renewal order: %s", exc)
