"""
Certificate Template Service
Manages certificate templates for pre-configured certificate profiles
"""
import json
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime

from models import db, CertificateTemplate, CA, CATemplatePin
from utils.datetime_utils import utc_now
import logging

logger = logging.getLogger(__name__)


class TemplateService:
    """Service for Certificate Template operations"""
    
    # System template definitions
    SYSTEM_TEMPLATES = [
        {
            "name": "Web Server (TLS/SSL)",
            "description": "SSL/TLS certificate for web servers (HTTPS). Compatible with Apache, Nginx, IIS. Validity: 397 days (Apple/Chrome limit).",
            "template_type": "web_server",
            "key_type": "RSA-2048",
            "validity_days": 397,
            "digest": "sha256",
            "dn_template": json.dumps({
                "CN": "{hostname}",
                "O": "",
                "OU": "IT",
                "C": "",
                "ST": "",
                "L": ""
            }),
            "extensions_template": json.dumps({
                "key_usage": ["digitalSignature", "keyEncipherment"],
                "extended_key_usage": ["serverAuth"],
                "basic_constraints": {"ca": False},
                "san_types": ["dns", "ip"]
            }),
            "is_system": True,
            "is_active": True
        },
        {
            "name": "Email Certificate (S/MIME)",
            "description": "S/MIME certificate for email encryption and digital signatures. Compatible with Outlook, Thunderbird, Apple Mail.",
            "template_type": "email",
            "key_type": "RSA-2048",
            "validity_days": 397,
            "digest": "sha256",
            "dn_template": json.dumps({
                "CN": "{email}",
                "O": "",
                "OU": "Users",
                "C": "",
                "ST": "",
                "L": ""
            }),
            "extensions_template": json.dumps({
                "key_usage": ["digitalSignature", "keyEncipherment", "dataEncipherment"],
                "extended_key_usage": ["emailProtection"],
                "basic_constraints": {"ca": False},
                "san_types": ["email"]
            }),
            "is_system": True,
            "is_active": True
        },
        {
            "name": "VPN Server",
            "description": "VPN server certificate for OpenVPN, IPsec, WireGuard. Includes serverAuth and ipsecEndSystem extended key usage.",
            "template_type": "vpn_server",
            "key_type": "RSA-2048",
            "validity_days": 825,
            "digest": "sha256",
            "dn_template": json.dumps({
                "CN": "{hostname}",
                "O": "",
                "OU": "VPN",
                "C": "",
                "ST": "",
                "L": ""
            }),
            "extensions_template": json.dumps({
                "key_usage": ["digitalSignature", "keyEncipherment"],
                "extended_key_usage": ["serverAuth", "ipsecEndSystem"],
                "basic_constraints": {"ca": False},
                "san_types": ["dns", "ip"]
            }),
            "is_system": True,
            "is_active": True
        },
        {
            "name": "VPN Client",
            "description": "VPN client certificate for user authentication. Compatible with OpenVPN, IPsec clients.",
            "template_type": "vpn_client",
            "key_type": "RSA-2048",
            "validity_days": 397,
            "digest": "sha256",
            "dn_template": json.dumps({
                "CN": "{username}",
                "O": "",
                "OU": "VPN Users",
                "C": "",
                "ST": "",
                "L": ""
            }),
            "extensions_template": json.dumps({
                "key_usage": ["digitalSignature", "keyEncipherment"],
                "extended_key_usage": ["clientAuth", "ipsecUser"],
                "basic_constraints": {"ca": False},
                "san_types": ["email"]
            }),
            "is_system": True,
            "is_active": True
        },
        {
            "name": "Code Signing",
            "description": "Code signing certificate for software developers. Sign executables, scripts, packages. Validity: 3 years max.",
            "template_type": "code_signing",
            "key_type": "RSA-2048",
            "validity_days": 1095,
            "digest": "sha256",
            "dn_template": json.dumps({
                "CN": "{username}",
                "O": "",
                "OU": "Development",
                "C": "",
                "ST": "",
                "L": ""
            }),
            "extensions_template": json.dumps({
                "key_usage": ["digitalSignature"],
                "extended_key_usage": ["codeSigning"],
                "basic_constraints": {"ca": False},
                "san_types": []
            }),
            "is_system": True,
            "is_active": True
        },
        {
            "name": "Client Authentication",
            "description": "Client authentication certificate for user/device authentication. Compatible with 802.1X, RADIUS, mTLS.",
            "template_type": "client_auth",
            "key_type": "RSA-2048",
            "validity_days": 397,
            "digest": "sha256",
            "dn_template": json.dumps({
                "CN": "{username}",
                "O": "",
                "OU": "Users",
                "C": "",
                "ST": "",
                "L": ""
            }),
            "extensions_template": json.dumps({
                "key_usage": ["digitalSignature", "keyEncipherment"],
                "extended_key_usage": ["clientAuth"],
                "basic_constraints": {"ca": False},
                "san_types": ["email"]
            }),
            "is_system": True,
            "is_active": True
        }
    ]
    
    @staticmethod
    def get_all_templates(active_only: bool = True) -> List[CertificateTemplate]:
        """
        Get all certificate templates
        
        Args:
            active_only: Only return active templates
            
        Returns:
            List of CertificateTemplate objects
        """
        query = CertificateTemplate.query
        if active_only:
            query = query.filter_by(is_active=True)
        return query.order_by(CertificateTemplate.is_system.desc(), CertificateTemplate.name).all()
    
    @staticmethod
    def get_template(template_id: int) -> Optional[CertificateTemplate]:
        """
        Get a template by ID
        
        Args:
            template_id: Template ID
            
        Returns:
            CertificateTemplate object or None
        """
        return CertificateTemplate.query.get(template_id)
    
    @staticmethod
    def get_template_by_name(name: str) -> Optional[CertificateTemplate]:
        """
        Get a template by name
        
        Args:
            name: Template name
            
        Returns:
            CertificateTemplate object or None
        """
        return CertificateTemplate.query.filter_by(name=name).first()
    
    @staticmethod
    def create_template(data: Dict[str, Any], username: str) -> CertificateTemplate:
        """
        Create a new custom template
        
        Args:
            data: Template data
            username: Creator username
            
        Returns:
            Created CertificateTemplate
        """
        template = CertificateTemplate(
            name=data['name'],
            description=data.get('description', ''),
            template_type=data.get('template_type', 'custom'),
            key_type=data.get('key_type', 'RSA-2048'),
            validity_days=data.get('validity_days', 397),
            digest=data.get('digest', 'sha256'),
            dn_template=json.dumps(data.get('dn_template', {})),
            extensions_template=json.dumps(data.get('extensions_template', {})),
            is_system=False,  # Custom templates are never system
            is_active=True,
            created_by=username,
            created_at=utc_now()
        )
        
        db.session.add(template)
        try:
            db.session.commit()
        except Exception as _commit_err:
            db.session.rollback()
            logger.error(f"Commit failed in services/template_service.py:238: {_commit_err}", exc_info=True)
            raise
        
        return template
    
    @staticmethod
    def update_template(template_id: int, data: Dict[str, Any], username: str) -> CertificateTemplate:
        """
        Update an existing template (custom only)
        
        Args:
            template_id: Template ID
            data: Updated data
            username: Editor username
            
        Returns:
            Updated CertificateTemplate
            
        Raises:
            ValueError: If template is system template
        """
        template = CertificateTemplate.query.get(template_id)
        if not template:
            raise ValueError("Template not found")
        
        if template.is_system:
            raise ValueError("Cannot modify system templates")
        
        # Update fields
        if 'name' in data:
            template.name = data['name']
        if 'description' in data:
            template.description = data['description']
        if 'template_type' in data:
            template.template_type = data['template_type']
        if 'key_type' in data:
            template.key_type = data['key_type']
        if 'validity_days' in data:
            template.validity_days = data['validity_days']
        if 'digest' in data:
            template.digest = data['digest']
        if 'dn_template' in data:
            template.dn_template = json.dumps(data['dn_template'])
        if 'extensions_template' in data:
            template.extensions_template = json.dumps(data['extensions_template'])
        if 'is_active' in data:
            template.is_active = data['is_active']
        
        template.updated_by = username
        template.updated_at = utc_now()
        
        try:
            db.session.commit()
        except Exception as _commit_err:
            db.session.rollback()
            logger.error(f"Commit failed in services/template_service.py:288: {_commit_err}", exc_info=True)
            raise
        
        return template
    
    @staticmethod
    def delete_template(template_id: int) -> bool:
        """
        Delete a template (custom only)
        
        Args:
            template_id: Template ID
            
        Returns:
            True if deleted
            
        Raises:
            ValueError: If template is system template or in use
        """
        template = CertificateTemplate.query.get(template_id)
        if not template:
            raise ValueError("Template not found")
        
        if template.is_system:
            raise ValueError("Cannot delete system templates")
        
        # Check if template is in use
        from models import Certificate
        in_use = Certificate.query.filter_by(template_id=template_id).count()
        if in_use > 0:
            raise ValueError(f"Cannot delete template: {in_use} certificate(s) using this template")
        
        db.session.delete(template)
        try:
            db.session.commit()
        except Exception as _commit_err:
            db.session.rollback()
            logger.error(f"Commit failed in services/template_service.py:320: {_commit_err}", exc_info=True)
            raise
        
        return True
    
    @staticmethod
    def render_template(template_id: int, variables: Dict[str, str]) -> Dict[str, Any]:
        """
        Render a template with provided variables
        
        Args:
            template_id: Template ID
            variables: Variables to substitute (e.g. {"hostname": "www.example.com"})
            
        Returns:
            Dict with rendered dn, extensions, and other template data
        """
        template = CertificateTemplate.query.get(template_id)
        if not template:
            raise ValueError("Template not found")
        
        # Parse JSON
        dn_template = json.loads(template.dn_template) if template.dn_template else {}
        extensions = json.loads(template.extensions_template) if template.extensions_template else {}
        
        # Render DN fields with variables
        rendered_dn = {}
        for key, value in dn_template.items():
            if isinstance(value, str):
                # Replace {variable} placeholders
                for var_name, var_value in variables.items():
                    value = value.replace(f"{{{var_name}}}", var_value)
            rendered_dn[key] = value
        
        return {
            "name": template.name,
            "template_type": template.template_type,
            "key_type": template.key_type,
            "validity_days": template.validity_days,
            "digest": template.digest,
            "dn": rendered_dn,
            "extensions": extensions
        }
    
    @staticmethod
    def pin_template_to_ca(ca_id: int, template_id: int, username: str) -> CATemplatePin:
        """
        Pin a template to a specific CA
        
        Args:
            ca_id: CA ID
            template_id: Template ID
            username: User creating the pin
            
        Returns:
            Created CATemplatePin object
            
        Raises:
            ValueError: If CA or template not found, or already pinned
        """
        # Verify CA exists
        ca = CA.query.get(ca_id)
        if not ca:
            raise ValueError(f"CA with id {ca_id} not found")
        
        # Verify template exists
        template = CertificateTemplate.query.get(template_id)
        if not template:
            raise ValueError(f"Template with id {template_id} not found")
        
        # Check if already pinned
        existing = CATemplatePin.query.filter_by(ca_id=ca_id, template_id=template_id).first()
        if existing:
            raise ValueError(f"Template {template_id} is already pinned to CA {ca_id}")
        
        # Create pin
        pin = CATemplatePin(
            ca_id=ca_id,
            template_id=template_id,
            created_by=username,
            created_at=utc_now()
        )
        
        db.session.add(pin)
        try:
            db.session.commit()
        except Exception as _commit_err:
            db.session.rollback()
            logger.error(f"Commit failed in pin_template_to_ca: {_commit_err}", exc_info=True)
            raise
        
        logger.info(f"Pinned template {template_id} to CA {ca_id} by {username}")
        return pin
    
    @staticmethod
    def unpin_template_from_ca(ca_id: int, template_id: int) -> bool:
        """
        Unpin a template from a CA
        
        Args:
            ca_id: CA ID
            template_id: Template ID
            
        Returns:
            True if unpinned, False if pin didn't exist
        """
        pin = CATemplatePin.query.filter_by(ca_id=ca_id, template_id=template_id).first()
        if not pin:
            return False
        
        db.session.delete(pin)
        try:
            db.session.commit()
        except Exception as _commit_err:
            db.session.rollback()
            logger.error(f"Commit failed in unpin_template_from_ca: {_commit_err}", exc_info=True)
            raise
        
        logger.info(f"Unpinned template {template_id} from CA {ca_id}")
        return True
    
    @staticmethod
    def get_pinned_templates_for_ca(ca_id: int, active_only: bool = True) -> List[CertificateTemplate]:
        """
        Get all templates pinned to a specific CA
        
        Args:
            ca_id: CA ID
            active_only: Only return active templates
            
        Returns:
            List of CertificateTemplate objects
        """
        query = db.session.query(CertificateTemplate).join(
            CATemplatePin,
            CertificateTemplate.id == CATemplatePin.template_id
        ).filter(CATemplatePin.ca_id == ca_id)
        
        if active_only:
            query = query.filter(CertificateTemplate.is_active == True)
        
        return query.order_by(CertificateTemplate.name).all()
    
    @staticmethod
    def get_templates_with_pin_status(ca_id: int, active_only: bool = True) -> List[Dict[str, Any]]:
        """
        Get all templates with pin status for a specific CA
        
        Args:
            ca_id: CA ID
            active_only: Only return active templates
            
        Returns:
            List of dicts with template data and is_pinned flag
        """
        # Get all templates
        templates_query = CertificateTemplate.query
        if active_only:
            templates_query = templates_query.filter_by(is_active=True)
        
        templates = templates_query.order_by(
            CertificateTemplate.is_system.desc(),
            CertificateTemplate.name
        ).all()
        
        # Get pinned template IDs for this CA
        pinned_ids = set(
            pin.template_id for pin in CATemplatePin.query.filter_by(ca_id=ca_id).all()
        )
        
        # Build result with is_pinned flag
        result = []
        for template in templates:
            template_dict = template.to_dict()
            template_dict['is_pinned'] = template.id in pinned_ids
            result.append(template_dict)
        
        return result
    
    @staticmethod
    def seed_system_templates() -> int:
        """
        Seed system templates into database
        
        Returns:
            Number of templates created
        """
        count = 0
        for template_data in TemplateService.SYSTEM_TEMPLATES:
            # Check if template already exists
            existing = CertificateTemplate.query.filter_by(name=template_data['name']).first()
            if not existing:
                template = CertificateTemplate(**template_data)
                template.created_at = utc_now()
                template.created_by = 'system'
                db.session.add(template)
                count += 1
        
        try:
            db.session.commit()
        except Exception as _commit_err:
            db.session.rollback()
            logger.error(f"Commit failed in services/template_service.py:382: {_commit_err}", exc_info=True)
            raise
        return count
