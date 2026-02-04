"""
Certificate Policy API - UCM Pro
Manages certificate policies and approval workflows.
"""
from flask import Blueprint, request
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db
from models.pro.policy import CertificatePolicy, ApprovalRequest
from datetime import datetime, timedelta
import json

bp = Blueprint('policies_pro', __name__)


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
        created_by=request.current_user.get('username') if hasattr(request, 'current_user') else None
    )
    
    if data.get('rules'):
        policy.set_rules(data['rules'])
    
    if data.get('notification_emails'):
        policy.notification_emails = json.dumps(data['notification_emails'])
    
    db.session.add(policy)
    db.session.commit()
    
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
    
    db.session.commit()
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
    
    db.session.delete(policy)
    db.session.commit()
    
    return success_response(message="Policy deleted")


@bp.route('/api/v2/policies/<int:policy_id>/toggle', methods=['POST'])
@require_auth(['write:policies'])
def toggle_policy(policy_id):
    """Enable/disable policy"""
    policy = CertificatePolicy.query.get_or_404(policy_id)
    policy.is_active = not policy.is_active
    db.session.commit()
    
    status = "enabled" if policy.is_active else "disabled"
    return success_response(data=policy.to_dict(), message=f"Policy {status}")


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
    """Approve a request"""
    approval = ApprovalRequest.query.get_or_404(request_id)
    
    if approval.status != 'pending':
        return error_response(f"Request is already {approval.status}", 400)
    
    data = request.get_json() or {}
    user = request.current_user if hasattr(request, 'current_user') else {}
    
    approval.add_approval(
        user_id=user.get('id'),
        username=user.get('username', 'system'),
        action='approve',
        comment=data.get('comment')
    )
    
    db.session.commit()
    
    return success_response(data=approval.to_dict(), message="Approval recorded")


@bp.route('/api/v2/approvals/<int:request_id>/reject', methods=['POST'])
@require_auth(['write:approvals'])
def reject_request(request_id):
    """Reject a request"""
    approval = ApprovalRequest.query.get_or_404(request_id)
    
    if approval.status != 'pending':
        return error_response(f"Request is already {approval.status}", 400)
    
    data = request.get_json() or {}
    user = request.current_user if hasattr(request, 'current_user') else {}
    
    if not data.get('comment'):
        return error_response("Rejection reason is required", 400)
    
    approval.add_approval(
        user_id=user.get('id'),
        username=user.get('username', 'system'),
        action='reject',
        comment=data.get('comment')
    )
    
    db.session.commit()
    
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
