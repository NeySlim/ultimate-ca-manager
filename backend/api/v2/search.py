"""
Global Search API - Search across all entities
"""
from flask import Blueprint, request, g
from sqlalchemy import or_
from auth.unified import require_auth, has_permission
from models import Certificate, CA, User, CertificateTemplate
from utils.response import success_response
from utils.pagination import parse_request_limit
from utils.datetime_utils import utc_now
from utils.serial_format import serial_search_forms

bp = Blueprint('search', __name__)


@bp.route('/api/v2/search', methods=['GET'])
@require_auth()
def global_search():
    """
    Search across certificates, CAs, users, and templates.
    
    Query params:
        q: search query (required, min 2 chars)
        limit: max results per category (default: 5)
    
    Returns:
        {
            "certificates": [...],
            "cas": [...],
            "users": [...],
            "templates": [...]
        }
    """
    query = request.args.get('q', '').strip()
    limit = parse_request_limit(5, 20)   # max 20 per category
    
    if len(query) < 2:
        return success_response(data={
            'certificates': [],
            'cas': [],
            'users': [],
            'templates': []
        })
    
    # Escape LIKE wildcards in user input
    safe_query = query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    search_pattern = f'%{safe_query}%'
    results = {}
    
    # Search certificates
    certs = Certificate.query.filter(
        or_(
            Certificate.subject.ilike(search_pattern, escape='\\'),
            Certificate.issuer.ilike(search_pattern, escape='\\'),
            Certificate.descr.ilike(search_pattern, escape='\\'),
            Certificate.serial_number.ilike(search_pattern, escape='\\'),
            Certificate.serial_number.in_(serial_search_forms(query)),
        )
    ).limit(limit).all()
    
    from datetime import datetime
    
    def get_cert_status(cert):
        if cert.revoked:
            return 'revoked'
        if cert.valid_to and cert.valid_to < utc_now():
            return 'expired'
        return 'valid'
    
    results['certificates'] = [{
        'id': c.id,
        'refid': c.refid,
        'name': _extract_cn(c.subject) or c.descr or 'Unnamed',
        'subject': c.subject,
        'type': 'certificate',
        'status': get_cert_status(c)
    } for c in certs]
    
    # Search CAs
    cas = CA.query.filter(
        or_(
            CA.descr.ilike(search_pattern, escape='\\'),
            CA.subject.ilike(search_pattern, escape='\\'),
            CA.issuer.ilike(search_pattern, escape='\\')
        )
    ).limit(limit).all()
    
    results['cas'] = [{
        'id': ca.id,
        'refid': ca.refid,
        'name': ca.descr or _extract_cn(ca.subject) or 'Unnamed CA',
        'subject': ca.subject,
        'type': 'ca',
        'is_root': ca.caref is None
    } for ca in cas]
    
    # Search users — same scope as /api/v2/users (read:users)
    if has_permission('read:users', g.permissions):
        users = User.query.filter(
            or_(
                User.username.ilike(search_pattern, escape='\\'),
                User.email.ilike(search_pattern, escape='\\'),
                User.full_name.ilike(search_pattern, escape='\\')
            )
        ).limit(limit).all()

        results['users'] = [{
            'id': u.id,
            'name': u.full_name or u.username,
            'username': u.username,
            'email': u.email,
            'type': 'user',
            'role': u.role
        } for u in users]
    else:
        results['users'] = []
    
    # Search templates
    templates = CertificateTemplate.query.filter(
        or_(
            CertificateTemplate.name.ilike(search_pattern, escape='\\'),
            CertificateTemplate.description.ilike(search_pattern, escape='\\')
        )
    ).limit(limit).all()
    
    results['templates'] = [{
        'id': t.id,
        'name': t.name,
        'description': t.description,
        'type': 'template'
    } for t in templates]
    
    return success_response(data=results)


def _extract_cn(subject):
    """The first CN of a stored subject string, escapes honoured."""
    from utils.dn_parse import stored_dn_common_name
    return stored_dn_common_name(subject)
