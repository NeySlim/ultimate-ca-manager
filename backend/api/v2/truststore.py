"""
TrustStore Management Routes v2.0
/api/v2/truststore/* - Manage trusted certificates
"""

from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response, error_response, created_response, no_content_response
from models import db
from models.truststore import TrustedCertificate
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.backends import default_backend
import hashlib
from datetime import datetime

bp = Blueprint('truststore_v2', __name__)


def parse_certificate(pem_data):
    """
    Parse certificate and extract details
    
    Returns dict with subject, issuer, fingerprints, etc.
    """
    try:
        cert = x509.load_pem_x509_certificate(pem_data.encode(), default_backend())
        
        # Extract subject and issuer
        subject = cert.subject.rfc4514_string()
        issuer = cert.issuer.rfc4514_string()
        
        # Calculate fingerprints
        cert_der = cert.public_bytes(serialization.Encoding.DER)
        fp_sha256 = hashlib.sha256(cert_der).hexdigest()
        fp_sha1 = hashlib.sha1(cert_der).hexdigest()
        
        return {
            'subject': subject,
            'issuer': issuer,
            'serial_number': format(cert.serial_number, 'X'),
            'not_before': cert.not_valid_before_utc,
            'not_after': cert.not_valid_after_utc,
            'fingerprint_sha256': fp_sha256,
            'fingerprint_sha1': fp_sha1,
        }
    except Exception as e:
        raise ValueError(f'Invalid certificate: {str(e)}')


@bp.route('/api/v2/truststore', methods=['GET'])
@require_auth()
def list_trusted_certificates():
    """
    List all trusted certificates
    
    Query params:
    - purpose: Filter by purpose
    - search: Search name, subject, fingerprint
    """
    purpose = request.args.get('purpose')
    search = request.args.get('search', '').strip()
    
    query = TrustedCertificate.query
    
    if purpose:
        query = query.filter_by(purpose=purpose)
    
    if search:
        search_pattern = f'%{search}%'
        query = query.filter(
            db.or_(
                TrustedCertificate.name.ilike(search_pattern),
                TrustedCertificate.subject.ilike(search_pattern),
                TrustedCertificate.fingerprint_sha256.ilike(search_pattern)
            )
        )
    
    certs = query.order_by(TrustedCertificate.added_at.desc()).all()
    
    return success_response(
        data=[cert.to_dict() for cert in certs]
    )


@bp.route('/api/v2/truststore', methods=['POST'])
@require_auth()
def add_trusted_certificate():
    """
    Add certificate to trust store
    
    POST /api/v2/truststore
    {
        "name": "DigiCert Global Root CA",
        "description": "DigiCert public root CA",
        "certificate_pem": "-----BEGIN CERTIFICATE-----...",
        "purpose": "root_ca",
        "notes": "Trusted for code signing"
    }
    """
    data = request.get_json()
    
    # Required fields
    if not data.get('name'):
        return error_response('Name is required', 400)
    if not data.get('certificate_pem'):
        return error_response('Certificate PEM is required', 400)
    
    # Parse certificate
    try:
        cert_details = parse_certificate(data['certificate_pem'])
    except ValueError as e:
        return error_response(str(e), 400)
    
    # Check if already exists (by fingerprint)
    existing = TrustedCertificate.query.filter_by(
        fingerprint_sha256=cert_details['fingerprint_sha256']
    ).first()
    
    if existing:
        return error_response('Certificate already in trust store', 409)
    
    # Create trusted certificate
    trusted_cert = TrustedCertificate(
        name=data['name'],
        description=data.get('description', ''),
        certificate_pem=data['certificate_pem'],
        fingerprint_sha256=cert_details['fingerprint_sha256'],
        fingerprint_sha1=cert_details['fingerprint_sha1'],
        subject=cert_details['subject'],
        issuer=cert_details['issuer'],
        serial_number=cert_details['serial_number'],
        not_before=cert_details['not_before'],
        not_after=cert_details['not_after'],
        purpose=data.get('purpose', 'custom'),
        added_by=g.current_user.username,
        notes=data.get('notes', '')
    )
    
    try:
        db.session.add(trusted_cert)
        db.session.commit()
        
        return created_response(
            data=trusted_cert.to_dict(),
            message=f'Certificate {trusted_cert.name} added to trust store'
        )
    except Exception as e:
        db.session.rollback()
        return error_response(f'Failed to add certificate: {str(e)}', 500)


@bp.route('/api/v2/truststore/<int:cert_id>', methods=['GET'])
@require_auth()
def get_trusted_certificate(cert_id):
    """Get single trusted certificate details"""
    cert = TrustedCertificate.query.get(cert_id)
    if not cert:
        return error_response('Certificate not found', 404)
    
    return success_response(data=cert.to_dict())


@bp.route('/api/v2/truststore/<int:cert_id>', methods=['DELETE'])
@require_auth()
def remove_trusted_certificate(cert_id):
    """
    Remove certificate from trust store
    
    DELETE /api/v2/truststore/{cert_id}
    """
    cert = TrustedCertificate.query.get(cert_id)
    if not cert:
        return error_response('Certificate not found', 404)
    
    cert_name = cert.name
    
    try:
        db.session.delete(cert)
        db.session.commit()
        
        return no_content_response(
            message=f'Certificate {cert_name} removed from trust store'
        )
    except Exception as e:
        db.session.rollback()
        return error_response(f'Failed to remove certificate: {str(e)}', 500)
