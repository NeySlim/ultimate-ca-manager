"""
ACME Local Domains API Routes
Manages domain-to-CA mappings for the Local ACME server.
"""
import re
from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db, AcmeLocalDomain, CA
from services.audit_service import AuditService

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
    domain = AcmeLocalDomain.query.get_or_404(domain_id)
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
    
    ca = CA.query.get(issuing_ca_id)
    if not ca:
        return error_response('Issuing CA not found', 404)
    if not ca.prv:
        return error_response('Selected CA has no private key', 400)
    
    existing = AcmeLocalDomain.query.filter_by(domain=domain_name).first()
    if existing:
        return error_response(f'Domain {domain_name} is already registered', 409)
    
    domain = AcmeLocalDomain(
        domain=domain_name,
        issuing_ca_id=issuing_ca_id,
        auto_approve=data.get('auto_approve', True),
        created_by=g.user.username if hasattr(g, 'user') and g.user else None
    )
    
    db.session.add(domain)
    db.session.commit()
    
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
    domain = AcmeLocalDomain.query.get_or_404(domain_id)
    data = request.json
    
    if not data:
        return error_response('Request body required', 400)
    
    if 'issuing_ca_id' in data:
        ca = CA.query.get(data['issuing_ca_id'])
        if not ca:
            return error_response('Issuing CA not found', 404)
        if not ca.prv:
            return error_response('Selected CA has no private key', 400)
        domain.issuing_ca_id = data['issuing_ca_id']
    
    if 'auto_approve' in data:
        domain.auto_approve = bool(data['auto_approve'])
    
    db.session.commit()
    
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
@require_auth(['write:acme'])
def delete_local_domain(domain_id):
    """Delete a local domain mapping"""
    domain = AcmeLocalDomain.query.get_or_404(domain_id)
    domain_name = domain.domain
    
    db.session.delete(domain)
    db.session.commit()
    
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
    
    Uses hierarchical matching: exact → parent → grandparent.
    Returns issuing_ca_id or None.
    """
    domain = domain.strip().lower()
    if domain.startswith('*.'):
        domain = domain[2:]
    
    # Exact match
    local = AcmeLocalDomain.query.filter_by(domain=domain).first()
    if local:
        return local.issuing_ca_id
    
    # Parent domains
    parts = domain.split('.')
    for i in range(1, len(parts)):
        parent = '.'.join(parts[i:])
        local = AcmeLocalDomain.query.filter_by(domain=parent).first()
        if local:
            return local.issuing_ca_id
    
    return None


def _is_valid_domain(domain: str) -> bool:
    """Validate domain format"""
    pattern = r'^(\*\.)?([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
    return bool(re.match(pattern, domain))
