"""
Global Search API - Search across all entities
"""
from flask import Blueprint, request, jsonify
from sqlalchemy import or_
from auth.unified import require_auth
from models import Certificate, CA, User, CertificateTemplate

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
    limit = min(int(request.args.get('limit', 5)), 20)  # Max 20 per category
    
    if len(query) < 2:
        return jsonify({
            'certificates': [],
            'cas': [],
            'users': [],
            'templates': []
        })
    
    search_pattern = f'%{query}%'
    results = {}
    
    # Search certificates
    certs = Certificate.query.filter(
        or_(
            Certificate.subject.ilike(search_pattern),
            Certificate.issuer.ilike(search_pattern),
            Certificate.descr.ilike(search_pattern),
            Certificate.serial_number.ilike(search_pattern)
        )
    ).limit(limit).all()
    
    from datetime import datetime
    
    def get_cert_status(cert):
        if cert.revoked:
            return 'revoked'
        if cert.valid_to and cert.valid_to < datetime.utcnow():
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
            CA.descr.ilike(search_pattern),
            CA.subject.ilike(search_pattern),
            CA.issuer.ilike(search_pattern)
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
    
    # Search users
    users = User.query.filter(
        or_(
            User.username.ilike(search_pattern),
            User.email.ilike(search_pattern),
            User.full_name.ilike(search_pattern)
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
    
    # Search templates
    templates = CertificateTemplate.query.filter(
        or_(
            CertificateTemplate.name.ilike(search_pattern),
            CertificateTemplate.description.ilike(search_pattern)
        )
    ).limit(limit).all()
    
    results['templates'] = [{
        'id': t.id,
        'name': t.name,
        'description': t.description,
        'type': 'template'
    } for t in templates]
    
    return jsonify(results)


def _extract_cn(subject):
    """Extract CN from subject string"""
    if not subject:
        return None
    for part in subject.split(','):
        part = part.strip()
        if part.upper().startswith('CN='):
            return part[3:]
    return None
