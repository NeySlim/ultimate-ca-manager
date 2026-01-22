"""
Certificate Templates Management Routes v2.0
/api/v2/templates/* - Manage certificate templates
"""

from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response, error_response, created_response, no_content_response
from models import db
from models.certificate_template import CertificateTemplate
from datetime import datetime
import json

bp = Blueprint('templates_v2', __name__)


@bp.route('/api/v2/templates', methods=['GET'])
@require_auth()
def list_templates():
    """
    List all certificate templates
    
    Query params:
    - type: Filter by template_type
    - active: Filter by is_active (true/false)
    - search: Search name, description
    """
    template_type = request.args.get('type')
    active_str = request.args.get('active')
    search = request.args.get('search', '').strip()
    
    query = CertificateTemplate.query
    
    if template_type:
        query = query.filter_by(template_type=template_type)
    
    if active_str:
        active = active_str.lower() == 'true'
        query = query.filter_by(is_active=active)
    
    if search:
        search_pattern = f'%{search}%'
        query = query.filter(
            db.or_(
                CertificateTemplate.name.ilike(search_pattern),
                CertificateTemplate.description.ilike(search_pattern)
            )
        )
    
    templates = query.order_by(CertificateTemplate.created_at.desc()).all()
    
    return success_response(
        data=[template.to_dict() for template in templates]
    )


@bp.route('/api/v2/templates', methods=['POST'])
@require_auth()
def create_template():
    """
    Create new certificate template
    
    POST /api/v2/templates
    {
        "name": "Web Server SSL",
        "description": "Standard web server certificate",
        "template_type": "web_server",
        "key_type": "RSA-2048",
        "validity_days": 397,
        "digest": "sha256",
        "dn_template": {
            "CN": "{hostname}",
            "O": "My Company",
            "OU": "IT Department"
        },
        "extensions_template": {
            "key_usage": ["digitalSignature", "keyEncipherment"],
            "extended_key_usage": ["serverAuth"],
            "basic_constraints": {"ca": false},
            "san_types": ["dns", "ip"]
        }
    }
    """
    data = request.get_json()
    
    # Required fields
    if not data.get('name'):
        return error_response('Template name is required', 400)
    if not data.get('template_type'):
        return error_response('Template type is required', 400)
    
    # Check if template name exists
    if CertificateTemplate.query.filter_by(name=data['name']).first():
        return error_response('Template name already exists', 409)
    
    # Validate template type
    valid_types = ['web_server', 'email', 'vpn_server', 'vpn_client', 'code_signing', 'client_auth', 'piv', 'custom']
    if data['template_type'] not in valid_types:
        return error_response(f'Invalid template type. Must be one of: {", ".join(valid_types)}', 400)
    
    # Prepare extensions template
    extensions = data.get('extensions_template', {})
    if not extensions:
        # Default based on type
        if data['template_type'] == 'web_server':
            extensions = {
                "key_usage": ["digitalSignature", "keyEncipherment"],
                "extended_key_usage": ["serverAuth"],
                "basic_constraints": {"ca": False}
            }
        elif data['template_type'] == 'email':
            extensions = {
                "key_usage": ["digitalSignature", "keyEncipherment"],
                "extended_key_usage": ["emailProtection"],
                "basic_constraints": {"ca": False}
            }
        elif data['template_type'] == 'code_signing':
            extensions = {
                "key_usage": ["digitalSignature"],
                "extended_key_usage": ["codeSigning"],
                "basic_constraints": {"ca": False}
            }
    
    # Create template
    template = CertificateTemplate(
        name=data['name'],
        description=data.get('description', ''),
        template_type=data['template_type'],
        key_type=data.get('key_type', 'RSA-2048'),
        validity_days=data.get('validity_days', 397),
        digest=data.get('digest', 'sha256'),
        dn_template=json.dumps(data.get('dn_template', {})),
        extensions_template=json.dumps(extensions),
        is_system=False,  # User-created templates are never system
        is_active=True,
        created_by=g.current_user.username
    )
    
    try:
        db.session.add(template)
        db.session.commit()
        
        return created_response(
            data=template.to_dict(),
            message=f'Template {template.name} created successfully'
        )
    except Exception as e:
        db.session.rollback()
        return error_response(f'Failed to create template: {str(e)}', 500)


@bp.route('/api/v2/templates/<int:template_id>', methods=['GET'])
@require_auth()
def get_template(template_id):
    """Get single template details"""
    template = CertificateTemplate.query.get(template_id)
    if not template:
        return error_response('Template not found', 404)
    
    return success_response(data=template.to_dict())


@bp.route('/api/v2/templates/<int:template_id>', methods=['PUT'])
@require_auth()
def update_template(template_id):
    """
    Update existing template
    
    PUT /api/v2/templates/{template_id}
    {
        "description": "Updated description",
        "validity_days": 365,
        "is_active": false
    }
    """
    template = CertificateTemplate.query.get(template_id)
    if not template:
        return error_response('Template not found', 404)
    
    # Prevent updating system templates
    if template.is_system:
        return error_response('Cannot modify system templates', 403)
    
    data = request.get_json()
    
    # Update fields
    if 'name' in data:
        # Check if name already used by another template
        existing = CertificateTemplate.query.filter(
            CertificateTemplate.name == data['name'],
            CertificateTemplate.id != template_id
        ).first()
        if existing:
            return error_response('Template name already in use', 409)
        template.name = data['name']
    
    if 'description' in data:
        template.description = data['description']
    
    if 'template_type' in data:
        valid_types = ['web_server', 'email', 'vpn_server', 'vpn_client', 'code_signing', 'client_auth', 'piv', 'custom']
        if data['template_type'] not in valid_types:
            return error_response(f'Invalid template type', 400)
        template.template_type = data['template_type']
    
    if 'key_type' in data:
        template.key_type = data['key_type']
    
    if 'validity_days' in data:
        template.validity_days = int(data['validity_days'])
    
    if 'digest' in data:
        template.digest = data['digest']
    
    if 'dn_template' in data:
        template.dn_template = json.dumps(data['dn_template'])
    
    if 'extensions_template' in data:
        template.extensions_template = json.dumps(data['extensions_template'])
    
    if 'is_active' in data:
        template.is_active = bool(data['is_active'])
    
    template.updated_by = g.current_user.username
    template.updated_at = datetime.utcnow()
    
    try:
        db.session.commit()
        return success_response(
            data=template.to_dict(),
            message=f'Template {template.name} updated successfully'
        )
    except Exception as e:
        db.session.rollback()
        return error_response(f'Failed to update template: {str(e)}', 500)


@bp.route('/api/v2/templates/<int:template_id>', methods=['DELETE'])
@require_auth()
def delete_template(template_id):
    """
    Delete certificate template
    
    DELETE /api/v2/templates/{template_id}
    """
    template = CertificateTemplate.query.get(template_id)
    if not template:
        return error_response('Template not found', 404)
    
    # Prevent deleting system templates
    if template.is_system:
        return error_response('Cannot delete system templates', 403)
    
    template_name = template.name
    
    try:
        db.session.delete(template)
        db.session.commit()
        
        return no_content_response(
            message=f'Template {template_name} deleted successfully'
        )
    except Exception as e:
        db.session.rollback()
        return error_response(f'Failed to delete template: {str(e)}', 500)
