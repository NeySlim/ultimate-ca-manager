"""
Certificate Policy Model - UCM Pro
Defines certificate policies and approval workflows for compliance.
"""
from datetime import datetime
from models import db
import json
from utils.datetime_utils import utc_now, utc_isoformat

# Operations a policy can govern
OPERATIONS = ('issuance', 'renewal', 'revocation')


def legacy_operations(policy_type):
    """The operations a policy of the old single type governed (the backfill
    of migration 099, also applied to rows restored from older backups): a
    renewal or revocation type was never enforced."""
    if policy_type in (None, '', 'issuance'):
        return ['issuance']
    return []


class CertificatePolicy(db.Model):
    """
    Certificate Policy defines rules for certificate issuance.
    Enforces organizational compliance requirements.
    """
    __tablename__ = "certificate_policies"
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.Text)
    
    # Legacy single type, kept in step with ``operations`` for older clients
    policy_type = db.Column(db.String(50), default='issuance')
    # JSON list of the operations governed (OPERATIONS); NULL reads as the
    # legacy type did (see legacy_operations)
    operations = db.Column(db.Text)
    
    # Scope
    ca_id = db.Column(db.Integer, db.ForeignKey('certificate_authorities.id'), nullable=True)
    template_id = db.Column(db.Integer, db.ForeignKey('certificate_templates.id'), nullable=True)
    
    # Rules (JSON)
    # Example: {
    #   "max_validity_days": 397,
    #   "allowed_key_types": ["RSA-2048", "RSA-4096", "EC-P256"],
    #   "required_extensions": ["keyUsage", "extendedKeyUsage"],
    #   "forbidden_extensions": [],
    #   "san_restrictions": {
    #     "max_dns_names": 50,
    #     "dns_pattern": "*.company.com",
    #     "require_approval_for_external": true
    #   }
    # }
    rules = db.Column(db.Text, nullable=False, default='{}')
    
    # Approval Requirements
    requires_approval = db.Column(db.Boolean, default=False)
    approval_group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=True)
    min_approvers = db.Column(db.Integer, default=1)
    
    # Notifications
    notify_on_violation = db.Column(db.Boolean, default=True)
    notification_emails = db.Column(db.Text)  # JSON array
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    priority = db.Column(db.Integer, default=100)  # Lower = higher priority
    
    # Metadata
    created_at = db.Column(db.DateTime, default=utc_now)
    created_by = db.Column(db.String(80))
    updated_at = db.Column(db.DateTime, onupdate=utc_now)
    
    # Relationships
    ca = db.relationship('CA', backref='policies', lazy='joined')
    approval_group = db.relationship('Group', backref='approval_policies')
    
    def get_rules(self):
        """Parse rules JSON"""
        try:
            return json.loads(self.rules) if self.rules else {}
        except Exception:
            return {}
    
    def set_rules(self, rules_dict):
        """Set rules from dict"""
        self.rules = json.dumps(rules_dict)

    def get_operations(self):
        if self.operations is None:
            return legacy_operations(self.policy_type)
        try:
            ops = json.loads(self.operations)
        except (TypeError, ValueError):
            return []
        return [op for op in OPERATIONS if isinstance(ops, list) and op in ops]

    def set_operations(self, operations):
        ops = [op for op in OPERATIONS if op in operations]
        self.operations = json.dumps(ops)
        self.policy_type = ops[0] if ops else self.policy_type

    def applies_to(self, operation):
        return operation in self.get_operations()
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'policy_type': self.policy_type,
            'operations': self.get_operations(),
            'ca_id': self.ca_id,
            'ca_name': self.ca.common_name if self.ca else None,
            'template_id': self.template_id,
            'rules': self.get_rules(),
            'requires_approval': self.requires_approval,
            'approval_group_id': self.approval_group_id,
            'approval_group_name': self.approval_group.name if self.approval_group else None,
            'min_approvers': self.min_approvers,
            'notify_on_violation': self.notify_on_violation,
            'notification_emails': json.loads(self.notification_emails) if self.notification_emails else [],
            'is_active': self.is_active,
            'priority': self.priority,
            'created_at': utc_isoformat(self.created_at),
            'created_by': self.created_by,
        }


class ApprovalRequest(db.Model):
    """
    Tracks certificate approval requests for workflow compliance.
    """
    __tablename__ = "approval_requests"
    __table_args__ = (
        # The pending requests of a type are looked up on every direct
        # signing, renewal, revocation and deletion (migration 084)
        db.Index('ix_approval_requests_status_type', 'status', 'request_type'),
    )

    id = db.Column(db.Integer, primary_key=True)
    request_type = db.Column(db.String(50), nullable=False)  # certificate, csr, renewal, revocation, ca_revocation
    
    # What needs approval (certificate ID, which can be a CSR or issued cert)
    certificate_id = db.Column(db.Integer, db.ForeignKey('certificates.id'), nullable=True)
    
    # Stored request data for deferred issuance (JSON)
    request_data = db.Column(db.Text)
    
    # Policy that triggered this
    policy_id = db.Column(db.Integer, db.ForeignKey('certificate_policies.id'), nullable=True)
    
    # Requester
    # None for a request the renewal scheduler queued (migration 099)
    requester_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    requester_comment = db.Column(db.Text)
    
    # Status
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected, expired, cancelled
    
    # Approvals received (JSON array)
    # Example: [{"user_id": 1, "username": "admin", "action": "approve", "comment": "OK", "timestamp": "..."}]
    approvals = db.Column(db.Text, default='[]')
    required_approvals = db.Column(db.Integer, default=1)
    
    # Timing
    created_at = db.Column(db.DateTime, default=utc_now)
    expires_at = db.Column(db.DateTime)  # Auto-reject after this
    resolved_at = db.Column(db.DateTime)
    
    # Relationships
    policy = db.relationship('CertificatePolicy', backref='requests')
    requester = db.relationship('User', backref='approval_requests')
    
    def get_approvals(self):
        try:
            return json.loads(self.approvals) if self.approvals else []
        except Exception:
            return []
    
    def add_approval(self, user_id, username, action, comment=None):
        """Add an approval/rejection"""
        approvals = self.get_approvals()
        approvals.append({
            'user_id': user_id,
            'username': username,
            'action': action,  # 'approve' or 'reject'
            'comment': comment,
            'timestamp': utc_now().isoformat()
        })
        self.approvals = json.dumps(approvals)
        
        # Check if enough approvals
        approve_count = sum(1 for a in approvals if a['action'] == 'approve')
        reject_count = sum(1 for a in approvals if a['action'] == 'reject')
        
        if approve_count >= self.required_approvals:
            self.status = 'approved'
            self.resolved_at = utc_now()
        elif reject_count > 0:  # Any rejection stops the request
            self.status = 'rejected'
            self.resolved_at = utc_now()
    
    def to_dict(self):
        result = {
            'id': self.id,
            'request_type': self.request_type,
            'certificate_id': self.certificate_id,
            'policy_id': self.policy_id,
            'policy_name': self.policy.name if self.policy else None,
            'requester_id': self.requester_id,
            'requester_username': self.requester.username if self.requester else None,
            'requester_comment': self.requester_comment,
            'status': self.status,
            'approvals': self.get_approvals(),
            'required_approvals': self.required_approvals,
            'created_at': utc_isoformat(self.created_at),
            'expires_at': utc_isoformat(self.expires_at),
            'resolved_at': utc_isoformat(self.resolved_at),
        }
        # Include certificate request summary if available
        if self.request_data:
            try:
                rd = json.loads(self.request_data)
                result['request_summary'] = {
                    'cn': rd.get('cn'),
                    'ca_id': rd.get('ca_id'),
                    'cert_type': rd.get('cert_type'),
                    'validity_days': rd.get('validity_days'),
                    'csr_id': rd.get('csr_id'),
                    'certificate_id': rd.get('certificate_id'),
                    'extra_ekus': rd.get('extra_ekus') or [],
                    # Names the requester added to a CSR's own (#389)
                    'extra_san': [v for vs in rd['extra_san'].values() for v in vs]
                    if isinstance(rd.get('extra_san'), dict) else [],
                    # Revocations: what is revoked, why, from when
                    'serial_number': rd.get('serial_number'),
                    'target_ca_id': rd.get('target_ca_id'),
                    'reason': rd.get('reason'),
                    'invalidity_at': rd.get('invalidity_at'),
                    'trigger': rd.get('trigger'),
                }
                if self.requester is None and rd.get('requested_by'):
                    result['requester_username'] = rd['requested_by']
            except Exception:
                pass
        return result
