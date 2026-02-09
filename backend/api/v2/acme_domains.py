"""
ACME Domains API Routes
Manages domain-to-DNS-provider mappings for ACME Proxy functionality.
"""
import json
from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db, AcmeDomain, DnsProvider

bp = Blueprint('acme_domains', __name__)


# =============================================================================
# Domain CRUD
# =============================================================================

@bp.route('/api/v2/acme/domains', methods=['GET'])
@require_auth(['read:acme'])
def list_domains():
    """List all registered ACME domains"""
    domains = AcmeDomain.query.order_by(AcmeDomain.domain).all()
    return success_response(data=[d.to_dict() for d in domains])


@bp.route('/api/v2/acme/domains/<int:domain_id>', methods=['GET'])
@require_auth(['read:acme'])
def get_domain(domain_id):
    """Get a specific domain"""
    domain = AcmeDomain.query.get_or_404(domain_id)
    return success_response(data=domain.to_dict())


@bp.route('/api/v2/acme/domains', methods=['POST'])
@require_auth(['write:acme'])
def create_domain():
    """Register a new domain for ACME Proxy"""
    data = request.json
    if not data:
        return error_response('Request body required', 400)
    
    # Validate required fields
    domain_name = data.get('domain', '').strip().lower()
    if not domain_name:
        return error_response('Domain is required', 400)
    
    dns_provider_id = data.get('dns_provider_id')
    if not dns_provider_id:
        return error_response('DNS provider is required', 400)
    
    # Check provider exists
    provider = DnsProvider.query.get(dns_provider_id)
    if not provider:
        return error_response('DNS provider not found', 404)
    
    # Check domain doesn't already exist
    existing = AcmeDomain.query.filter_by(domain=domain_name).first()
    if existing:
        return error_response(f'Domain {domain_name} is already registered', 409)
    
    # Validate domain format
    if not _is_valid_domain(domain_name):
        return error_response('Invalid domain format', 400)
    
    # Create domain
    domain = AcmeDomain(
        domain=domain_name,
        dns_provider_id=dns_provider_id,
        is_wildcard_allowed=data.get('is_wildcard_allowed', True),
        auto_approve=data.get('auto_approve', True),
        created_by=g.user.username if hasattr(g, 'user') and g.user else None
    )
    
    db.session.add(domain)
    db.session.commit()
    
    return success_response(
        data=domain.to_dict(),
        message=f'Domain {domain_name} registered successfully',
        status_code=201
    )


@bp.route('/api/v2/acme/domains/<int:domain_id>', methods=['PUT'])
@require_auth(['write:acme'])
def update_domain(domain_id):
    """Update a domain configuration"""
    domain = AcmeDomain.query.get_or_404(domain_id)
    data = request.json
    
    if not data:
        return error_response('Request body required', 400)
    
    # Update DNS provider if specified
    if 'dns_provider_id' in data:
        provider = DnsProvider.query.get(data['dns_provider_id'])
        if not provider:
            return error_response('DNS provider not found', 404)
        domain.dns_provider_id = data['dns_provider_id']
    
    # Update other fields
    if 'is_wildcard_allowed' in data:
        domain.is_wildcard_allowed = bool(data['is_wildcard_allowed'])
    
    if 'auto_approve' in data:
        domain.auto_approve = bool(data['auto_approve'])
    
    db.session.commit()
    
    return success_response(
        data=domain.to_dict(),
        message='Domain updated successfully'
    )


@bp.route('/api/v2/acme/domains/<int:domain_id>', methods=['DELETE'])
@require_auth(['write:acme'])
def delete_domain(domain_id):
    """Delete a domain registration"""
    domain = AcmeDomain.query.get_or_404(domain_id)
    domain_name = domain.domain
    
    db.session.delete(domain)
    db.session.commit()
    
    return success_response(message=f'Domain {domain_name} removed')


# =============================================================================
# Domain Resolution
# =============================================================================

@bp.route('/api/v2/acme/domains/resolve', methods=['GET'])
@require_auth(['read:acme'])
def resolve_domain():
    """
    Resolve which DNS provider handles a given domain.
    Used to test domain resolution before requesting certificates.
    
    Query params:
        domain: The domain to resolve (e.g., "api.example.com")
    """
    domain = request.args.get('domain', '').strip().lower()
    if not domain:
        return error_response('Domain query parameter is required', 400)
    
    result = find_provider_for_domain(domain)
    
    if result:
        return success_response(data={
            'domain': domain,
            'matched_domain': result['matched_domain'],
            'dns_provider_id': result['provider'].id,
            'dns_provider_name': result['provider'].name,
            'dns_provider_type': result['provider'].provider_type,
            'is_wildcard_allowed': result['is_wildcard_allowed'],
            'auto_approve': result['auto_approve'],
        })
    else:
        return error_response(
            f'No DNS provider configured for domain: {domain}. '
            'Register this domain or a parent domain first.',
            404
        )


@bp.route('/api/v2/acme/domains/test', methods=['POST'])
@require_auth(['write:acme'])
def test_domain_access():
    """
    Test DNS access for a domain by creating and deleting a test TXT record.
    
    Body:
        domain: The domain to test
        dns_provider_id: (optional) Provider to use, or resolve automatically
    """
    data = request.json
    if not data:
        return error_response('Request body required', 400)
    
    domain = data.get('domain', '').strip().lower()
    if not domain:
        return error_response('Domain is required', 400)
    
    # Get or resolve provider
    provider_id = data.get('dns_provider_id')
    if provider_id:
        provider = DnsProvider.query.get(provider_id)
        if not provider:
            return error_response('DNS provider not found', 404)
    else:
        result = find_provider_for_domain(domain)
        if not result:
            return error_response(f'No DNS provider configured for {domain}', 404)
        provider = result['provider']
    
    # Test by creating/deleting a TXT record
    try:
        from services.acme.dns_providers import get_dns_provider_instance
        
        dns_client = get_dns_provider_instance(provider)
        test_record = f"_acme-test.{domain.lstrip('*.')}"
        test_value = "ucm-dns-test-record"
        
        # Create test record
        dns_client.create_txt_record(test_record, test_value)
        
        # Wait a moment
        import time
        time.sleep(2)
        
        # Delete test record
        dns_client.delete_txt_record(test_record, test_value)
        
        return success_response(
            data={
                'domain': domain,
                'provider': provider.name,
                'test_record': test_record,
                'success': True
            },
            message=f'DNS access test successful for {domain} via {provider.name}'
        )
        
    except Exception as e:
        return error_response(
            f'DNS access test failed: {str(e)}',
            400
        )


# =============================================================================
# Helper Functions
# =============================================================================

def find_provider_for_domain(domain: str) -> dict | None:
    """
    Find the DNS provider for a given domain using hierarchical matching.
    
    Resolution order:
    1. Exact match: "api.example.com"
    2. Parent domain: "example.com" (covers *.example.com)
    3. Grandparent: "com" (unlikely but possible)
    
    Args:
        domain: The domain to resolve (e.g., "api.dev.example.com")
    
    Returns:
        dict with 'provider', 'matched_domain', 'is_wildcard_allowed', 'auto_approve'
        or None if not found
    """
    domain = domain.strip().lower()
    
    # Remove wildcard prefix if present
    if domain.startswith('*.'):
        domain = domain[2:]
    
    # Try exact match first
    acme_domain = AcmeDomain.query.filter_by(domain=domain).first()
    if acme_domain:
        return {
            'provider': acme_domain.dns_provider,
            'matched_domain': acme_domain.domain,
            'is_wildcard_allowed': acme_domain.is_wildcard_allowed,
            'auto_approve': acme_domain.auto_approve,
        }
    
    # Try parent domains
    parts = domain.split('.')
    for i in range(1, len(parts)):
        parent = '.'.join(parts[i:])
        acme_domain = AcmeDomain.query.filter_by(domain=parent).first()
        if acme_domain:
            return {
                'provider': acme_domain.dns_provider,
                'matched_domain': acme_domain.domain,
                'is_wildcard_allowed': acme_domain.is_wildcard_allowed,
                'auto_approve': acme_domain.auto_approve,
            }
    
    # No match found
    return None


def _is_valid_domain(domain: str) -> bool:
    """Validate domain format"""
    import re
    # Basic domain validation - allows subdomains and wildcards
    pattern = r'^(\*\.)?([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
    return bool(re.match(pattern, domain))
