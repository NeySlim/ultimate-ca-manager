"""
Certificate Policy API - UCM
Manages certificate policies and approval workflows.
"""
from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit
from models import db, CA, Certificate
from models.policy import CertificatePolicy, ApprovalRequest
from datetime import datetime, timedelta
import json
import logging
import base64
import uuid
from security.encryption import decrypt_private_key
from services.audit_service import AuditService

logger = logging.getLogger(__name__)

bp = Blueprint('policies_pro', __name__)


def _issue_approved_certificate(approval):
    """Issue a certificate from an approved request's stored data.
    
    Re-invokes the certificate creation logic using the original request data.
    Returns the certificate dict on success, raises on failure.
    """
    from services.policy_service import PolicyEvaluationService
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa, ec
    from cryptography.hazmat.backends import default_backend
    from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID, ExtensionOID
    from utils.datetime_utils import utc_now

    data = PolicyEvaluationService.get_request_data(approval)
    if not data:
        raise ValueError("No request data stored in approval")
    
    ca = CA.query.get(data['ca_id'])
    if not ca:
        raise ValueError(f"CA {data['ca_id']} not found")
    if not ca.prv:
        raise ValueError("CA private key not available")
    
    # Load CA cert and key
    ca_cert_pem = base64.b64decode(ca.crt)
    ca_cert = x509.load_pem_x509_certificate(ca_cert_pem, default_backend())
    ca_key_pem = base64.b64decode(decrypt_private_key(ca.prv))
    ca_key = serialization.load_pem_private_key(ca_key_pem, password=None, backend=default_backend())
    
    # Generate key pair
    key_type = data.get('key_type', 'RSA')
    key_size = data.get('key_size', '2048')
    
    if key_type.upper() in ('EC', 'ECDSA'):
        curve_map = {
            '256': ec.SECP256R1(), 'secp256r1': ec.SECP256R1(),
            '384': ec.SECP384R1(), 'secp384r1': ec.SECP384R1(),
            '521': ec.SECP521R1(), 'secp521r1': ec.SECP521R1(),
        }
        curve = curve_map.get(str(key_size), ec.SECP256R1())
        new_key = ec.generate_private_key(curve, default_backend())
    else:
        new_key = rsa.generate_private_key(65537, int(key_size), default_backend())
    
    # Build subject
    subject_attrs = [x509.NameAttribute(NameOID.COMMON_NAME, data['cn'])]
    for field, oid in [('organization', NameOID.ORGANIZATION_NAME), ('organizational_unit', NameOID.ORGANIZATIONAL_UNIT_NAME),
                       ('country', NameOID.COUNTRY_NAME), ('state', NameOID.STATE_OR_PROVINCE_NAME), ('locality', NameOID.LOCALITY_NAME)]:
        if data.get(field):
            val = data[field].upper() if field == 'country' else data[field]
            subject_attrs.append(x509.NameAttribute(oid, val))
    
    subject = x509.Name(subject_attrs)
    validity_days = data.get('validity_days', 365)
    now = utc_now()
    
    builder = x509.CertificateBuilder()
    builder = builder.subject_name(subject)
    builder = builder.issuer_name(ca_cert.subject)
    builder = builder.public_key(new_key.public_key())
    builder = builder.serial_number(x509.random_serial_number())
    builder = builder.not_valid_before(now)
    builder = builder.not_valid_after(now + timedelta(days=validity_days))
    
    builder = builder.add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
    
    # Key Usage
    cert_type = data.get('cert_type', 'server')
    if cert_type == 'client':
        builder = builder.add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=False, content_commitment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
        builder = builder.add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
    else:
        builder = builder.add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=True, content_commitment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
        ekus = [ExtendedKeyUsageOID.SERVER_AUTH]
        if cert_type == 'combined':
            ekus.append(ExtendedKeyUsageOID.CLIENT_AUTH)
        builder = builder.add_extension(x509.ExtendedKeyUsage(ekus), critical=False)
    
    # SANs
    from ipaddress import ip_address
    san_list = []
    for dns in data.get('san_dns', []):
        san_list.append(x509.DNSName(dns))
    for ip in data.get('san_ip', []):
        san_list.append(x509.IPAddress(ip_address(ip)))
    for email in data.get('san_email', []):
        san_list.append(x509.RFC822Name(email))
    
    cn = data['cn']
    if cert_type in ['server', 'combined'] and '.' in cn and cn not in data.get('san_dns', []):
        san_list.insert(0, x509.DNSName(cn))
    
    if san_list:
        builder = builder.add_extension(x509.SubjectAlternativeName(san_list), critical=False)
    
    # SKI/AKI
    builder = builder.add_extension(x509.SubjectKeyIdentifier.from_public_key(new_key.public_key()), critical=False)
    builder = builder.add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
    
    # CDP/OCSP/CPS
    if ca.cdp_enabled:
        cdp_urls = [url.replace('{ca_refid}', ca.refid or '') for url in ca.get_cdp_urls()]
        if cdp_urls:
            builder = builder.add_extension(x509.CRLDistributionPoints([
                x509.DistributionPoint(full_name=[x509.UniformResourceIdentifier(url)], relative_name=None, reasons=None, crl_issuer=None)
                for url in cdp_urls
            ]), critical=False)
    aia_descs = []
    if ca.ocsp_enabled:
        for uri in ca.get_ocsp_urls():
            aia_descs.append(x509.AccessDescription(x509.oid.AuthorityInformationAccessOID.OCSP, x509.UniformResourceIdentifier(uri)))
    if ca.aia_ca_issuers_enabled:
        for url in ca.get_aia_urls():
            aia_descs.append(x509.AccessDescription(x509.oid.AuthorityInformationAccessOID.CA_ISSUERS, x509.UniformResourceIdentifier(url.replace('{ca_refid}', ca.refid or ''))))
    if aia_descs:
        builder = builder.add_extension(x509.AuthorityInformationAccess(aia_descs), critical=False)
    if ca.cps_enabled and ca.cps_uri:
        builder = builder.add_extension(x509.CertificatePolicies([
            x509.PolicyInformation(policy_identifier=x509.ObjectIdentifier(ca.cps_oid or '2.5.29.32.0'), policy_qualifiers=[ca.cps_uri])
        ]), critical=False)
    
    # Sign
    new_cert = builder.sign(ca_key, hashes.SHA256(), default_backend())
    cert_pem = new_cert.public_bytes(serialization.Encoding.PEM).decode('utf-8')
    key_pem = new_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()).decode('utf-8')
    
    # Extract SKI/AKI
    cert_ski, cert_aki = None, None
    try:
        ext = new_cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_KEY_IDENTIFIER)
        cert_ski = ext.value.key_identifier.hex(':').upper()
    except Exception:
        pass
    try:
        ext = new_cert.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_KEY_IDENTIFIER)
        if ext.value.key_identifier:
            cert_aki = ext.value.key_identifier.hex(':').upper()
    except Exception:
        pass
    
    # Save to DB
    db_cert = Certificate(
        refid=str(uuid.uuid4())[:8],
        descr=data.get('description', data['cn']),
        caref=ca.refid,
        crt=base64.b64encode(cert_pem.encode()).decode(),
        prv=base64.b64encode(key_pem.encode()).decode(),
        cert_type=cert_type,
        subject=new_cert.subject.rfc4514_string(),
        issuer=new_cert.issuer.rfc4514_string(),
        serial_number=format(new_cert.serial_number, 'x'),
        aki=cert_aki,
        ski=cert_ski,
        valid_from=now,
        valid_to=now + timedelta(days=validity_days),
        san_dns=json.dumps(data.get('san_dns', [])),
        san_ip=json.dumps(data.get('san_ip', [])),
        san_email=json.dumps(data.get('san_email', [])),
        source='approval',
        created_by=approval.requester.username if approval.requester else 'system'
    )
    db.session.add(db_cert)
    
    # Link approval to issued cert
    approval.certificate_id = db_cert.id
    ok, _err = safe_commit(logger, "Failed to link approval to certificate")
    if not ok:
        return _err
    
    logger.info(f"Certificate CN={data['cn']} issued via approval #{approval.id}")
    
    return {
        'id': db_cert.id,
        'cn': data['cn'],
        'serial_number': db_cert.serial_number,
        'valid_from': now.isoformat(),
        'valid_to': (now + timedelta(days=validity_days)).isoformat(),
    }


# ============ Policy Management ============

@bp.route('/api/v2/policies', methods=['GET'])
@require_auth(['read:policies'])
def list_policies():
    """List all certificate policies"""
    policies = CertificatePolicy.query.order_by(CertificatePolicy.priority).all()
    return success_response(data=[p.to_dict() for p in policies])


@bp.route('/api/v2/policies/<int:policy_id>', methods=['GET'])
@require_auth(['read:policies'])
def get_policy(policy_id):
    """Get policy details"""
    policy = CertificatePolicy.query.get_or_404(policy_id)
    return success_response(data=policy.to_dict())


@bp.route('/api/v2/policies', methods=['POST'])
@require_auth(['write:policies'])
def create_policy():
    """Create new certificate policy"""
    data = request.get_json()
    
    if not data.get('name'):
        return error_response("Policy name is required", 400)
    
    # Check uniqueness
    if CertificatePolicy.query.filter_by(name=data['name']).first():
        return error_response("Policy name already exists", 400)
    
    policy = CertificatePolicy(
        name=data['name'],
        description=data.get('description'),
        policy_type=data.get('policy_type', 'issuance'),
        ca_id=data.get('ca_id'),
        template_id=data.get('template_id'),
        requires_approval=data.get('requires_approval', False),
        approval_group_id=data.get('approval_group_id'),
        min_approvers=data.get('min_approvers', 1),
        notify_on_violation=data.get('notify_on_violation', True),
        is_active=data.get('is_active', True),
        priority=data.get('priority', 100),
        created_by=g.current_user.username if hasattr(g, 'current_user') and g.current_user else None
    )
    
    if data.get('rules'):
        policy.set_rules(data['rules'])
    
    if data.get('notification_emails'):
        policy.notification_emails = json.dumps(data['notification_emails'])
    
    db.session.add(policy)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to create policy: {e}")
        return error_response('Failed to create policy', 500)
    
    AuditService.log_action(
        action='create',
        resource_type='policy',
        resource_id=policy.id,
        resource_name=policy.name,
        details=f'Created policy: {policy.name}',
        success=True
    )
    
    return success_response(data=policy.to_dict(), message="Policy created")


@bp.route('/api/v2/policies/<int:policy_id>', methods=['PUT'])
@require_auth(['write:policies'])
def update_policy(policy_id):
    """Update certificate policy"""
    policy = CertificatePolicy.query.get_or_404(policy_id)
    data = request.get_json()
    
    # Update fields
    if 'name' in data:
        existing = CertificatePolicy.query.filter_by(name=data['name']).first()
        if existing and existing.id != policy_id:
            return error_response("Policy name already exists", 400)
        policy.name = data['name']
    
    if 'description' in data:
        policy.description = data['description']
    if 'policy_type' in data:
        policy.policy_type = data['policy_type']
    if 'ca_id' in data:
        policy.ca_id = data['ca_id']
    if 'template_id' in data:
        policy.template_id = data['template_id']
    if 'requires_approval' in data:
        policy.requires_approval = data['requires_approval']
    if 'approval_group_id' in data:
        policy.approval_group_id = data['approval_group_id']
    if 'min_approvers' in data:
        policy.min_approvers = data['min_approvers']
    if 'notify_on_violation' in data:
        policy.notify_on_violation = data['notify_on_violation']
    if 'is_active' in data:
        policy.is_active = data['is_active']
    if 'priority' in data:
        policy.priority = data['priority']
    if 'rules' in data:
        policy.set_rules(data['rules'])
    if 'notification_emails' in data:
        policy.notification_emails = json.dumps(data['notification_emails'])
    
    ok, _err = safe_commit(logger, "Failed to update policy")
    if not ok:
        return _err
    
    AuditService.log_action(
        action='update',
        resource_type='policy',
        resource_id=policy.id,
        resource_name=policy.name,
        details=f'Updated policy: {policy.name}',
        success=True
    )
    
    return success_response(data=policy.to_dict(), message="Policy updated")


@bp.route('/api/v2/policies/<int:policy_id>', methods=['DELETE'])
@require_auth(['delete:policies'])
def delete_policy(policy_id):
    """Delete certificate policy"""
    policy = CertificatePolicy.query.get_or_404(policy_id)
    
    # Check for pending requests
    pending = ApprovalRequest.query.filter_by(
        policy_id=policy_id,
        status='pending'
    ).count()
    
    if pending > 0:
        return error_response(f"Cannot delete policy with {pending} pending approval requests", 400)
    
    try:
        # Clean up completed/rejected approval requests
        ApprovalRequest.query.filter_by(policy_id=policy_id).delete()
        
        policy_name = policy.name
        db.session.delete(policy)
        db.session.commit()
        
        AuditService.log_action(
            action='delete',
            resource_type='policy',
            resource_id=policy_id,
            resource_name=policy_name,
            details=f'Deleted policy: {policy_name}',
            success=True
        )
        
        return success_response(message="Policy deleted")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete policy {policy_id}: {e}")
        return error_response('Failed to delete policy', 500)


@bp.route('/api/v2/policies/<int:policy_id>/toggle', methods=['POST'])
@require_auth(['write:policies'])
def toggle_policy(policy_id):
    """Enable/disable policy"""
    policy = CertificatePolicy.query.get_or_404(policy_id)
    policy.is_active = not policy.is_active
    try:
        db.session.commit()
        status = "enabled" if policy.is_active else "disabled"
        return success_response(data=policy.to_dict(), message=f"Policy {status}")
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to toggle policy {policy_id}: {e}")
        return error_response('Failed to update policy', 500)


# ============ Approval Requests ============

@bp.route('/api/v2/approvals', methods=['GET'])
@require_auth(['read:approvals'])
def list_approvals():
    """List approval requests"""
    status = request.args.get('status', 'pending')
    
    query = ApprovalRequest.query
    if status != 'all':
        query = query.filter_by(status=status)
    
    requests = query.order_by(ApprovalRequest.created_at.desc()).all()
    return success_response(data=[r.to_dict() for r in requests])


@bp.route('/api/v2/approvals/<int:request_id>', methods=['GET'])
@require_auth(['read:approvals'])
def get_approval(request_id):
    """Get approval request details"""
    approval = ApprovalRequest.query.get_or_404(request_id)
    return success_response(data=approval.to_dict())


@bp.route('/api/v2/approvals/<int:request_id>/approve', methods=['POST'])
@require_auth(['write:approvals'])
def approve_request(request_id):
    """Approve a request — triggers certificate issuance if fully approved"""
    approval = ApprovalRequest.query.get_or_404(request_id)
    
    if approval.status != 'pending':
        return error_response(f"Request is already {approval.status}", 400)
    
    data = request.get_json() or {}
    user = g.current_user if hasattr(g, 'current_user') else None
    user_id = getattr(user, 'id', None)
    username = getattr(user, 'username', None) or 'system'

    # Prevent self-approval
    if user_id and approval.requester_id == user_id:
        return error_response("Cannot approve your own request", 403)

    approval.add_approval(
        user_id=user_id,
        username=username,
        action='approve',
        comment=data.get('comment')
    )
    
    ok, _err = safe_commit(logger, "Failed to approve request")
    if not ok:
        return _err
    
    result = approval.to_dict()
    
    # If fully approved and has stored request data, issue the certificate
    if approval.status == 'approved' and approval.request_data:
        try:
            cert_data = _issue_approved_certificate(approval)
            if cert_data:
                result['certificate'] = cert_data
                result['certificate_issued'] = True
                logger.info(f"Certificate issued for approval #{approval.id}")
        except Exception as e:
            logger.error(f"Failed to issue certificate for approval #{approval.id}: {e}")
            result['certificate_issued'] = False
            result['issue_error'] = 'Certificate issuance failed. Check server logs.'
    
    return success_response(data=result, message="Approval recorded")


@bp.route('/api/v2/approvals/<int:request_id>/reject', methods=['POST'])
@require_auth(['write:approvals'])
def reject_request(request_id):
    """Reject a request"""
    approval = ApprovalRequest.query.get_or_404(request_id)
    
    if approval.status != 'pending':
        return error_response(f"Request is already {approval.status}", 400)
    
    data = request.get_json() or {}
    user = g.current_user if hasattr(g, 'current_user') else None
    user_id = getattr(user, 'id', None)
    username = getattr(user, 'username', None) or 'system'

    if not data.get('comment'):
        return error_response("Rejection reason is required", 400)

    approval.add_approval(
        user_id=user_id,
        username=username,
        action='reject',
        comment=data.get('comment')
    )
    
    ok, _err = safe_commit(logger, "Failed to reject request")
    if not ok:
        return _err
    
    return success_response(data=approval.to_dict(), message="Request rejected")


@bp.route('/api/v2/approvals/stats', methods=['GET'])
@require_auth(['read:approvals'])
def approval_stats():
    """Get approval statistics"""
    pending = ApprovalRequest.query.filter_by(status='pending').count()
    approved = ApprovalRequest.query.filter_by(status='approved').count()
    rejected = ApprovalRequest.query.filter_by(status='rejected').count()
    
    return success_response(data={
        'pending': pending,
        'approved': approved,
        'rejected': rejected,
        'total': pending + approved + rejected
    })
