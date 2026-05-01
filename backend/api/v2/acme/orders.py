"""ACME orders, challenges, and history routes"""
import json

from flask import request
from models import db, AcmeAccount, AcmeOrder, AcmeAuthorization, AcmeChallenge, CA, Certificate
from models.acme_models import AcmeClientOrder, DnsProvider
from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.datetime_utils import utc_isoformat

from . import bp, logger


@bp.route('/api/v2/acme/orders', methods=['GET'])
@require_auth(['read:acme'])
def list_acme_orders():
    """List ACME orders"""
    status = request.args.get('status')
    query = AcmeOrder.query
    if status:
        query = query.filter_by(status=status)

    orders = query.order_by(AcmeOrder.created_at.desc()).limit(50).all()

    data = []
    for order in orders:
        # Extract identifiers for display
        identifiers_str = ", ".join([i.get('value', '') for i in order.identifiers_list])

        # Get account info
        account = order.account
        account_name = account.account_id if account else "Unknown"

        # Get challenge type (from first authz)
        method = "N/A"
        if order.authorizations.count() > 0:
            first_authz = order.authorizations.first()
            if first_authz.challenges.count() > 0:
                method = first_authz.challenges.first().type.upper()

        data.append({
            'id': order.id,
            'order_id': order.order_id,
            'domain': identifiers_str,
            'account': account_name,
            'status': order.status.capitalize(),
            'expires': order.expires.strftime('%Y-%m-%d'),
            'method': method,
            'created_at': utc_isoformat(order.created_at)
        })

    return success_response(data=data)


@bp.route('/api/v2/acme/accounts/<int:account_id>/orders', methods=['GET'])
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
    account = AcmeAccount.query.get_or_404(account_id)

    orders = AcmeOrder.query.filter_by(account_id=account.account_id).order_by(
        AcmeOrder.created_at.desc()
    ).limit(50).all()

    data = []
    for order in orders:
        identifiers_str = ", ".join([i.get('value', '') for i in order.identifiers_list])

        method = "N/A"
        if order.authorizations.count() > 0:
            first_authz = order.authorizations.first()
            if first_authz.challenges.count() > 0:
                method = first_authz.challenges.first().type.upper()

        data.append({
            'id': order.id,
            'order_id': order.order_id,
            'domain': identifiers_str,
            'status': order.status.capitalize(),
            'expires': order.expires.strftime('%Y-%m-%d') if order.expires else None,
            'method': method,
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


@bp.route('/api/v2/acme/accounts/<int:account_id>/challenges', methods=['GET'])
@require_auth(['read:acme'])
def list_account_challenges(account_id):
    """List challenges for a specific ACME account"""
    account = AcmeAccount.query.get_or_404(account_id)

    # Get all orders for this account
    orders = AcmeOrder.query.filter_by(account_id=account.account_id).all()

    data = []
    for order in orders:
        for authz in order.authorizations:
            # identifier is JSON: {"type": "dns", "value": "example.com"}
            try:
                ident = json.loads(authz.identifier) if isinstance(authz.identifier, str) else authz.identifier
                domain = ident.get('value', '') if isinstance(ident, dict) else str(authz.identifier)
            except Exception:
                domain = str(authz.identifier)
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
    """Get history of certificates issued via ACME (local and Let's Encrypt)

    Query params:
        page: Page number (default: 1)
        per_page: Items per page (default: 50, max: 100)
        source: Filter by source ('acme', 'letsencrypt', or 'all' - default: 'all')
    """
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 100)
    source_filter = request.args.get('source', 'all')

    # Whitelist source filter values
    valid_sources = ['all', 'acme', 'letsencrypt']
    if source_filter not in valid_sources:
        source_filter = 'all'

    # Get certificates with source='acme' or 'letsencrypt'
    if source_filter == 'all':
        query = Certificate.query.filter(
            Certificate.source.in_(['acme', 'letsencrypt'])
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
            orders_map[order.certificate_id] = {
                'order_id': order.order_id,
                'account': account.account_id if account else 'Unknown',
                'status': order.status,
                'challenge_type': 'http-01',  # Local ACME typically uses http-01
                'environment': 'local'
            }

    # Fetch LE client orders
    client_orders_map = {}
    if cert_ids:
        client_orders = AcmeClientOrder.query.filter(AcmeClientOrder.certificate_id.in_(cert_ids)).all()
        for order in client_orders:
            dns_provider = None
            if order.dns_provider_id:
                provider = DnsProvider.query.get(order.dns_provider_id)
                dns_provider = provider.name if provider else None

            client_orders_map[order.certificate_id] = {
                'order_id': order.id,
                'status': order.status,
                'challenge_type': order.challenge_type,
                'environment': order.environment,
                'dns_provider': dns_provider
            }

    data = []
    for cert in certs:
        # For LE certs, use the issuer field directly; for local ACME, use CA name
        if cert.source == 'letsencrypt':
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
