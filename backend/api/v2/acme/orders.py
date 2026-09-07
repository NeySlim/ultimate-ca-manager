"""ACME orders, challenges, and history routes"""
import json

from flask import request
from models import db, AcmeAccount, AcmeOrder, AcmeAuthorization, AcmeChallenge, CA, Certificate
from models.acme_models import AcmeClientOrder, DnsProvider
from models.acme_client_account import AcmeClientAccount
from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.datetime_utils import utc_isoformat

from . import bp, logger, resolve_acme_account
from services.audit_service import AuditService
from services.acme.mixins.order import EXPIRED_AUTHORIZATION_DETAIL


def _challenge_was_attempted(challenge) -> bool:
    """True when the client answered this challenge and validation failed.

    A failed attempt is the only path that marks a single challenge invalid
    with a validation problem. Lazy expiry marks every pending challenge of
    the authorization invalid with the same expiry problem, so those rows do
    not count as attempts.
    """
    if challenge.status != 'invalid' or not challenge.error:
        return False
    try:
        problem = json.loads(challenge.error) if isinstance(challenge.error, str) else challenge.error
    except (TypeError, ValueError):
        return False
    return (problem or {}).get('detail') != EXPIRED_AUTHORIZATION_DETAIL


def order_validation_method(order) -> str:
    """Challenge type(s) that proved control of the order's identifiers.

    Reads the validated challenge(s) of each authorization rather than the
    first challenge row, which is always the first type offered (dns-01) and
    says nothing about what the client did (#338). When nothing was
    validated, the challenge(s) the client attempted and failed are named so
    an Invalid order still shows the method that was tried. An order whose
    challenges were never answered reads N/A.
    """
    performed, attempted = [], []
    for authz in order.authorizations:
        for challenge in authz.challenges:
            if challenge.status == 'valid':
                performed.append(challenge.type)
            elif _challenge_was_attempted(challenge):
                attempted.append(challenge.type)
    types = list(dict.fromkeys(performed or attempted))
    return ', '.join(t.upper() for t in types) if types else 'N/A'


@bp.route('/api/v2/acme/orders', methods=['GET'])
@require_auth(['read:acme'])
def list_acme_orders():
    """List local ACME server orders (paginated since #303)."""
    status = request.args.get('status')
    domain = (request.args.get('domain') or '').strip()
    try:
        page = max(1, int(request.args.get('page', 1)))
        per_page = min(200, max(1, int(request.args.get('per_page', 50))))
    except (TypeError, ValueError):
        page, per_page = 1, 50
    query = AcmeOrder.query
    if status:
        query = query.filter_by(status=status)
    if domain:
        query = query.filter(AcmeOrder.identifiers.contains(domain))

    total = query.count()
    orders = (query.order_by(AcmeOrder.created_at.desc())
              .offset((page - 1) * per_page).limit(per_page).all())

    data = []
    for order in orders:
        # Extract identifiers for display
        identifiers_str = ", ".join([i.get('value', '') for i in order.identifiers_list])

        # Get account info
        account = order.account
        account_name = account.account_id if account else "Unknown"

        data.append({
            'id': order.id,
            'order_id': order.order_id,
            'domain': identifiers_str,
            'account': account_name,
            'status': order.status.capitalize(),
            'expires': order.expires.strftime('%Y-%m-%d'),
            'method': order_validation_method(order),
            'certificate_id': order.certificate_id,
            'created_at': utc_isoformat(order.created_at)
        })

    return success_response(data={
        'items': data,
        'meta': {'page': page, 'per_page': per_page, 'total': total},
    })


@bp.route('/api/v2/acme/orders/<int:order_pk>', methods=['DELETE'])
@require_auth(['delete:acme'])
def delete_acme_order(order_pk):
    """Delete one local ACME server order with its authorizations and
    challenges (#303). The linked certificate, if any, is not touched."""
    from models.acme_models import AcmeAuthorization, AcmeChallenge

    order = db.session.get(AcmeOrder, order_pk)
    if not order:
        return error_response('Order not found', 404)
    try:
        for authz in list(order.authorizations):
            AcmeChallenge.query.filter_by(
                authorization_id=authz.authorization_id
            ).delete(synchronize_session=False)
            db.session.delete(authz)
        db.session.delete(order)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete ACME order {order_pk}: {e}")
        return error_response('Failed to delete order', 500)

    AuditService.log_action(
        action='acme_order_delete', resource_type='acme_order',
        resource_id=str(order_pk), resource_name=order.order_id,
        details='Local ACME order deleted', success=True,
    )
    return success_response(message='Order deleted')


@bp.route('/api/v2/acme/orders/purge', methods=['POST'])
@require_auth(['delete:acme'])
def purge_acme_orders():
    """Run the expired-order purge now (#303)."""
    from services.acme.order_purge import purge_expired_orders

    try:
        stats = purge_expired_orders()
    except Exception:
        return error_response('Purge failed', 500)
    AuditService.log_action(
        action='acme_order_purge', resource_type='acme_order', resource_id='*',
        resource_name='Expired local ACME orders',
        details=f"Purged {stats['orders']} orders, "
                f"{stats['authorizations']} authorizations, "
                f"{stats['challenges']} challenges", success=True,
    )
    return success_response(data=stats, message='Purge complete')


@bp.route('/api/v2/acme/accounts/<string:account_id>/orders', methods=['GET'])
@require_auth(['read:acme'])
def list_account_orders(account_id):
    """List orders for a specific ACME account.

    Includes both:
      * direct local-server orders (``AcmeOrder``)
      * proxy orders made via ``/acme/proxy`` upstream to LE (``AcmeClientOrder``
        with ``is_proxy_order=True`` linked through ``account_id``)

    Issue #71: previously only local orders were shown, leaving proxy users
    unable to see their certificate history from the account detail.
    """
    account = resolve_acme_account(account_id)
    if not account:
        return error_response('Account not found', 404)

    orders = AcmeOrder.query.filter_by(account_id=account.account_id).order_by(
        AcmeOrder.created_at.desc()
    ).limit(50).all()

    data = []
    for order in orders:
        identifiers_str = ", ".join([i.get('value', '') for i in order.identifiers_list])

        data.append({
            'id': order.id,
            'order_id': order.order_id,
            'domain': identifiers_str,
            'status': order.status.capitalize(),
            'expires': order.expires.strftime('%Y-%m-%d') if order.expires else None,
            'method': order_validation_method(order),
            'created_at': utc_isoformat(order.created_at),
            'source': 'local',
        })

    proxy_orders = AcmeClientOrder.query.filter_by(
        account_id=account.account_id,
        is_proxy_order=True,
    ).order_by(AcmeClientOrder.created_at.desc()).limit(50).all()

    for po in proxy_orders:
        domains = po.domains_list
        data.append({
            'id': f'proxy-{po.id}',
            'order_id': po.order_url or po.upstream_order_url,
            'domain': ", ".join(domains) if domains else (po.primary_domain or ''),
            'status': (po.status or '').capitalize(),
            'expires': po.expires_at.strftime('%Y-%m-%d') if po.expires_at else None,
            'method': (po.challenge_type or 'N/A').upper(),
            'created_at': utc_isoformat(po.created_at),
            'source': 'proxy',
            'environment': po.environment,
            'certificate_id': po.certificate_id,
        })

    # Sort merged list newest-first.
    data.sort(key=lambda o: o.get('created_at') or '', reverse=True)

    return success_response(data=data)


@bp.route('/api/v2/acme/accounts/<string:account_id>/challenges', methods=['GET'])
@require_auth(['read:acme'])
def list_account_challenges(account_id):
    """List challenges for a specific ACME account (accepts numeric PK or RFC 8555 account_id)"""
    account = resolve_acme_account(account_id)
    if not account:
        return error_response('Account not found', 404)

    # Get all orders for this account
    orders = AcmeOrder.query.filter_by(account_id=account.account_id).all()

    data = []
    for order in orders:
        for authz in order.authorizations:
            domain = authz.identifier_value or str(authz.identifier)
            for challenge in authz.challenges:
                data.append({
                    'id': challenge.id,
                    'type': challenge.type.upper(),
                    'status': challenge.status.capitalize(),
                    'domain': domain,
                    'token': challenge.token[:20] + '...' if challenge.token and len(challenge.token) > 20 else challenge.token,
                    'validated': utc_isoformat(challenge.validated),
                    'order_id': order.order_id,
                    'created_at': utc_isoformat(challenge.created_at) if hasattr(challenge, 'created_at') and challenge.created_at else None
                })

    return success_response(data=data)


@bp.route('/api/v2/acme/history', methods=['GET'])
@require_auth(['read:acme'])
def get_acme_history():
    """Get history of certificates issued via ACME (local and external CAs).

    Query params:
        page: Page number (default: 1)
        per_page: Items per page (default: 50, max: 100)
        source: Filter by source ('acme', 'acme_client', 'letsencrypt', or 'all')
    """
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 100)
    source_filter = request.args.get('source', 'all')

    # ``letsencrypt`` is retained for legacy rows. New certificates from any
    # external ACME CA (Actalis, Let's Encrypt, ZeroSSL, ...) use acme_client.
    external_sources = ['acme_client', 'letsencrypt']
    valid_sources = ['all', 'acme', *external_sources]
    if source_filter not in valid_sources:
        source_filter = 'all'

    if source_filter == 'all':
        query = Certificate.query.filter(
            Certificate.source.in_(['acme', *external_sources])
        )
    else:
        query = Certificate.query.filter_by(source=source_filter)

    query = query.order_by(Certificate.created_at.desc())
    total = query.count()
    certs = query.offset((page - 1) * per_page).limit(per_page).all()

    # Batch fetch CAs and orders to avoid N+1
    cert_ids = [c.id for c in certs]
    ca_refs = [c.caref for c in certs if c.caref]

    # Fetch all CAs at once
    cas_map = {}
    if ca_refs:
        cas = CA.query.filter(CA.refid.in_(ca_refs)).all()
        cas_map = {ca.refid: ca.common_name for ca in cas}

    # Fetch local ACME orders
    orders_map = {}
    if cert_ids:
        orders = AcmeOrder.query.filter(AcmeOrder.certificate_id.in_(cert_ids)).all()
        for order in orders:
            account = order.account
            
            # Determine the actual challenge type from validated challenges
            challenge_type = 'N/A'
            for authz in order.authorizations:
                for challenge in authz.challenges:
                    if challenge.validated is not None:
                        challenge_type = challenge.type
                        break
                if challenge_type != 'N/A':
                    break
            
            orders_map[order.certificate_id] = {
                'order_id': order.order_id,
                'account': account.account_id if account else 'Unknown',
                'status': order.status,
                'challenge_type': challenge_type,
                'environment': 'local'
            }

    # Fetch LE client orders
    client_orders_map = {}
    if cert_ids:
        client_orders = AcmeClientOrder.query.filter(AcmeClientOrder.certificate_id.in_(cert_ids)).all()
        external_account_ids = {
            order.acme_client_account_id
            for order in client_orders
            if order.acme_client_account_id
        }
        external_accounts = (
            AcmeClientAccount.query.filter(AcmeClientAccount.id.in_(external_account_ids)).all()
            if external_account_ids else []
        )
        external_account_labels = {
            account.id: account.label for account in external_accounts
        }
        dns_provider_ids = {
            order.dns_provider_id for order in client_orders if order.dns_provider_id
        }
        dns_provider_names = {
            provider.id: provider.name
            for provider in (
                DnsProvider.query.filter(DnsProvider.id.in_(dns_provider_ids)).all()
                if dns_provider_ids else []
            )
        }
        for order in client_orders:
            client_orders_map[order.certificate_id] = {
                'order_id': order.id,
                'status': order.status,
                'challenge_type': order.challenge_type,
                'environment': order.environment,
                'dns_provider': dns_provider_names.get(order.dns_provider_id),
                'ca_account_label': external_account_labels.get(
                    order.acme_client_account_id
                ),
            }

    data = []
    for cert in certs:
        # External ACME certificates use their X.509 issuer directly; local
        # ACME certificates resolve the managed UCM CA name.
        if cert.source in external_sources:
            issuer_name = cert.issuer_name if hasattr(cert, 'issuer_name') else cert.issuer
            order_data = client_orders_map.get(cert.id, {})
        else:
            issuer_name = cas_map.get(cert.caref) if cert.caref else None
            order_data = orders_map.get(cert.id, {})

        data.append({
            'id': cert.id,
            'refid': cert.refid,
            'common_name': cert.subject_cn or cert.descr,
            'serial': cert.serial_number,
            'issuer': issuer_name,
            'source': cert.source,
            'status': order_data.get('status', 'valid'),  # Default to 'valid' if cert exists
            'challenge_type': order_data.get('challenge_type'),
            'environment': order_data.get('environment'),
            'dns_provider': order_data.get('dns_provider'),
            'ca_account_label': order_data.get('ca_account_label'),
            'valid_from': utc_isoformat(cert.valid_from),
            'valid_to': utc_isoformat(cert.valid_to),
            'revoked': cert.revoked,
            'created_at': utc_isoformat(cert.created_at),
            'order': order_data
        })

    return success_response(
        data=data,
        meta={'total': total, 'page': page, 'per_page': per_page}
    )
