"""
ACME Auto-Renewal Service
Automatically renews Let's Encrypt certificates before expiry.
"""
import base64
import json
import logging
import random
from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError

from models import CA, Certificate, DnsProvider, RevokedSerial, SystemConfig, db
from models.acme_models import AcmeClientOrder
from models.compromised_key import remember_if_compromised
from services.acme import dns_providers
from services.acme.acme_client_service import ACCOUNT_GONE, AcmeClientService
from services.acme.compromised_keys import refuse_compromised_csr
from services.acme.dns_selfcheck import dns_propagation_timeout, wait_for_challenges
from services.acme.http01 import wait_for_http01
from services.acme import client_certificates
from services.acme.client_certificates import KEY_MISMATCH
from services.acme.order_housekeeping import purge_stale_pending_orders
from services.acme.order_lease import BUSY, LEASE_LOST, OrderLease, RenewalInProgress
from services.audit.staging import stage_audit_entry
from services.audit_service import AuditService
from services.cert_service import CertificateService
from services.webhook_service import emit_acme_renewal_failed, emit_acme_revocation_failed
from utils.revocation_reasons import reason_code
from utils.spki_digest import certificate_key_sha256
from utils.acme_debug import acme_log
from utils.datetime_utils import utc_now
from utils.san_parse import strip_wildcard
from services.acme.dns_txt_lock import txt_record_lock
from services.acme.single_txt_value import keep_for_another_order, txt_lock_name
from utils.db_transaction import commit_or_rollback

logger = logging.getLogger(__name__)

# Default: renew 30 days before expiry
DEFAULT_RENEWAL_DAYS = 30
# From this many failures on, an order is still renewed, once a day
MAX_RENEWAL_FAILURES = AcmeClientOrder.RENEWAL_FAILURES_BEFORE_DAILY
DAILY_RETRY = timedelta(days=1)
# UCM serves its own HTTP-01 tokens, so the file is there at once or not at all.
HTTP01_RENEWAL_WAIT = 10


RENEWAL_ORDER_GONE = 'The order is gone at the CA; the next pass opens a new one'
REUSE_SOURCE_GONE = ('The certificate holding the key this order reuses was deleted: request a new '
                     'certificate for these names, with a new key or the key of another certificate')


class RenewalBlocked(Exception):
    """Renewal stopped before reaching the CA; the message is meant for the operator."""

# Successful ARI responses are cached until the upstream Retry-After time.
# The scheduler is process-local, so this is sufficient to prevent repeated
# polling on each scheduler tick without adding persistent schema state.
_ARI_CACHE = {}
# Interval of the scheduled renewal pass (acme_auto_renewal task)
RENEWAL_PASS_SECONDS = 21600
# RFC 9773 §4.2: the renewal instant drawn per certificate, kept while its window is unchanged
_ARI_PICKS = {}
_ARI_MIN_RETRY = timedelta(minutes=1)
_ARI_MAX_RETRY = timedelta(days=1)


def _renewal_instant(cache_key, window):
    """A uniform random instant of the suggested window, drawn once per window."""
    bounds = (window['start'], window['end'])
    picked = _ARI_PICKS.get(cache_key)
    if picked and picked[0] == bounds:
        return picked[1]
    instant = bounds[0] + (bounds[1] - bounds[0]) * random.random()
    _ARI_PICKS[cache_key] = (bounds, instant)
    return instant


def renewal_client(order):
    """The client of the CA account ``order`` was issued under.

    RenewalBlocked when the order names an account that is gone; an order that names
    none (older than per-order accounts) still resolves by environment."""
    client = AcmeClientService.for_existing_order(order)
    if client is None:
        raise RenewalBlocked(ACCOUNT_GONE)
    return client


def _cached_renewal_info(order, certificate, now):
    """Return upstream ARI data while honoring Retry-After."""
    cache_key = (order.acme_client_account_id, certificate.id)
    # RFC 9773 §4.3: an expired certificate's RenewalInfo is never checked
    valid_to = getattr(certificate, 'valid_to', None)
    if valid_to is not None and valid_to < now:
        _ARI_CACHE.pop(cache_key, None)
        return None
    cached = _ARI_CACHE.get(cache_key)
    if cached and cached.get('retry_after') and now < cached['retry_after']:
        return cached['info']

    client = renewal_client(order)
    info = client.get_renewal_info(certificate)
    if info and info.get('retry_after'):
        # RFC 9773 §4.3.2: the checking interval is kept between one minute and one day
        retry_after = min(max(info['retry_after'], now + _ARI_MIN_RETRY), now + _ARI_MAX_RETRY)
        _ARI_CACHE[cache_key] = {
            'info': info,
            'retry_after': retry_after,
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
                # RFC 9773 §4.2 step 5: an instant before the next pass is renewed now
                instant = _renewal_instant((order.acme_client_account_id, certificate.id),
                                           info['suggested_window'])
                return instant <= now + timedelta(seconds=RENEWAL_PASS_SECONDS)
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
        # Never the order another order's renewal opened
        or_(AcmeClientOrder.renewal_of_order_id.is_(None), AcmeClientOrder.renewal_of_order_id == order.id),
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
                           caref=certificate.caref, revoked=bool(certificate.revoked),
                           revoke_reason=certificate.revoke_reason)


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
    # The row now holds the new key: the digest comes from the replaced certificate
    row.public_key_sha256 = certificate_key_sha256(base64.b64encode(replaced.pem))
    commit_or_rollback(logger, f"Revocation record of serial {replaced.serial} not saved")


def _revoke_replaced_certificate(acme_client, replaced, in_place, order=None):
    """Best-effort local and upstream revocation after successful renewal.

    Renewed in place, the row holds the new certificate: only the old serial is recorded,
    and the CA is sent the old certificate as it was before the renewal. A revocation the CA
    does not confirm is kept on ``order`` and sent again by the next passes.
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

    label = f"certificate {replaced.id} (serial {replaced.serial})"
    reason = _upstream_reason(replaced)
    try:
        error = send_upstream_revocation(acme_client, replaced.pem, reason, label)
    except Exception as exc:
        error = str(exc)
    if error is None:
        return
    logger.warning("Upstream revocation of %s failed: %s", label, error)
    if order is not None:
        not_after = replaced.valid_to or utc_now() + timedelta(days=90)
        _owe_upstream_revocation(order, {
            'serial': replaced.serial, 'certificate': replaced.pem.decode(), 'reason': reason,
            'not_after': not_after.isoformat()}, error)


_ACME_ERROR = 'urn:ietf:params:acme:error:'


def _problem(response):
    """``(type, detail)`` of an ACME problem document, empty strings when there is none."""
    try:
        body = response.json()
    except Exception:
        body = None
    if not isinstance(body, dict):
        return '', ''
    return str(body.get('type') or ''), str(body.get('detail') or '')


def _revoked_upstream(response) -> bool:
    # RFC 8555 §7.6: done, or done before (alreadyRevoked)
    return 200 <= response.status_code < 300 or _problem(response)[0] == _ACME_ERROR + 'alreadyRevoked'


def send_upstream_revocation(acme_client, pem, reason, label):
    """Revoke ``pem`` at the CA: None once it is revoked there, else the reason it is not.

    RFC 8555 §7.6 lets the CA refuse a reason (badRevocationReason): the request is then
    sent again without one, and the log says so."""
    response = acme_client.revoke_certificate(pem, reason=reason)
    if _revoked_upstream(response):
        return None
    if _problem(response)[0] == _ACME_ERROR + 'badRevocationReason' and reason is not None:
        logger.warning("The CA refused revocation reason %s for %s: revoking it without a reason",
                       reason, label)
        response = acme_client.revoke_certificate(pem, reason=None)
        if _revoked_upstream(response):
            return None
    _type, detail = _problem(response)
    return f"HTTP {response.status_code}{': ' + detail if detail else ''}"


# Local reasons the CA is told; any other leaves the optional field out (never a hold)
_UPSTREAM_REASONS = {1, 3, 4, 5}


def _upstream_reason(replaced):
    """The RFC 5280 §5.3.1 code sent to the CA, or None: superseded for a row renewed,
    the local reason of a revoked row when it is one a replaced certificate may carry."""
    if not replaced.revoked:
        return 4
    code = reason_code(replaced.revoke_reason)
    return code if code in _UPSTREAM_REASONS else None


def _owe_upstream_revocation(order, entry, error) -> None:
    """Keep ``entry`` on ``order`` for the next pass, and announce the failure."""
    entry.update(attempts=entry.get('attempts', 0) + 1, error=error,
                 last_attempt_at=utc_now().isoformat())
    owed = [e for e in order.upstream_revocations_list if e.get('serial') != entry['serial']]
    order.upstream_revocations_list = owed + [entry]
    if commit_or_rollback(logger, f"Revocation owed by the CA for order {order.id} not kept"):
        payload = order.to_dict()
        payload.pop('challenges', None)
        emit_acme_revocation_failed(payload, entry['serial'], error, entry['attempts'])


def _revocation_due(entry, now) -> bool:
    """Every pass for the first attempts; then once a day, as a failing renewal."""
    if entry.get('attempts', 0) < MAX_RENEWAL_FAILURES or not entry.get('last_attempt_at'):
        return True
    return now - datetime.fromisoformat(entry['last_attempt_at']) >= DAILY_RETRY


def retry_upstream_revocations() -> int:
    """Send again the revocations the CA refused or never received; the number still owed."""
    now = utc_now()
    owed_total = 0
    for order_id, in db.session.query(AcmeClientOrder.id).filter(
            AcmeClientOrder.upstream_revocations.isnot(None)).all():
        lease = OrderLease.take(order_id)
        if lease is None:  # a renewal of the order runs: the next pass retries
            continue
        try:
            owed_total += _retry_order_revocations(db.session.get(AcmeClientOrder, order_id), now)
        except Exception as exc:
            db.session.rollback()
            logger.warning("Revocations owed for ACME order %s not retried: %s", order_id, exc)
        finally:
            lease.release()
    return owed_total


def _retry_order_revocations(order, now) -> int:
    entries = order.upstream_revocations_list
    alive = [e for e in entries if datetime.fromisoformat(e['not_after']) > now]
    for gone in [e for e in entries if e not in alive]:
        logger.info("Certificate %s expired before its CA confirmed the revocation: no longer sent",
                    gone.get('serial'))
    order.upstream_revocations_list = alive
    commit_or_rollback(logger, f"Revocations owed for order {order.id} not updated")
    due = [e for e in alive if _revocation_due(e, now)]
    if not due:
        return len(alive)
    client = AcmeClientService.for_existing_order(order)
    for entry in due:
        label = f"certificate serial {entry['serial']}"
        if client is None:
            error = ACCOUNT_GONE
        else:
            try:
                error = send_upstream_revocation(client, entry['certificate'], entry.get('reason'), label)
            except Exception as exc:
                error = str(exc)
        if error is None:
            logger.info("The CA confirmed the revocation of %s", label)
            order.upstream_revocations_list = [e for e in order.upstream_revocations_list
                                               if e.get('serial') != entry['serial']]
            commit_or_rollback(logger, f"Revocation of {label} done but not recorded")
        else:
            logger.warning("Revocation of %s at the CA failed again: %s", label, error)
            _owe_upstream_revocation(order, entry, error)
    return len(order.upstream_revocations_list)


def _configured_renewal_days():
    """``acme.client.renewal_days`` (1 to 60), the default when unset or invalid."""
    row = SystemConfig.query.filter_by(key='acme.client.renewal_days').first()
    try:
        days = int(row.value) if row else DEFAULT_RENEWAL_DAYS
    except (TypeError, ValueError):
        return DEFAULT_RENEWAL_DAYS
    return min(60, max(1, days))


def _attempt_allowed(order, now):
    """Every pass below the failure threshold; past it, a day after the last failure."""
    if not order.renewal_retry_daily or order.last_error_at is None:
        return True
    return now - order.last_error_at >= DAILY_RETRY


def record_renewal_failure(order, error, manual=False):
    """Count, audit and announce one failed renewal of ``order``, scheduled or asked for;
    returns the message recorded."""
    message = 'Database error during renewal' if isinstance(error, SQLAlchemyError) else str(error)
    db.session.rollback()  # a failed flush would refuse the writes below
    order.renewal_failures = (order.renewal_failures or 0) + 1
    order.last_error_at = utc_now()
    order.error_message = message
    if not manual:  # in the counter's commit; a manual one names its user below
        stage_audit_entry(action='acme_order.auto_renewal_failed', resource_type='acme_order',
                          resource_id=str(order.id), resource_name=order.primary_domain,
                          details=f'Auto-renewal failed: {message}', success=False)
    if commit_or_rollback(logger, f"Failed to persist renewal failure for order {order.id}"):
        payload = order.to_dict()
        payload.pop('challenges', None)  # tokens and TXT values stay out of webhooks
        if manual:
            AuditService.log_action(action='acme_renew', resource_type='acme_order',
                                    resource_id=str(order.id), resource_name=payload.get('primary_domain'),
                                    details=f'Renewal failed: {message}', success=False)
        emit_acme_renewal_failed(payload, payload.get('renewal_failures'), message,
                                 payload.get('renewal_retry_daily'))
    return message


def _pass_outcome(failed, daily):
    """The scheduler's status for a pass: a warning while renewals fail or run once a day."""
    if not failed and not daily:
        return None
    parts = []
    if failed:
        parts.append(f'{failed} renewal(s) failed in this run')
    if daily:
        parts.append(f'{daily} order(s) retried once a day after {MAX_RENEWAL_FAILURES} failures')
    return {'status': 'warning', 'reason': '; '.join(parts)}


def scheduled_acme_renewal():
    """
    Scheduled task to check and renew ACME certificates.
    Called by scheduler service.
    """
    logger.info("Starting ACME auto-renewal check...")
    try:
        purge_stale_pending_orders()
    except Exception as exc:  # housekeeping never stops the renewals
        db.session.rollback()
        logger.warning("Stale pending ACME orders not purged: %s", exc)
    try:
        retry_upstream_revocations()
    except Exception as exc:
        db.session.rollback()
        logger.warning("Revocations owed by the CA not retried: %s", exc)

    # The Let's Encrypt tab's global switch; each order also has its own.
    switch = SystemConfig.query.filter_by(key='acme.client.renewal_enabled').first()
    if switch is not None and str(switch.value).lower() != 'true':
        logger.info("ACME auto-renewal is turned off")
        return {'status': 'skipped', 'reason': 'acme_renewal_off'}

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
        ).all()
        daily_ids = {order.id for order in eligible_orders if order.renewal_retry_daily}
        orders_to_renew = [
            order for order in eligible_orders
            if _attempt_allowed(order, now) and _order_is_due(order, now, threshold_date)
        ]
        
        if not orders_to_renew:
            logger.info("No certificates need renewal")
            return _pass_outcome(0, len(daily_ids))
        
        logger.info(f"Found {len(orders_to_renew)} certificate(s) to renew")
        
        failed = 0
        for order in orders_to_renew:
            order_id = order.id
            lease = OrderLease.take(order_id)
            if lease is None:
                logger.info("Order %s skipped: another renewal of it is running", order_id)
                continue
            try:
                renew_certificate(order, lease=lease)
                daily_ids.discard(order_id)
            except RenewalInProgress as e:
                logger.info("Order %s left to another renewal: %s", order_id, e)
            except Exception as e:
                logger.error(f"Failed to renew order {order_id}: {e}")
                failed += 1
                record_renewal_failure(order, e)
                if order.renewal_retry_daily:
                    daily_ids.add(order_id)
            finally:
                lease.release()
        
        logger.info("ACME auto-renewal check completed")
        return _pass_outcome(failed, len(daily_ids))
        
    except Exception as e:
        logger.error(f"ACME auto-renewal task failed: {e}")
        return {'status': 'failed', 'reason': str(e)}


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
    # Before the CA is asked: a renewal in place overwrites the revoked row and its key
    if old_certificate is not None and remember_if_compromised(old_certificate):
        commit_or_rollback(logger, f"Compromised key of certificate {old_certificate.id} not saved")
    if order.key_source == 'csr' and order.csr_pem:
        _refuse_compromised_order_csr(order)
    if (order.key_source == 'csr' and order.csr_pem and old_certificate is not None
            and old_certificate.crt and not old_certificate.revoked):
        # Refused before the CA is asked: each attempt would cost a certificate
        refusal = client_certificates.csr_key_refusal(old_certificate, order.csr_pem)
        if refusal:
            raise RenewalBlocked(refusal)

    # Initialize ACME client for the same CA that issued the original order
    acme_client = renewal_client(order)
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
        _revoke_replaced_certificate(acme_client, replaced, in_place=cert_id == old_certificate_id, order=order)

    return True, f"Successfully renewed (certificate ID: {cert_id})"


def _refuse_compromised_order_csr(order):
    """CompromisedKey before any order is opened: the CA would issue, the finalize refuse."""
    from utils.acme_csr import load_pem_csr
    try:
        csr = load_pem_csr(order.csr_pem)
    except ValueError as exc:
        raise RenewalBlocked(f'The CSR of this order cannot be read: {exc}')
    refuse_compromised_csr(csr)


# Statuses of a renewal order that may hold a finalization: kept for the next renewal.
_RESUMABLE = ('validating', 'ready', 'processing', 'valid', 'error')


def _kept_renewal_order(order, account_id):
    """The newest resumable order whose ``renewal_of_order_id`` names ``order``, or None.
    Those opened under another account than ``account_id`` cannot be finished: removed."""
    linked = AcmeClientOrder.query.filter(
        AcmeClientOrder.renewal_of_order_id == order.id,
        AcmeClientOrder.status.in_(_RESUMABLE),
    ).order_by(AcmeClientOrder.id.desc()).all()
    usable = next((c for c in linked if c.acme_client_account_id == account_id), None)
    for other in [c for c in linked if c.acme_client_account_id != account_id]:
        logger.warning("Renewal of order %s drops order %s: it was opened under another CA account",
                       order.id, other.id)
        _drop_kept_order(other)
    return usable


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
        if not dns_provider_model.enabled:
            raise RenewalBlocked(f'The DNS provider "{dns_provider_model.name}" of this order is disabled: '
                                 'enable it to renew')
        credentials = json.loads(dns_provider_model.credentials) if dns_provider_model.credentials else {}
        dns_provider = dns_providers.create_provider(
            dns_provider_model.provider_type,
            credentials,
        )
    
    reuse_src = None
    if (order.key_source or 'generate') == 'reuse':
        # The certificate this order issued, else the source of its first key
        held = [cid for cid in (order.certificate_id, order.source_certificate_id) if cid]
        reuse_src = next((cid for cid in held if db.session.get(Certificate, cid) is not None), None)
        if reuse_src is None:
            raise RenewalBlocked(REUSE_SOURCE_GONE)

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
        if new_order.renewal_of_order_id is None:
            new_order.renewal_of_order_id = order.id
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
    if reuse_src:
        new_order.source_certificate_id = reuse_src
    if not commit_or_rollback(logger, "Could not persist key source on renewal order"):
        logger.warning("Renewal will continue with the in-memory key source settings")
    
    challenges = new_order.challenges_dict
    dns_txt_created = False

    def _cleanup_dns_txt_records():
        for domain, challenge_info in challenges.items():
            record_name = challenge_info.get(
                'dns_txt_name', f"_acme-challenge.{strip_wildcard(domain)}"
            )
            value = challenge_info.get('dns_txt_value')
            if not value:
                # Deleting by name alone would take other orders' values with it
                logger.warning("Renewal DNS cleanup skipped for %s: no TXT value recorded", record_name)
                continue
            try:
                with txt_record_lock(txt_lock_name(dns_provider, record_name)):
                    if keep_for_another_order(dns_provider, record_name, new_order.id):
                        continue
                    result = dns_provider.delete_txt_record(
                        domain=strip_wildcard(domain),
                        record_name=record_name,
                        record_value=value,
                    )
                if isinstance(result, tuple) and not result[0]:
                    logger.warning('Failed to delete renewal DNS TXT for %s (%s): %s',
                                   domain, record_name, result[1])
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

                with txt_record_lock(txt_lock_name(dns_provider, record_name)):
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
        if status == 'gone':
            raise Exception(RENEWAL_ORDER_GONE)
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
        order_id = new_order.id  # read after the delete, it would flush it and fail
        db.session.delete(new_order)
        commit_or_rollback(logger, f"Could not remove the failed renewal order {order_id}")
    except Exception as exc:  # never hide the renewal's own error
        logger.warning("Could not remove the failed renewal order: %s", exc)
