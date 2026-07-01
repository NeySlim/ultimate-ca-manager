"""
ACME Client Orders Routes
GET    /api/v2/acme/client/orders
GET    /api/v2/acme/client/orders/<id>
POST   /api/v2/acme/client/request
POST   /api/v2/acme/client/orders/<id>/verify
GET    /api/v2/acme/client/orders/<id>/status
POST   /api/v2/acme/client/orders/<id>/finalize
DELETE /api/v2/acme/client/orders/<id>
POST   /api/v2/acme/client/orders/<id>/renew
"""

import logging
import threading
import time
from flask import request, current_app

from api.v2.acme_client import bp
from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit
from models import db, DnsProvider, AcmeClientOrder, SystemConfig
from services.acme.acme_client_service import AcmeClientService, AUTHZ_INVALID_USER_MSG
from services.audit_service import AuditService
from utils.dns_txt_lookup import log_public_resolver_status, txt_record_present

logger = logging.getLogger(__name__)

# DNS-01 propagation: poll for the expected TXT record before telling the CA to
# validate, instead of a fixed sleep (#140). Timeout is configurable (up to
# 3600s). The automated path runs in a background thread (see
# _run_auto_poll_background), so it is NOT constrained by the gunicorn worker
# timeout and honors the full configured timeout.
_DNS_SELFCHECK_DEFAULT_TIMEOUT = 120
_DNS_SELFCHECK_INTERVAL = 5


def _dns_propagation_timeout() -> int:
    cfg = SystemConfig.query.filter_by(key='acme.client.dns_propagation_timeout').first()
    try:
        return max(0, int(cfg.value)) if cfg and cfg.value is not None else _DNS_SELFCHECK_DEFAULT_TIMEOUT
    except (ValueError, TypeError):
        return _DNS_SELFCHECK_DEFAULT_TIMEOUT


def _txt_present(name: str, expected: str) -> bool:
    """True if the DNS TXT record `name` currently serves the `expected` value."""
    return txt_record_present(name, expected)


def _dns_selfcheck(challenges: dict, timeout: int) -> dict:
    """Poll DNS until every dns-01 TXT record is visible, or until timeout.

    Each poll queries configured/authoritative resolvers plus 9.9.9.9, 8.8.8.8
    and 1.1.1.1 explicitly (logged per resolver). A domain is ready when any of
    these paths returns the expected TXT.

    Returns {'ok': bool, 'missing': [domains], 'waited': seconds}. Non-dns-01
    challenges (no dns_txt_value) are ignored.
    """
    pending = {d: c for d, c in challenges.items() if c.get('dns_txt_value')}
    waited = 0
    while pending:
        for domain in list(pending):
            c = pending[domain]
            txt_name = c['dns_txt_name']
            txt_value = c['dns_txt_value']
            if _txt_present(txt_name, txt_value):
                logger.info(f'DNS TXT confirmed for {domain} ({txt_name})')
                del pending[domain]
            else:
                log_public_resolver_status(txt_name, txt_value)
        if not pending or waited >= timeout:
            break
        time.sleep(_DNS_SELFCHECK_INTERVAL)
        waited += _DNS_SELFCHECK_INTERVAL
    return {'ok': not pending, 'missing': list(pending), 'waited': waited}


@bp.route('/api/v2/acme/client/orders', methods=['GET'])
@require_auth(['read:acme'])
def list_orders():
    """List all ACME client orders"""
    status = request.args.get('status')
    environment = request.args.get('environment')

    query = AcmeClientOrder.query

    if status:
        query = query.filter_by(status=status)
    if environment:
        query = query.filter_by(environment=environment)

    orders = query.order_by(AcmeClientOrder.created_at.desc()).limit(100).all()

    return success_response(data=[o.to_dict() for o in orders])


@bp.route('/api/v2/acme/client/orders/<int:order_id>', methods=['GET'])
@require_auth(['read:acme'])
def get_order(order_id):
    """Get a specific ACME client order"""
    order = AcmeClientOrder.query.get(order_id)
    if not order:
        return error_response('Order not found', 404)

    return success_response(data=order.to_dict())


@bp.route('/api/v2/acme/client/request', methods=['POST'])
@require_auth(['write:acme'])
def request_certificate():
    """
    Request a new certificate from Let's Encrypt.

    Body:
    {
        "domains": ["example.com", "www.example.com"],
        "email": "admin@example.com",  // Optional, uses default if not set
        "challenge_type": "dns-01",    // dns-01 or http-01
        "environment": "staging",      // staging or production
        "dns_provider_id": 1           // Required for dns-01
    }
    """
    data = request.json
    if not data:
        return error_response('Request body required', 400)

    domains = data.get('domains', [])
    if not domains:
        return error_response('At least one domain is required', 400)
    if not isinstance(domains, list):
        return error_response('domains must be a list', 400)
    # RFC 1035 caps a single FQDN at 253 chars; ACME servers further cap the
    # number of identifiers per order (LE = 100). Enforce locally to avoid
    # passing junk upstream and to bound CSR size.
    if len(domains) > 100:
        return error_response('Too many domains (max 100 per order)', 400)

    import re as _re
    # FQDN: labels of 1-63 chars (alnum + hyphen, no leading/trailing hyphen),
    # 1+ labels separated by dots; allow leading "*." for wildcards.
    _label = r'(?!-)[A-Za-z0-9-]{1,63}(?<!-)'
    _fqdn_re = _re.compile(rf'^(\*\.)?({_label}\.)+{_label}$')
    for domain in domains:
        if not isinstance(domain, str) or not domain:
            return error_response('Invalid domain (empty or not a string)', 400)
        if len(domain) > 253:
            return error_response(f'Invalid domain (>253 chars): {domain[:60]}...', 400)
        if not _fqdn_re.match(domain):
            return error_response(f'Invalid domain syntax: {domain}', 400)

    # Get email (from request or settings)
    email = data.get('email')
    if not email:
        email_cfg = SystemConfig.query.filter_by(key='acme.client.email').first()
        if email_cfg:
            email = email_cfg.value
    if not email:
        return error_response('Email is required. Set it in settings or provide in request.', 400)

    # Challenge type
    challenge_type = data.get('challenge_type', 'dns-01')
    if challenge_type not in ['dns-01', 'http-01']:
        return error_response('Challenge type must be dns-01 or http-01', 400)

    # Environment — fall back to configured default, NOT hardcoded staging.
    # Without this, a frontend race (modal opened before settings finished loading)
    # silently downgrades a production-default install to staging (#26).
    environment = data.get('environment')
    if not environment:
        env_cfg = SystemConfig.query.filter_by(key='acme.client.environment').first()
        environment = env_cfg.value if env_cfg else 'staging'
    # Only Let's Encrypt staging/production are gated to those two values. A
    # selected custom CA (ZeroSSL...) derives 'custom' and is allowed.
    if environment not in ['staging', 'production', 'custom']:
        return error_response('Environment must be staging or production', 400)

    # Explicit ACME CA account selection (multi-CA). When provided, the chosen
    # AcmeClientAccount wins over environment/default resolution and is pinned
    # to the order so renewals stay on the same authority.
    acme_account_id = data.get('acme_account_id')
    if acme_account_id not in (None, ''):
        from models.acme_client_account import AcmeClientAccount
        try:
            acme_account_id = int(acme_account_id)
        except (TypeError, ValueError):
            return error_response('acme_account_id must be an integer', 400)
        selected_account = AcmeClientAccount.query.get(acme_account_id)
        if not selected_account:
            return error_response('ACME account not found', 404)
        # Drive environment from the selected account so the order/Audit row
        # records the real CA context (staging/production/custom).
        environment = selected_account.derived_environment()
    else:
        acme_account_id = None

    # DNS provider (required for dns-01)
    dns_provider_id = data.get('dns_provider_id')
    provider = None
    if challenge_type == 'dns-01' and dns_provider_id:
        provider = DnsProvider.query.get(dns_provider_id)
        if not provider:
            return error_response('DNS provider not found', 404)
        if not provider.enabled:
            return error_response('DNS provider is disabled', 400)

    # Wildcard domains require dns-01
    has_wildcard = any(d.startswith('*.') for d in domains)
    if has_wildcard and challenge_type != 'dns-01':
        return error_response('Wildcard domains require DNS-01 challenge', 400)

    # Key type for certificate
    key_type = data.get('key_type')
    if key_type and key_type not in ['RSA-2048', 'RSA-4096', 'EC-P256', 'EC-P384']:
        return error_response('Invalid key type', 400)

    # Create order
    try:
        client = AcmeClientService.for_issuance(
            environment=environment, account_id=acme_account_id
        )
        success, message, order = client.create_order(
            domains=domains,
            email=email,
            challenge_type=challenge_type,
            dns_provider_id=dns_provider_id
        )

        if not success:
            return error_response(message, 400)

        # Store key_type on order if specified
        if key_type:
            order.key_type = key_type
            ok, _err = safe_commit(logger, "Failed to persist order key_type")
            if not ok:
                return _err

        AuditService.log_action(
            action='acme_request',
            resource_type='acme_order',
            resource_id=str(order.id),
            resource_name=', '.join(domains),
            details=f'Requested certificate for {", ".join(domains)} ({environment})',
            success=True
        )

        # Set up DNS challenges if using dns-01
        challenge_info = {}
        challenge_warning = None
        auto_polling = False
        manual_dns = bool(provider) and provider.provider_type == 'manual'
        if challenge_type == 'dns-01':
            setup_success, setup_message, challenge_info = client.setup_dns_challenge(order)
            if not setup_success:
                challenge_warning = setup_message
            elif manual_dns:
                # Manual provider: the user must place the TXT record themselves,
                # which can take far longer than any auto-wait. Do NOT auto-submit
                # (that's what made manual DNS-01 fail, #140) — leave the order
                # pending so the user adds the record and clicks "Verify" when
                # ready (the verify endpoint self-checks DNS before submitting).
                logger.info(f'Order {order.id}: manual DNS provider — awaiting user verification')
            else:
                # Automated provider: run the DNS self-check → verify → poll →
                # finalize flow in a BACKGROUND thread (DNS propagation + CA
                # polling can exceed the gunicorn worker timeout). The request
                # returns immediately; the frontend polls the status endpoint.
                order.status = 'processing'
                ok, _err = safe_commit(logger, 'Failed to mark order as processing')
                if not ok:
                    return _err
                auto_polling = True
                _run_auto_poll_background(order.id, environment)

        response_data = {
            'order': order.to_dict(),
            'challenges': challenge_info,
            'manual_dns': manual_dns,
            'auto_polling': auto_polling,
        }
        if challenge_warning:
            response_data['challenge_warning'] = challenge_warning

        return success_response(
            data=response_data,
            message=challenge_warning or message,
            status=201
        )

    except Exception as e:
        logger.error(f'Failed to create ACME order: {e}')
        return error_response('Failed to create order', 500)


@bp.route('/api/v2/acme/client/orders/<int:order_id>/verify', methods=['POST'])
@require_auth(['write:acme'])
def verify_challenges(order_id):
    """
    Trigger challenge verification for an order.

    Body (optional):
    {
        "domain": "example.com"  // Verify specific domain, or all if not specified
    }
    """
    order = AcmeClientOrder.query.get(order_id)
    if not order:
        return error_response('Order not found', 404)

    if order.status not in ['pending', 'processing', 'validating']:
        return error_response(f'Order cannot be verified (status: {order.status})', 400)

    data = request.json or {}
    specific_domain = data.get('domain')
    force = bool(data.get('force'))

    try:
        client = AcmeClientService.for_order(order)

        results = {}
        challenges = order.challenges_dict

        domains_to_verify = [specific_domain] if specific_domain else list(challenges.keys())

        # DNS self-check before submitting: if the expected TXT record isn't
        # visible yet, don't submit (a failed validation marks the order invalid
        # and burns the token). Tell the user to wait and retry. `force` bypasses.
        if not force:
            to_check = {d: challenges[d] for d in domains_to_verify
                        if d in challenges and challenges[d].get('dns_txt_value')}
            if to_check:
                check = _dns_selfcheck(to_check, timeout=0)  # single pass, quick
                if not check['ok']:
                    return success_response(
                        data={'dns_not_ready': True, 'missing': check['missing'],
                              'order': order.to_dict()},
                        message=('TXT record not visible yet for '
                                 f'{", ".join(check["missing"])}. Add the record, '
                                 'wait for propagation, then verify again.'))

        for domain in domains_to_verify:
            if domain not in challenges:
                results[domain] = {'success': False, 'message': 'Domain not in order'}
                continue

            success, message = client.verify_challenge(order, domain)
            results[domain] = {'success': success, 'message': message}

        all_success = all(r['success'] for r in results.values())
        any_failed = any(not r['success'] for r in results.values())

        if all_success:
            # Check if LE has already validated (poll order status)
            try:
                le_status, _ = client.check_order_status(order)
                if le_status in ['ready', 'valid']:
                    order.status = le_status
                else:
                    order.status = 'validating'
            except Exception:
                order.status = 'validating'
        elif any_failed:
            invalid_hit = any(
                AUTHZ_INVALID_USER_MSG in (r.get('message') or '')
                for r in results.values() if not r.get('success')
            )
            if invalid_hit:
                order.status = 'invalid'
            else:
                order.status = 'pending'
            order.error_message = '; '.join(
                f"{d}: {r['message']}" for d, r in results.items() if not r['success']
            )

        ok, _err = safe_commit(logger, "Failed to persist verification results")
        if not ok:
            return _err

        return success_response(
            data={
                'results': results,
                'order': order.to_dict()
            },
            message='Challenges submitted for verification' if all_success else 'Some challenges failed'
        )

    except Exception as e:
        try:
            db.session.rollback()
        except Exception as rb_err:
            logger.error(f'Rollback failed during ACME challenge verification: {rb_err}')
        logger.error(f'ACME challenge verification failed: {e}')
        return error_response('Verification failed', 500)


@bp.route('/api/v2/acme/client/orders/<int:order_id>/status', methods=['GET'])
@require_auth(['read:acme'])
def check_order_status(order_id):
    """Check current order status from ACME server"""
    order = AcmeClientOrder.query.get(order_id)
    if not order:
        return error_response('Order not found', 404)

    try:
        client = AcmeClientService.for_order(order)
        status, data = client.check_order_status(order)

        return success_response(data={
            'status': status,
            'order': order.to_dict(),
            'acme_data': data
        })

    except Exception as e:
        logger.error(f'ACME order status check failed: {e}')
        return error_response('Status check failed', 500)


@bp.route('/api/v2/acme/client/orders/<int:order_id>/finalize', methods=['POST'])
@require_auth(['write:acme'])
def finalize_order(order_id):
    """Finalize order and obtain certificate"""
    order = AcmeClientOrder.query.get(order_id)
    if not order:
        return error_response('Order not found', 404)

    if order.status == 'issued':
        return error_response('Order already issued', 400)

    try:
        client = AcmeClientService.for_order(order)
        success, message, cert_id = client.finalize_order(order)

        if success:
            # Clean up DNS records
            client.cleanup_dns_challenge(order)

            AuditService.log_action(
                action='acme_finalize',
                resource_type='acme_order',
                resource_id=str(order_id),
                resource_name=f'Order {order_id}',
                details=f'Finalized ACME order {order_id}, certificate ID: {cert_id}',
                success=True
            )

            return success_response(
                data={
                    'order': order.to_dict(),
                    'certificate_id': cert_id
                },
                message=message
            )
        else:
            return error_response(message, 400)

    except Exception as e:
        logger.error(f'ACME order finalization failed: {e}')
        return error_response('Finalization failed', 500)


@bp.route('/api/v2/acme/client/orders/<int:order_id>', methods=['DELETE'])
@require_auth(['delete:acme'])
def cancel_order(order_id):
    """Cancel/delete an order"""
    order = AcmeClientOrder.query.get(order_id)
    if not order:
        return error_response('Order not found', 404)

    # Clean up DNS if needed
    if order.challenge_type == 'dns-01' and order.dns_provider_id:
        try:
            client = AcmeClientService.for_order(order)
            client.cleanup_dns_challenge(order)
        except Exception:
            pass  # Best effort cleanup

    order_domains = ', '.join([d.get('value', '') for d in (order.identifiers_list if hasattr(order, 'identifiers_list') else [])]) or f'Order {order_id}'
    db.session.delete(order)
    ok, _err = safe_commit(logger, "Failed to cancel ACME order")
    if not ok:
        return _err

    AuditService.log_action(
        action='acme_order_cancel',
        resource_type='acme_order',
        resource_id=str(order_id),
        resource_name=order_domains,
        details=f'Cancelled/deleted ACME order {order_id}',
        success=True
    )

    return success_response(message='Order deleted')


@bp.route('/api/v2/acme/client/orders/<int:order_id>/renew', methods=['POST'])
@require_auth(['write:acme'])
def renew_order(order_id):
    """Manually trigger renewal for an order"""
    order = AcmeClientOrder.query.get(order_id)
    if not order:
        return error_response('Order not found', 404)

    if order.status not in ('valid', 'issued'):
        return error_response('Only valid/issued orders can be renewed', 400)

    try:
        from services.acme_renewal_service import renew_certificate

        success, message = renew_certificate(order)

        if success:
            AuditService.log_action(
                action='acme_renew',
                resource_type='acme_order',
                resource_id=str(order_id),
                resource_name=f'Order {order_id}',
                details=f'Renewed ACME order {order_id}',
                success=True
            )
            return success_response(
                data={'order': order.to_dict()},
                message=message
            )
        else:
            return error_response(message, 400)

    except Exception as e:
        logger.error(f'ACME certificate renewal failed: {e}')
        return error_response('Renewal failed', 500)


def _auto_poll_and_finalize(client, order) -> dict:
    """Wait for DNS propagation, verify challenges, poll until ready, auto-finalize.

    Mirrors the renewal service flow (DNS wait → verify → poll → finalize).
    Runs in a background thread (see _run_auto_poll_background), so it honors the
    full configured DNS propagation timeout and is NOT constrained by the
    gunicorn worker timeout. Updates order.status / order.error_message at each
    transition (committed) so the status endpoint reflects progress. Returns a
    status dict (used for logging and, under TESTING, embedded in the response).
    """
    def _set_status(status, error_message=None):
        """Persist a status transition on the order (best-effort)."""
        try:
            order.status = status
            if error_message is not None:
                order.error_message = error_message
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f'Failed to persist status={status} for order {order.id}: {e}')

    result = {
        'dns_propagation_wait': False,
        'challenge_submitted': False,
        'polling_status': None,
        'finalized': False,
        'certificate_id': None,
        'error': None,
    }

    try:
        challenges = order.challenges_dict
        if not challenges:
            result['error'] = 'No challenges for this order'
            _set_status('pending', result['error'])
            return result

        _set_status('processing')

        # 1. Self-check DNS propagation: poll for the expected TXT records up to
        #    the configured timeout before asking the CA to validate (#140).
        timeout = _dns_propagation_timeout()
        check = _dns_selfcheck(challenges, timeout)
        result['dns_propagation_wait'] = True
        if check['ok']:
            logger.info(f'DNS propagation confirmed after {check["waited"]}s')
        else:
            logger.warning(
                f'DNS self-check timed out after {timeout}s; TXT not visible for '
                f'{check["missing"]} — submitting anyway (CA may still validate)')

        # 2. Submit challenges for validation
        for domain in challenges:
            success, msg = client.verify_challenge(order, domain)
            if success:
                result['challenge_submitted'] = True
                logger.info(f'Challenge submitted for {domain}')
            else:
                logger.warning(f'Challenge submission failed for {domain}: {msg}')

        _set_status('validating')

        poll = client.get_poll_settings()
        max_wait = poll['order_poll_timeout_sec']
        poll_interval = poll['order_poll_interval_sec']
        elapsed = 0
        while elapsed < max_wait:
            time.sleep(poll_interval)
            elapsed += poll_interval

            invalid = client.find_invalid_authorization(order)
            if invalid:
                domain, msg = invalid
                result['error'] = msg
                logger.warning(f'Authorization invalid for {domain} on order {order.id}: {msg}')
                _set_status('invalid', msg)
                break

            le_status, le_data = client.check_order_status(order)
            result['polling_status'] = le_status
            logger.info(f'ACME order {order.id} status after {elapsed}s: {le_status}')

            if le_status in ('ready', 'valid'):
                # 4. Auto-finalize (finalize_order sets status='issued' on success)
                fin_success, fin_msg, cert_id = client.finalize_order(order)
                if fin_success:
                    result['finalized'] = True
                    result['certificate_id'] = cert_id
                    logger.info(f'Auto-finalized order {order.id}, cert ID: {cert_id}')
                    # Clean up DNS records
                    try:
                        client.cleanup_dns_challenge(order)
                    except Exception as cleanup_err:
                        logger.warning(f'DNS cleanup after auto-finalize: {cleanup_err}')
                else:
                    result['error'] = fin_msg
                    logger.warning(f'Auto-finalize failed: {fin_msg}')
                    _set_status('pending', fin_msg)
                break

            if le_status == 'invalid':
                result['error'] = f'Order became invalid: {le_data.get("error", {}).get("detail", "Unknown")}'
                _set_status('invalid', result['error'])
                break

            if elapsed >= max_wait:
                invalid = client.find_invalid_authorization(order)
                if invalid:
                    _, msg = invalid
                    result['error'] = msg
                    _set_status('invalid', msg)
                else:
                    result['error'] = f'Timeout after {max_wait}s (status: {le_status})'
                    _set_status('pending', result['error'])
                break

    except Exception as e:
        result['error'] = 'ACME order failed, see server logs for details'
        logger.error(f'Auto-poll error for order {order.id}: {e}', exc_info=True)
        # Reset to 'pending' so the manual Verify/Finalize path can recover.
        _set_status('pending', result['error'])

    logger.info(f'Auto-poll result for order {order.id}: status={result.get("polling_status")}, finalized={result["finalized"]}, error={result["error"]}')

    return result


def _run_auto_poll_background(order_id: int, environment: str) -> None:
    """Run the automated DNS-01 flow (self-check → verify → poll → finalize) in a
    background thread.

    The synchronous HTTP request must not block on DNS propagation + CA polling
    (can exceed the gunicorn worker timeout). Instead request_certificate kicks
    this off and returns immediately with the order in 'processing' state; the
    frontend polls /orders/<id>/status for progress.

    Each background thread pushes its own app context (→ its own SQLAlchemy
    session), independent of the request's session — same pattern the scheduler
    uses for its tasks. Under TESTING we run synchronously instead, because the
    test DB uses a single shared (StaticPool) connection that a background
    thread would contend with.
    """
    app = current_app._get_current_object()

    def _worker():
        with app.app_context():
            try:
                order = AcmeClientOrder.query.get(order_id)
                if not order:
                    logger.error(f'Auto-poll background: order {order_id} not found')
                    return
                # Skip if the order was cancelled/finalized between request and run.
                if order.status in ('issued', 'invalid', 'expired'):
                    logger.info(f'Auto-poll background: order {order_id} already {order.status}, skipping')
                    return
                client = AcmeClientService.for_order(order)
                _auto_poll_and_finalize(client, order)
            except Exception as e:
                logger.error(f'Auto-poll background failed for order {order_id}: {e}', exc_info=True)
                try:
                    with app.app_context():
                        order = AcmeClientOrder.query.get(order_id)
                        if order and order.status not in ('issued', 'invalid', 'expired'):
                            order.status = 'pending'
                            order.error_message = 'Background processing failed; retry manually'
                            db.session.commit()
                except Exception:
                    db.session.rollback()

    # Under TESTING the DB is a single shared SQLite connection (StaticPool):
    # a background thread would contend with the test request's session. Run
    # inline so the flow remains deterministic and testable.
    if app.config.get('TESTING'):
        _worker()
        return

    thread = threading.Thread(target=_worker, name=f'acme-autopoll-{order_id}', daemon=True)
    thread.start()
    logger.info(f'Started background auto-poll thread for order {order_id}')
