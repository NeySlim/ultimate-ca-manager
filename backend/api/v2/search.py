"""
Global Search API - Search across all entities
"""
from flask import Blueprint, request, g
from sqlalchemy import or_
from auth.unified import require_auth, has_permission
from models import Certificate, CA, User, CertificateTemplate, AcmeAccount
from models.scep import ScepProfile
from utils.response import success_response
from utils.pagination import parse_request_limit
from utils.datetime_utils import utc_now
from utils.serial_format import serial_search_forms

bp = Blueprint('search', __name__)


@bp.route('/api/v2/search', methods=['GET'])
@require_auth()
def global_search():
    """
    Search across certificates, CAs, users, templates, ACME accounts and SCEP profiles.
    
    Query params:
        q: search query (required, min 2 chars)
        limit: max results per category (default: 5)
    
    Returns:
        {
            "certificates": [...],
            "cas": [...],
            "users": [...],
            "templates": [...],
            "acme_accounts": [...],   # read:acme only
            "scep_profiles": [...]    # read:scep only
        }
    """
    query = request.args.get('q', '').strip()
    limit = parse_request_limit(5, 20)   # max 20 per category
    
    if len(query) < 2:
        return success_response(data={
            'certificates': [],
            'cas': [],
            'users': [],
            'templates': [],
            'acme_accounts': [],
            'scep_profiles': [],
        })
    
    # Escape LIKE wildcards in user input
    safe_query = query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    search_pattern = f'%{safe_query}%'
    results = {}
    
    # Each category to the readers of its own list only, as /api/v2/certificates, /cas
    # and /templates answer them
    cert_terms = [
        Certificate.subject.ilike(search_pattern, escape='\\'),
        Certificate.issuer.ilike(search_pattern, escape='\\'),
        Certificate.descr.ilike(search_pattern, escape='\\'),
        Certificate.serial_number.ilike(search_pattern, escape='\\'),
        Certificate.serial_number.in_(serial_search_forms(query)),
        Certificate.comment.ilike(search_pattern, escape='\\'),
    ]
    certs = (Certificate.query.filter(or_(*cert_terms)).limit(limit).all()
             if has_permission('read:certificates', g.permissions) else [])
    
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
    ).limit(limit).all() if has_permission('read:cas', g.permissions) else []
    
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
    ).limit(limit).all() if has_permission('read:templates', g.permissions) else []
    
    results['templates'] = [{
        'id': t.id,
        'name': t.name,
        'description': t.description,
        'type': 'template'
    } for t in templates]

    # The protocol objects the palette offers, each to the readers of its module only
    results['acme_accounts'] = []
    if has_permission('read:acme', g.permissions):
        accounts = AcmeAccount.query.filter(
            or_(
                AcmeAccount.contact.ilike(search_pattern, escape='\\'),
                AcmeAccount.account_id.ilike(search_pattern, escape='\\'),
            )
        ).order_by(AcmeAccount.created_at.desc()).limit(limit).all()
        results['acme_accounts'] = [{
            'id': a.id,
            'name': _acme_account_name(a),
            'account_id': a.account_id,
            'status': a.status,
            'type': 'acme_account',
        } for a in accounts]

    results['scep_profiles'] = []
    if has_permission('read:scep', g.permissions):
        profiles = ScepProfile.query.filter(
            or_(
                ScepProfile.name.ilike(search_pattern, escape='\\'),
                ScepProfile.url_slug.ilike(search_pattern, escape='\\'),
                ScepProfile.description.ilike(search_pattern, escape='\\'),
            )
        ).order_by(ScepProfile.name).limit(limit).all()
        results['scep_profiles'] = [{
            'id': p.id,
            'name': p.name,
            'url_slug': p.url_slug,
            'enabled': p.enabled,
            'type': 'scep_profile',
        } for p in profiles]

    return success_response(data=results)


def _acme_account_name(account):
    """The first contact without its scheme, else the account's own id."""
    for uri in account.contact_list:
        if isinstance(uri, str) and uri:
            return uri.split(':', 1)[1] if uri.lower().startswith('mailto:') else uri
    return account.account_id


def _extract_cn(subject):
    """The first CN of a stored subject string, escapes honoured."""
    from utils.dn_parse import stored_dn_common_name
    return stored_dn_common_name(subject)
