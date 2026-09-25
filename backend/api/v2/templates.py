"""
Certificate Templates Management Routes v2.0
/api/v2/templates/* - Manage certificate templates
"""

from flask import Blueprint, request, g, Response
import logging
from auth.unified import require_auth
from utils.response import success_response, error_response, created_response, no_content_response
from utils.validity import DEFAULT_TEMPLATE_VALIDITY_DAYS
from utils.db_transaction import safe_commit
from utils.file_validation import validate_upload, JSON_EXTENSIONS
from utils.sanitize import sanitize_filename
from models import db, Certificate, CA
from models.certificate_template import CertificateTemplate
from models.policy import CertificatePolicy
from services.audit_service import AuditService
from services.deletion_blockers import (
    first_blocker, parse_bulk_ids, template_deletion_blockers,
)
from services.template_service import TemplateService
from utils.dn_validation import validate_dn_field
from datetime import datetime
import traceback


def _template_usage_counts():
    """Issued-certificate count per template_id, one grouped query."""
    rows = (
        db.session.query(Certificate.template_id, db.func.count(Certificate.id))
        .filter(Certificate.template_id.isnot(None))
        .group_by(Certificate.template_id)
        .all()
    )
    return {template_id: count for template_id, count in rows}

logger = logging.getLogger(__name__)
import json
from utils.datetime_utils import utc_now

bp = Blueprint('templates_v2', __name__)


from utils.validity import (MAX_VALIDITY_DAYS as _MAX_VALIDITY_DAYS,
                            MIN_VALIDITY_DAYS as _MIN_VALIDITY_DAYS,
                            coerce_validity_days)
_VALID_KEY_TYPES = {
    'RSA-2048', 'RSA-3072', 'RSA-4096',
    'EC-P256', 'EC-P384', 'EC-P521',
    # no ED25519: parse_issue_key_type() cannot generate an Edwards key, so a
    # template saved with it fails every issuance with a 400
    # legacy lowercase forms used by some import payloads
    'rsa:2048', 'rsa:3072', 'rsa:4096',
    'ec:p256', 'ec:p384', 'ec:p521',
}
_VALID_DIGESTS = {'sha256', 'sha384', 'sha512'}
_VALID_TEMPLATE_TYPES = {
    'web_server', 'email', 'vpn_server', 'vpn_client',
    'code_signing', 'client_auth', 'ocsp_signing', 'smartcard_logon',
    'piv', 'custom',
}


_PINNABLE_SUBJECT_FIELDS = {'O', 'OU', 'C', 'ST', 'L'}


def _clean_pinned_subject_fields(raw):
    """Returns (cleaned_dict, err_msg). Uppercases C, validates each present
    field via validate_dn_field (same check cert_create.py's manual-issuance
    path already applies to these same five DN keys), rejects unknown keys
    (including CN -- pinning never touches CN, only WSTEP's dynamic-CN/SAN
    contract stays intact)."""
    if not raw:
        return {}, None
    if not isinstance(raw, dict):
        return None, 'pinned_subject_fields must be an object'
    cleaned = {}
    for key, value in raw.items():
        if key not in _PINNABLE_SUBJECT_FIELDS:
            return None, f'Unsupported pinned subject field: {key}'
        if not value:
            continue
        value = value.strip().upper() if key == 'C' else value.strip()
        ok, err = validate_dn_field(key, value)
        if not ok:
            return None, err
        cleaned[key] = value
    return cleaned, None


def _coerce_json_object_fields(tpl_data):
    """Returns err_msg or None. Coerces dn_template / extensions_template /
    pinned_subject_fields to dicts in place. Exports carry the first two as
    JSON strings while API payloads carry objects; storing a string as-is
    would double-encode it (json.dumps of a str) and the template would
    silently lose its subject/extension settings."""
    for key in ('dn_template', 'extensions_template', 'pinned_subject_fields'):
        if key not in tpl_data or tpl_data[key] is None:
            continue
        value = tpl_data[key]
        if isinstance(value, str):
            if not value.strip():
                tpl_data[key] = {}
                continue
            try:
                value = json.loads(value)
            except (TypeError, ValueError):
                return f'{key} is not valid JSON'
        if not isinstance(value, dict):
            return f'{key} must be an object'
        tpl_data[key] = value
    return None


def _validate_template_payload(data, *, partial=False):
    """Returns (ok, err_msg). Sanitises validity_days/key_type/digest/template_type."""
    err = _coerce_json_object_fields(data)
    if err:
        return False, err
    if 'pinned_subject_fields' in data:
        cleaned, err = _clean_pinned_subject_fields(data['pinned_subject_fields'])
        if err:
            return False, err
        data['pinned_subject_fields'] = cleaned
    if 'validity_days' in data:
        v = coerce_validity_days(data['validity_days'])
        if v is None:
            return False, 'validity_days must be an integer'
        if v < _MIN_VALIDITY_DAYS or v > _MAX_VALIDITY_DAYS:
            return False, f'validity_days must be between {_MIN_VALIDITY_DAYS} and {_MAX_VALIDITY_DAYS}'
        data['validity_days'] = v
    elif not partial:
        # default applied at object creation, no-op
        pass
    if 'key_type' in data and data['key_type']:
        if data['key_type'] not in _VALID_KEY_TYPES:
            return False, f'Unsupported key_type: {data["key_type"]}'
    if 'digest' in data and data['digest']:
        if data['digest'].lower() not in _VALID_DIGESTS:
            return False, f'Unsupported digest: {data["digest"]} (allowed: {", ".join(sorted(_VALID_DIGESTS))})'
        data['digest'] = data['digest'].lower()
    if 'template_type' in data and data['template_type']:
        if data['template_type'] not in _VALID_TEMPLATE_TYPES:
            return False, f'Invalid template type. Must be one of: {", ".join(sorted(_VALID_TEMPLATE_TYPES))}'
    if 'extensions_template' in data and isinstance(data['extensions_template'], dict):
        # CA key usages belong to CA templates only: on a leaf they would be
        # ignored by some issuance paths and honoured by others
        ku = data['extensions_template'].get('key_usage')
        if isinstance(ku, list):
            # Certificate templates describe end-entity certificates: the CA
            # key usages are dropped (no issuance path honours them)
            kept = [k for k in ku if str(k).lower() not in ('keycertsign', 'crlsign')]
            if len(kept) != len(ku):
                logger.warning("template payload: CA key usages dropped from key_usage")
                data['extensions_template']['key_usage'] = kept
    return True, None


@bp.route('/api/v2/templates', methods=['GET'])
@require_auth(["read:templates"])
def list_templates():
    """
    List all certificate templates
    
    Query params:
    - type: Filter by template_type
    - active: Filter by is_active (true/false)
    - search: Search name, description
    - ca_id: If provided, returns all templates with is_pinned flag for this CA
    """
    type_list = request.args.getlist('type')
    active_str = request.args.get('active')
    search = request.args.get('search', '').strip()
    ca_id = request.args.get('ca_id', type=int)
    
    # If ca_id is provided, return templates with pin status
    if ca_id:
        # Verify CA exists
        ca = db.session.get(CA, ca_id)
        if not ca:
            return error_response('CA not found', 404)
        
        try:
            templates = TemplateService.get_templates_with_pin_status(ca_id, active_only=(active_str != 'false'))
            
            # Apply additional filters if provided
            if type_list:
                templates = [t for t in templates if t['template_type'] in type_list]
            
            if search:
                search_lower = search.lower()
                templates = [t for t in templates if
                           search_lower in t['name'].lower() or
                           search_lower in (t.get('description') or '').lower()]

            counts = _template_usage_counts()
            for t in templates:
                t['usage_count'] = counts.get(t['id'], 0)
            return success_response(data=templates)
        except Exception as e:
            logger.error(f"Failed to list templates with pin status for CA {ca_id}: {e}")
            return error_response('Failed to list templates', 500)
    
    # Original behavior: return all templates without pin status
    query = CertificateTemplate.query
    
    if type_list:
        query = query.filter(CertificateTemplate.template_type.in_(type_list))
    
    if active_str:
        active = active_str.lower() == 'true'
        query = query.filter_by(is_active=active)
    
    if search:
        safe_search = search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        search_pattern = f'%{safe_search}%'
        query = query.filter(
            db.or_(
                CertificateTemplate.name.ilike(search_pattern),
                CertificateTemplate.description.ilike(search_pattern)
            )
        )
    
    templates = query.order_by(CertificateTemplate.created_at.desc()).all()

    counts = _template_usage_counts()
    data = []
    for template in templates:
        d = template.to_dict()
        d['usage_count'] = counts.get(template.id, 0)
        data.append(d)
    return success_response(data=data)


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

    # Validate template type / key_type / digest / validity bounds
    ok, err = _validate_template_payload(data)
    if not ok:
        return error_response(err, 400)
    
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
        elif data['template_type'] == 'ocsp_signing':
            extensions = {
                "key_usage": ["digitalSignature"],
                "extended_key_usage": ["OCSPSigning"],
                "basic_constraints": {"ca": False}
            }
    
    # Create template
    template = CertificateTemplate(
        name=data['name'],
        description=data.get('description', ''),
        template_type=data['template_type'],
        key_type=data.get('key_type', 'RSA-2048'),
        validity_days=data.get('validity_days',
                                DEFAULT_TEMPLATE_VALIDITY_DAYS),
        digest=data.get('digest', 'sha256'),
        dn_template=json.dumps(data.get('dn_template', {})),
        extensions_template=json.dumps(extensions),
        is_system=False,  # User-created templates are never system
        is_active=True,
        ad_derived_subject=bool(data.get('ad_derived_subject', False)),
        autoenroll_enabled=bool(data.get('autoenroll_enabled', False)),
        allowed_ad_group=(data.get('allowed_ad_group') or '').strip()[:255] or None,
        pinned_subject_fields=json.dumps(data.get('pinned_subject_fields') or {}),
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
        logger.error(f'Failed to create template: {e}')
        return error_response('Failed to create template', 500)


@bp.route('/api/v2/templates/<int:template_id>', methods=['GET'])
@require_auth(["read:templates"])
def get_template(template_id):
    """Get single template details"""
    template = db.session.get(CertificateTemplate, template_id)
    if not template:
        return error_response('Template not found', 404)

    data = template.to_dict()
    data['usage_count'] = (
        Certificate.query.filter_by(template_id=template.id).count()
    )
    return success_response(data=data)


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
    template = db.session.get(CertificateTemplate, template_id)
    if not template:
        return error_response('Template not found', 404)
    
    # Prevent updating system templates
    if template.is_system:
        return error_response('Cannot modify system templates', 403)
    
    data = request.get_json()

    # Validate any provided fields (validity bounds + enums)
    ok, err = _validate_template_payload(data, partial=True)
    if not ok:
        return error_response(err, 400)

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
        template.template_type = data['template_type']

    if 'key_type' in data:
        template.key_type = data['key_type']

    if 'validity_days' in data:
        template.validity_days = data['validity_days']  # already coerced to int by _validate_template_payload

    if 'digest' in data:
        template.digest = data['digest']  # already lowercased
    
    if 'dn_template' in data:
        template.dn_template = json.dumps(data['dn_template'])
    
    if 'extensions_template' in data:
        template.extensions_template = json.dumps(data['extensions_template'])
    
    if 'is_active' in data:
        template.is_active = bool(data['is_active'])

    if 'ad_derived_subject' in data:
        template.ad_derived_subject = bool(data['ad_derived_subject'])

    if 'autoenroll_enabled' in data:
        template.autoenroll_enabled = bool(data['autoenroll_enabled'])

    if 'allowed_ad_group' in data:
        template.allowed_ad_group = (data['allowed_ad_group'] or '').strip()[:255] or None

    if 'pinned_subject_fields' in data:
        template.pinned_subject_fields = json.dumps(data['pinned_subject_fields'] or {})

    template.updated_by = g.current_user.username
    template.updated_at = utc_now()
    
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
        logger.error(f'Failed to update template: {e}')
        return error_response('Failed to update template', 500)


@bp.route('/api/v2/templates/<int:template_id>', methods=['DELETE'])
@require_auth(["delete:templates"])
def delete_template(template_id):
    """
    Delete certificate template
    
    DELETE /api/v2/templates/{template_id}
    """
    template = db.session.get(CertificateTemplate, template_id)
    if not template:
        return error_response('Template not found', 404)
    
    blocker = first_blocker(template_deletion_blockers(template))
    if blocker:
        return error_response(blocker.message, blocker.status)

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
        
        return no_content_response()
    except Exception as e:
        db.session.rollback()
        logger.error(f'Failed to delete template: {e}')
        return error_response('Failed to delete template', 500)


# ============================================================
# Bulk Operations
# ============================================================

@bp.route('/api/v2/templates/bulk/delete', methods=['POST'])
@require_auth(['delete:templates'])
def bulk_delete_templates():
    """Bulk delete templates"""

    ids, err = parse_bulk_ids(request.get_json())
    if err:
        return err

    results = {'success': [], 'failed': []}

    for template_id in ids:
        template = db.session.get(CertificateTemplate, template_id)
        if not template:
            results['failed'].append({'id': template_id, 'error': 'Not found'})
            continue
        blocker = first_blocker(template_deletion_blockers(template))
        if blocker:
            results['failed'].append({'id': template_id, 'error': blocker.brief})
            continue
        db.session.delete(template)
        ok, _err = safe_commit(logger, f"Delete template {template_id}")
        if not ok:
            # One template that will not go is not a reason to abandon the
            # rest: returning here left the caller with no results body at
            # all, the ids already committed silently deleted, and the ids
            # after this one never even attempted.
            results['failed'].append({'id': template_id, 'error': 'Deletion failed'})
            continue
        results['success'].append(template_id)

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
    template = db.session.get(CertificateTemplate, template_id)
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
        ad_derived_subject=template.ad_derived_subject,
        autoenroll_enabled=template.autoenroll_enabled,
        allowed_ad_group=template.allowed_ad_group,
        pinned_subject_fields=template.pinned_subject_fields,
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
        logger.error(f'Failed to duplicate template: {e}')
        return error_response('Failed to duplicate template', 500)


def _template_export_dict(template):
    """Portable representation of a template for export/import.

    dn_template / extensions_template stay JSON strings (the historical
    export format) so files remain importable by older UCM versions; the
    importer accepts either strings or objects for them."""
    return {
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
        'ad_derived_subject': bool(template.ad_derived_subject),
        'autoenroll_enabled': bool(template.autoenroll_enabled),
        'allowed_ad_group': template.allowed_ad_group,
        'pinned_subject_fields': (
            json.loads(template.pinned_subject_fields)
            if template.pinned_subject_fields else {}
        ),
    }


@bp.route('/api/v2/templates/<int:template_id>/export', methods=['GET'])
@require_auth(['read:templates'])
def export_template(template_id):
    """
    Export template as JSON
    
    GET /api/v2/templates/{template_id}/export
    """
    
    template = db.session.get(CertificateTemplate, template_id)
    if not template:
        return error_response('Template not found', 404)
    
    export_data = _template_export_dict(template)
    
    return Response(
        json.dumps(export_data, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename="{sanitize_filename(template.name)}.json"'}
    )


@bp.route('/api/v2/templates/export', methods=['GET'])
@require_auth(['read:templates'])
def export_all_templates():
    """
    Export all templates as JSON array
    
    GET /api/v2/templates/export
    """
    
    templates = CertificateTemplate.query.filter_by(is_system=False).all()
    
    export_data = [_template_export_dict(template) for template in templates]
    
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
    
    # Get JSON data from file or pasted content
    json_data = None
    
    if 'file' in request.files and request.files['file'].filename:
        file = request.files['file']
        try:
            raw, _ = validate_upload(file, JSON_EXTENSIONS)
            json_data = raw.decode('utf-8')
        except ValueError as e:
            logger.error(f'Template import file validation failed: {e}')
            return error_response('Invalid file upload', 400)
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

            # Validate per-item; reject the item but continue with the rest
            ok, err = _validate_template_payload(tpl_data, partial=True)
            if not ok:
                skipped.append(f"{tpl_data['name']} ({err})")
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
                if tpl_data.get('dn_template') is not None:
                    existing.dn_template = json.dumps(tpl_data['dn_template'])
                if tpl_data.get('extensions_template') is not None:
                    existing.extensions_template = json.dumps(tpl_data['extensions_template'])
                existing.is_active = tpl_data.get('is_active', existing.is_active)
                if 'ad_derived_subject' in tpl_data:
                    existing.ad_derived_subject = bool(tpl_data['ad_derived_subject'])
                if 'autoenroll_enabled' in tpl_data:
                    existing.autoenroll_enabled = bool(tpl_data['autoenroll_enabled'])
                if 'allowed_ad_group' in tpl_data:
                    existing.allowed_ad_group = (tpl_data['allowed_ad_group'] or '').strip()[:255] or None
                if 'pinned_subject_fields' in tpl_data:
                    existing.pinned_subject_fields = json.dumps(tpl_data['pinned_subject_fields'] or {})
                updated.append(existing.name)
            else:
                # Create new — _validate_template_payload already enforced enums + bounds.
                # Default template_type=custom (was 'server', not in valid set).
                template = CertificateTemplate(
                    name=tpl_data['name'],
                    description=tpl_data.get('description', ''),
                    template_type=tpl_data.get('template_type', 'custom'),
                    key_type=tpl_data.get('key_type', 'RSA-2048'),
                    validity_days=tpl_data.get(
                        'validity_days', DEFAULT_TEMPLATE_VALIDITY_DAYS),
                    digest=tpl_data.get('digest', 'sha256'),
                    dn_template=json.dumps(tpl_data.get('dn_template') or {}),
                    extensions_template=json.dumps(tpl_data.get('extensions_template') or {}),
                    is_system=False,
                    is_active=tpl_data.get('is_active', True),
                    ad_derived_subject=bool(tpl_data.get('ad_derived_subject', False)),
                    autoenroll_enabled=bool(tpl_data.get('autoenroll_enabled', False)),
                    allowed_ad_group=(tpl_data.get('allowed_ad_group') or '').strip()[:255] or None,
                    pinned_subject_fields=json.dumps(tpl_data.get('pinned_subject_fields') or {}),
                )
                db.session.add(template)
                imported.append(template.name)
        
        ok, _err = safe_commit(logger, "Failed to import templates")
        if not ok:
            return _err
        
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
        logger.error(f'Template import invalid JSON: {e}')
        return error_response('Invalid JSON format', 400)
    except Exception as e:
        db.session.rollback()
        logger.error(f"Template Import Error: {str(e)}")
        logger.error(traceback.format_exc())
        logger.error(f'Import failed: {e}')
        return error_response('Import failed', 500)


# ============================================================================
# CA-Template Pinning Endpoints
# ============================================================================

@bp.route('/api/v2/cas/<int:ca_id>/templates', methods=['GET'])
@require_auth(['read:cas', 'read:templates'])
def list_templates_with_pin_status(ca_id):
    """
    List all templates with pin status for a specific CA
    
    GET /api/v2/cas/{ca_id}/templates
    
    Returns all templates with is_pinned flag indicating which are pinned to this CA.
    """
    # Verify CA exists
    ca = db.session.get(CA, ca_id)
    if not ca:
        return error_response('CA not found', 404)
    
    try:
        templates = TemplateService.get_templates_with_pin_status(ca_id)
        
        return success_response(
            data={
                'ca_id': ca_id,
                'ca_name': ca.descr,
                'templates': templates
            }
        )
    except Exception as e:
        logger.error(f"Failed to list templates with pin status for CA {ca_id}: {e}")
        return error_response('Failed to list templates', 500)


@bp.route('/api/v2/cas/<int:ca_id>/templates/<int:template_id>/pin', methods=['POST'])
@require_auth(['write:cas', 'write:templates'])
def pin_template_to_ca(ca_id, template_id):
    """
    Pin a template to a specific CA
    
    POST /api/v2/cas/{ca_id}/templates/{template_id}/pin
    
    When a CA has pinned templates, only those templates will be shown by default
    in the certificate creation form (with a "Show all" toggle available).
    """
    username = g.current_user.username if hasattr(g, 'current_user') else 'system'
    
    try:
        pin = TemplateService.pin_template_to_ca(ca_id, template_id, username)
        
        # Get template and CA names for audit
        template = db.session.get(CertificateTemplate, template_id)
        ca = db.session.get(CA, ca_id)
        
        AuditService.log_action(
            action='template_pinned_to_ca',
            resource_type='template',
            resource_id=str(template_id),
            resource_name=template.name if template else f'Template {template_id}',
            details=f'Pinned template "{template.name if template else template_id}" to CA "{ca.descr if ca else ca_id}"',
            success=True,
            username=username
        )
        
        return created_response(
            data=pin.to_dict(),
            message=f'Template pinned to CA successfully'
        )
        
    except ValueError as e:
        return error_response(str(e), 400)
    except Exception as e:
        logger.error(f"Failed to pin template {template_id} to CA {ca_id}: {e}")
        return error_response('Failed to pin template to CA', 500)


@bp.route('/api/v2/cas/<int:ca_id>/templates/<int:template_id>/pin', methods=['DELETE'])
@require_auth(['write:cas', 'write:templates'])
def unpin_template_from_ca(ca_id, template_id):
    """
    Unpin a template from a specific CA
    
    DELETE /api/v2/cas/{ca_id}/templates/{template_id}/pin
    
    Removes the pin relationship between the template and CA.
    """
    username = g.current_user.username if hasattr(g, 'current_user') else 'system'
    
    try:
        success = TemplateService.unpin_template_from_ca(ca_id, template_id)
        
        if not success:
            return error_response('Template is not pinned to this CA', 404)
        
        # Get template and CA names for audit
        template = db.session.get(CertificateTemplate, template_id)
        ca = db.session.get(CA, ca_id)
        
        AuditService.log_action(
            action='template_unpinned_from_ca',
            resource_type='template',
            resource_id=str(template_id),
            resource_name=template.name if template else f'Template {template_id}',
            details=f'Unpinned template "{template.name if template else template_id}" from CA "{ca.descr if ca else ca_id}"',
            success=True,
            username=username
        )
        
        return success_response(
            message=f'Template unpinned from CA successfully'
        )
        
    except Exception as e:
        logger.error(f"Failed to unpin template {template_id} from CA {ca_id}: {e}")
        return error_response('Failed to unpin template from CA', 500)
