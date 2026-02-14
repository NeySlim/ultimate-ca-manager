"""
Certificate Templates Management Routes v2.0
/api/v2/templates/* - Manage certificate templates
"""

from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response, error_response, created_response, no_content_response
from models import db
from models.certificate_template import CertificateTemplate
from services.audit_service import AuditService
from datetime import datetime
import json

bp = Blueprint('templates_v2', __name__)


@bp.route('/api/v2/templates', methods=['GET'])
@require_auth(["read:templates"])
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
@require_auth(["write:templates"])
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
        
        AuditService.log_action(
            action='template_create',
            resource_type='template',
            resource_id=str(template.id),
            resource_name=template.name,
            details=f'Created template: {template.name} ({template.template_type})',
            success=True
        )
        
        return created_response(
            data=template.to_dict(),
            message=f'Template {template.name} created successfully'
        )
    except Exception as e:
        db.session.rollback()
        return error_response(f'Failed to create template: {str(e)}', 500)


@bp.route('/api/v2/templates/<int:template_id>', methods=['GET'])
@require_auth(["read:templates"])
def get_template(template_id):
    """Get single template details"""
    template = CertificateTemplate.query.get(template_id)
    if not template:
        return error_response('Template not found', 404)
    
    return success_response(data=template.to_dict())


@bp.route('/api/v2/templates/<int:template_id>', methods=['PUT'])
@require_auth(["write:templates"])
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
        AuditService.log_action(
            action='template_update',
            resource_type='template',
            resource_id=str(template_id),
            resource_name=template.name,
            details=f'Updated template: {template.name}',
            success=True
        )
        return success_response(
            data=template.to_dict(),
            message=f'Template {template.name} updated successfully'
        )
    except Exception as e:
        db.session.rollback()
        return error_response(f'Failed to update template: {str(e)}', 500)


@bp.route('/api/v2/templates/<int:template_id>', methods=['DELETE'])
@require_auth(["read:templates"])
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
        
        AuditService.log_action(
            action='template_delete',
            resource_type='template',
            resource_id=str(template_id),
            resource_name=template_name,
            details=f'Deleted template: {template_name}',
            success=True
        )
        
        return no_content_response(
            message=f'Template {template_name} deleted successfully'
        )
    except Exception as e:
        db.session.rollback()
        return error_response(f'Failed to delete template: {str(e)}', 500)


# ============================================================
# Bulk Operations
# ============================================================

@bp.route('/api/v2/templates/bulk/delete', methods=['POST'])
@require_auth(['read:templates'])
def bulk_delete_templates():
    """Bulk delete templates"""

    data = request.get_json()
    if not data or not data.get('ids'):
        return error_response('ids array required', 400)

    ids = data['ids']
    results = {'success': [], 'failed': []}

    for template_id in ids:
        try:
            template = CertificateTemplate.query.get(template_id)
            if not template:
                results['failed'].append({'id': template_id, 'error': 'Not found'})
                continue
            if template.is_system:
                results['failed'].append({'id': template_id, 'error': 'Cannot delete system template'})
                continue
            template_name = template.name
            db.session.delete(template)
            db.session.commit()
            results['success'].append(template_id)
        except Exception as e:
            db.session.rollback()
            results['failed'].append({'id': template_id, 'error': str(e)})

    AuditService.log_action(
        action='templates_bulk_deleted',
        resource_type='template',
        resource_id=','.join(str(i) for i in results['success']),
        resource_name=f'{len(results["success"])} templates',
        details=f'Bulk deleted {len(results["success"])} templates',
        success=True
    )

    return success_response(data=results, message=f'{len(results["success"])} templates deleted')


@bp.route('/api/v2/templates/<int:template_id>/duplicate', methods=['POST'])
@require_auth(["write:templates"])
def duplicate_template(template_id):
    """
    Duplicate (clone) a template

    POST /api/v2/templates/{template_id}/duplicate
    """
    template = CertificateTemplate.query.get(template_id)
    if not template:
        return error_response('Template not found', 404)

    # Generate unique name
    base_name = template.name + ' (Copy)'
    name = base_name
    counter = 2
    while CertificateTemplate.query.filter_by(name=name).first():
        name = f'{base_name} {counter}'
        counter += 1

    clone = CertificateTemplate(
        name=name,
        description=template.description,
        template_type=template.template_type,
        key_type=template.key_type,
        validity_days=template.validity_days,
        digest=template.digest,
        dn_template=template.dn_template,
        extensions_template=template.extensions_template,
        is_system=False,
        is_active=template.is_active,
        created_by=g.current_user.username
    )

    try:
        db.session.add(clone)
        db.session.commit()

        AuditService.log_action(
            action='template_duplicate',
            resource_type='template',
            resource_id=str(clone.id),
            resource_name=clone.name,
            details=f'Duplicated from template: {template.name} (id={template.id})',
            success=True
        )

        return created_response(
            data=clone.to_dict(),
            message=f'Template duplicated as {clone.name}'
        )
    except Exception as e:
        db.session.rollback()
        return error_response(f'Failed to duplicate template: {str(e)}', 500)


@bp.route('/api/v2/templates/<int:template_id>/export', methods=['GET'])
@require_auth(['read:templates'])
def export_template(template_id):
    """
    Export template as JSON
    
    GET /api/v2/templates/{template_id}/export
    """
    from flask import Response
    import json
    
    template = CertificateTemplate.query.get(template_id)
    if not template:
        return error_response('Template not found', 404)
    
    export_data = {
        'name': template.name,
        'description': template.description,
        'template_type': template.template_type,
        'key_type': template.key_type,
        'validity_days': template.validity_days,
        'digest': template.digest,
        'dn_template': template.dn_template,
        'extensions_template': template.extensions_template,
        'is_system': False,  # Exported templates are not system
        'is_active': template.is_active,
    }
    
    return Response(
        json.dumps(export_data, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename="{template.name}.json"'}
    )


@bp.route('/api/v2/templates/export', methods=['GET'])
@require_auth(['read:templates'])
def export_all_templates():
    """
    Export all templates as JSON array
    
    GET /api/v2/templates/export
    """
    from flask import Response
    import json
    
    templates = CertificateTemplate.query.filter_by(is_system=False).all()
    
    export_data = []
    for template in templates:
        export_data.append({
            'name': template.name,
            'description': template.description,
            'template_type': template.template_type,
            'key_type': template.key_type,
            'validity_days': template.validity_days,
            'digest': template.digest,
            'dn_template': template.dn_template,
            'extensions_template': template.extensions_template,
            'is_system': False,
            'is_active': template.is_active,
        })
    
    return Response(
        json.dumps(export_data, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename="templates_export.json"'}
    )


@bp.route('/api/v2/templates/import', methods=['POST'])
@require_auth(['write:templates'])
def import_template():
    """
    Import template from JSON file or pasted JSON content
    
    Form data:
        file: JSON file (optional if json_content provided)
        json_content: Pasted JSON content (optional if file provided)
        update_existing: Whether to update if name exists (default: false)
    """
    import json
    
    # Get JSON data from file or pasted content
    json_data = None
    
    if 'file' in request.files and request.files['file'].filename:
        file = request.files['file']
        from utils.file_validation import validate_upload, JSON_EXTENSIONS
        try:
            raw, _ = validate_upload(file, JSON_EXTENSIONS)
            json_data = raw.decode('utf-8')
        except ValueError as e:
            return error_response(str(e), 400)
    elif request.form.get('json_content'):
        json_data = request.form.get('json_content')
    else:
        return error_response('No file or JSON content provided', 400)
    
    update_existing = request.form.get('update_existing', 'false').lower() == 'true'
    
    try:
        data = json.loads(json_data)
        
        # Handle both single template and array
        templates_to_import = data if isinstance(data, list) else [data]
        
        imported = []
        updated = []
        skipped = []
        
        for tpl_data in templates_to_import:
            if not tpl_data.get('name'):
                skipped.append('Template without name')
                continue
            
            # Check for existing
            existing = CertificateTemplate.query.filter_by(name=tpl_data['name']).first()
            
            if existing:
                if existing.is_system:
                    skipped.append(f"{tpl_data['name']} (system template)")
                    continue
                    
                if not update_existing:
                    skipped.append(f"{tpl_data['name']} (already exists)")
                    continue
                
                # Update existing
                existing.description = tpl_data.get('description', existing.description)
                existing.template_type = tpl_data.get('template_type', existing.template_type)
                existing.key_type = tpl_data.get('key_type', existing.key_type)
                existing.validity_days = tpl_data.get('validity_days', existing.validity_days)
                existing.digest = tpl_data.get('digest', existing.digest)
                existing.dn_template = tpl_data.get('dn_template', existing.dn_template)
                existing.extensions_template = tpl_data.get('extensions_template', existing.extensions_template)
                existing.is_active = tpl_data.get('is_active', existing.is_active)
                updated.append(existing.name)
            else:
                # Create new
                template = CertificateTemplate(
                    name=tpl_data['name'],
                    description=tpl_data.get('description', ''),
                    template_type=tpl_data.get('template_type', 'server'),
                    key_type=tpl_data.get('key_type', 'rsa:2048'),
                    validity_days=tpl_data.get('validity_days', 365),
                    digest=tpl_data.get('digest', 'sha256'),
                    dn_template=tpl_data.get('dn_template'),
                    extensions_template=tpl_data.get('extensions_template'),
                    is_system=False,
                    is_active=tpl_data.get('is_active', True),
                )
                db.session.add(template)
                imported.append(template.name)
        
        db.session.commit()
        
        AuditService.log_action(
            action='template_import',
            resource_type='template',
            resource_name='Template Import',
            details=f'Imported {len(imported)} templates, updated {len(updated)}, skipped {len(skipped)}',
            success=True
        )
        
        # Build message
        msg_parts = []
        if imported:
            msg_parts.append(f"Imported: {', '.join(imported)}")
        if updated:
            msg_parts.append(f"Updated: {', '.join(updated)}")
        if skipped:
            msg_parts.append(f"Skipped: {', '.join(skipped)}")
        
        return success_response(
            data={
                'imported': len(imported),
                'updated': len(updated),
                'skipped': len(skipped)
            },
            message=' | '.join(msg_parts) or 'No templates imported'
        )
        
    except json.JSONDecodeError as e:
        db.session.rollback()
        return error_response(f'Invalid JSON: {str(e)}', 400)
    except Exception as e:
        db.session.rollback()
        import traceback
        print(f"Template Import Error: {str(e)}")
        print(traceback.format_exc())
        return error_response(f'Import failed: {str(e)}', 500)
