"""
Certificate Template API
RESTful API for managing certificate templates
"""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from models import db, CertificateTemplate, User
from services.template_service import TemplateService
from middleware.auth_middleware import operator_required, admin_required

bp = Blueprint('templates', __name__, url_prefix='/api/v1/templates')


@bp.route('/', methods=['GET'])
@jwt_required()
def list_templates():
    """
    List all certificate templates
    
    Query params:
        active_only: bool (default: true)
    """
    active_only = request.args.get('active_only', 'true').lower() == 'true'
    
    templates = TemplateService.get_all_templates(active_only=active_only)
    
    return jsonify({
        "templates": [t.to_dict() for t in templates],
        "count": len(templates)
    })


@bp.route('/<int:template_id>', methods=['GET'])
@jwt_required()
def get_template(template_id):
    """Get a specific template by ID"""
    template = TemplateService.get_template(template_id)
    
    if not template:
        return jsonify({"error": "Template not found"}), 404
    
    return jsonify(template.to_dict())


@bp.route('/', methods=['POST'])
@jwt_required()
@admin_required
def create_template():
    """
    Create a new custom template
    
    Body:
        name: str (required)
        description: str
        template_type: str (default: custom)
        key_type: str (default: RSA-2048)
        validity_days: int (default: 397)
        digest: str (default: sha256)
        dn_template: dict
        extensions_template: dict (required)
    """
    data = request.get_json()
    
    # Validation
    if not data.get('name'):
        return jsonify({"error": "Template name is required"}), 400
    
    if not data.get('extensions_template'):
        return jsonify({"error": "extensions_template is required"}), 400
    
    # Check for duplicate name
    existing = TemplateService.get_template_by_name(data['name'])
    if existing:
        return jsonify({"error": "Template name already exists"}), 409
    
    try:
        username = get_jwt_identity()
        template = TemplateService.create_template(data, username)
        
        return jsonify({
            "message": "Template created successfully",
            "template": template.to_dict()
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@bp.route('/<int:template_id>', methods=['PUT'])
@jwt_required()
@admin_required
def update_template(template_id):
    """
    Update an existing template (custom only)
    
    Body: Same as create_template
    """
    data = request.get_json()
    
    try:
        username = get_jwt_identity()
        template = TemplateService.update_template(template_id, data, username)
        
        return jsonify({
            "message": "Template updated successfully",
            "template": template.to_dict()
        })
        
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@bp.route('/<int:template_id>', methods=['DELETE'])
@jwt_required()
@admin_required
def delete_template(template_id):
    """Delete a template (custom only)"""
    try:
        TemplateService.delete_template(template_id)
        
        return jsonify({"message": "Template deleted successfully"})
        
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@bp.route('/<int:template_id>/render', methods=['POST'])
@jwt_required()
def render_template(template_id):
    """
    Render a template with variables
    
    Body:
        variables: dict (e.g. {"hostname": "www.example.com", "email": "user@example.com"})
    """
    data = request.get_json()
    variables = data.get('variables', {})
    
    try:
        rendered = TemplateService.render_template(template_id, variables)
        return jsonify(rendered)
        
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
