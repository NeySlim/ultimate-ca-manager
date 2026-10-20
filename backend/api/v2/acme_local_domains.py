"""
ACME Local Domains API Routes
Manages domain-to-CA mappings for the Local ACME server.
"""
import logging
from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit
from models import db, AcmeLocalDomain, CA
from services.acme import domain_match
from utils.signing_ca import signing_ca_problem
from services.audit_service import AuditService

logger = logging.getLogger(__name__)

bp = Blueprint('acme_local_domains', __name__)


@bp.route('/api/v2/acme/local-domains', methods=['GET'])
@require_auth(['read:acme'])
def list_local_domains():
    """List all local ACME domain mappings"""
    domains = AcmeLocalDomain.query.order_by(AcmeLocalDomain.domain).all()
    return success_response(data=[d.to_dict() for d in domains])


@bp.route('/api/v2/acme/local-domains/<int:domain_id>', methods=['GET'])
@require_auth(['read:acme'])
def get_local_domain(domain_id):
    """Get a specific local domain"""
    domain = db.get_or_404(AcmeLocalDomain, domain_id)
    return success_response(data=domain.to_dict())


@bp.route('/api/v2/acme/local-domains', methods=['POST'])
@require_auth(['write:acme'])
def create_local_domain():
    """Create a new local domain mapping"""
    data = request.json
    if not data:
        return error_response('Request body required', 400)
    
    domain_name = data.get('domain', '').strip().lower()
    if not domain_name:
        return error_response('Domain is required', 400)
    
    if not _is_valid_domain(domain_name):
        return error_response('Invalid domain format', 400)
    
    issuing_ca_id = data.get('issuing_ca_id')
    if not issuing_ca_id:
        return error_response('Issuing CA is required', 400)
    
    ca = db.session.get(CA, issuing_ca_id)
    if not ca:
        return error_response('Issuing CA not found', 404)
    # The same six reasons the DNS-mapped table refuses, asked the same way:
    # two of them were checked here and a zone could be bound to an authority
    # that is revoked, that sits under a revoked one, or that has been taken
    # offline. Nothing is signed by such an authority, but issuance refuses
    # the order without failing it, so the client retries for ever and the
    # operator is never told what is wrong.
    problem = signing_ca_problem(ca)
    if problem:
        return error_response(f'Selected CA cannot sign: {problem}', 400)
    
    # `custom` and `*.custom` name the same zone, so they cannot be two
    # entries: the second would never be reached and the operator could not
    # tell which one was in force.
    bare = domain_match.normalize(domain_name)
    existing = AcmeLocalDomain.query.filter(
        AcmeLocalDomain.domain.in_([bare, f'*.{bare}'])).first()
    if existing:
        return error_response(
            f'Domain {existing.domain} is already registered', 409)
    
    domain = AcmeLocalDomain(
        domain=domain_name,
        issuing_ca_id=issuing_ca_id,
        auto_approve=data.get('auto_approve', False),
        created_by=g.user.username if hasattr(g, 'user') and g.user else None
    )
    
    db.session.add(domain)
    ok, _err = safe_commit(logger, "Failed to create local ACME domain")
    if not ok:
        return _err
    
    AuditService.log_action(
        action='acme_local_domain_create',
        resource_type='acme_local_domain',
        resource_id=str(domain.id),
        resource_name=domain_name,
        details=f'Registered local ACME domain: {domain_name} -> CA {ca.common_name}',
        success=True
    )
    
    return success_response(
        data=domain.to_dict(),
        message=f'Domain {domain_name} registered successfully',
        status=201
    )


@bp.route('/api/v2/acme/local-domains/<int:domain_id>', methods=['PUT'])
@require_auth(['write:acme'])
def update_local_domain(domain_id):
    """Update a local domain mapping"""
    domain = db.get_or_404(AcmeLocalDomain, domain_id)
    data = request.json
    
    if not data:
        return error_response('Request body required', 400)
    
    if 'issuing_ca_id' in data:
        ca = db.session.get(CA, data['issuing_ca_id'])
        if not ca:
            return error_response('Issuing CA not found', 404)
        # Judged only when the authority actually changes, exactly as the
        # DNS-mapped table does it: an authority taken offline after the zone
        # was bound to it would otherwise freeze the zone, and the operator
        # could no longer correct it nor turn its approval off. Both sides go
        # through `str` because the column is an integer and a client may send
        # the identifier as text, in which case a bare comparison differs and
        # re-judges an authority that did not change.
        problem = signing_ca_problem(ca)
        if problem and str(data['issuing_ca_id']) != str(domain.issuing_ca_id or ''):
            return error_response(f'Selected CA cannot sign: {problem}', 400)
        domain.issuing_ca_id = data['issuing_ca_id']
    
    if 'auto_approve' in data:
        domain.auto_approve = bool(data['auto_approve'])
    
    ok, _err = safe_commit(logger, "Failed to update local ACME domain")
    if not ok:
        return _err
    
    AuditService.log_action(
        action='acme_local_domain_update',
        resource_type='acme_local_domain',
        resource_id=str(domain_id),
        resource_name=domain.domain,
        details=f'Updated local ACME domain: {domain.domain}',
        success=True
    )
    
    return success_response(
        data=domain.to_dict(),
        message='Domain updated successfully'
    )


@bp.route('/api/v2/acme/local-domains/<int:domain_id>', methods=['DELETE'])
@require_auth(['delete:acme'])
def delete_local_domain(domain_id):
    """Delete a local domain mapping"""
    domain = db.get_or_404(AcmeLocalDomain, domain_id)
    domain_name = domain.domain
    
    db.session.delete(domain)
    ok, _err = safe_commit(logger, "Failed to delete local ACME domain")
    if not ok:
        return _err
    
    AuditService.log_action(
        action='acme_local_domain_delete',
        resource_type='acme_local_domain',
        resource_id=str(domain_id),
        resource_name=domain_name,
        details=f'Removed local ACME domain: {domain_name}',
        success=True
    )
    
    return success_response(message=f'Domain {domain_name} removed')


def find_local_domain_ca(domain: str) -> int | None:
    """Find which CA should sign for a local ACME domain.

    Hierarchical matching, most specific first, and either spelling of each
    level: an entry registered as ``*.custom`` used to match nothing at all,
    so its orders went to the default CA (#352).

    Returns issuing_ca_id or None.
    """
    local = domain_match.find(AcmeLocalDomain, domain)
    return local.issuing_ca_id if local else None


def _is_valid_domain(domain: str) -> bool:
    """Whether ``domain`` can be registered as a local ACME domain.

    Same shape rule as the DNS-provider table, plus a bare private TLD such as
    ``lan`` or ``*.lan``, which covers every name under it on this table.
    """
    return domain_match.is_valid_entry(domain, allow_single_label=True)
