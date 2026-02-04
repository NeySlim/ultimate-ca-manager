"""
Certificate Policy Model - UCM Pro
Defines certificate policies and approval workflows for compliance.
"""
from datetime import datetime
from models import db
import json


class CertificatePolicy(db.Model):
    """
    Certificate Policy defines rules for certificate issuance.
    Enforces organizational compliance requirements.
    """
    __tablename__ = "certificate_policies"
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.Text)
    
    # Policy Type
    policy_type = db.Column(db.String(50), default='issuance')  # issuance, renewal, revocation
    
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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.String(80))
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    
    # Relationships
    ca = db.relationship('CA', backref='policies', lazy='joined')
    approval_group = db.relationship('Group', backref='approval_policies')
    
    def get_rules(self):
        """Parse rules JSON"""
        try:
            return json.loads(self.rules) if self.rules else {}
        except:
            return {}
    
    def set_rules(self, rules_dict):
        """Set rules from dict"""
        self.rules = json.dumps(rules_dict)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'policy_type': self.policy_type,
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
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'created_by': self.created_by,
        }


class ApprovalRequest(db.Model):
    """
    Tracks certificate approval requests for workflow compliance.
    """
    __tablename__ = "approval_requests"
    
    id = db.Column(db.Integer, primary_key=True)
    request_type = db.Column(db.String(50), nullable=False)  # certificate, csr, revocation
    
    # What needs approval (certificate ID, which can be a CSR or issued cert)
    certificate_id = db.Column(db.Integer, db.ForeignKey('certificates.id'), nullable=True)
    
    # Policy that triggered this
    policy_id = db.Column(db.Integer, db.ForeignKey('certificate_policies.id'), nullable=True)
    
    # Requester
    requester_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    requester_comment = db.Column(db.Text)
    
    # Status
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected, expired
    
    # Approvals received (JSON array)
    # Example: [{"user_id": 1, "username": "admin", "action": "approve", "comment": "OK", "timestamp": "..."}]
    approvals = db.Column(db.Text, default='[]')
    required_approvals = db.Column(db.Integer, default=1)
    
    # Timing
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)  # Auto-reject after this
    resolved_at = db.Column(db.DateTime)
    
    # Relationships
    policy = db.relationship('CertificatePolicy', backref='requests')
    requester = db.relationship('User', backref='approval_requests')
    
    def get_approvals(self):
        try:
            return json.loads(self.approvals) if self.approvals else []
        except:
            return []
    
    def add_approval(self, user_id, username, action, comment=None):
        """Add an approval/rejection"""
        approvals = self.get_approvals()
        approvals.append({
            'user_id': user_id,
            'username': username,
            'action': action,  # 'approve' or 'reject'
            'comment': comment,
            'timestamp': datetime.utcnow().isoformat()
        })
        self.approvals = json.dumps(approvals)
        
        # Check if enough approvals
        approve_count = sum(1 for a in approvals if a['action'] == 'approve')
        reject_count = sum(1 for a in approvals if a['action'] == 'reject')
        
        if approve_count >= self.required_approvals:
            self.status = 'approved'
            self.resolved_at = datetime.utcnow()
        elif reject_count > 0:  # Any rejection stops the request
            self.status = 'rejected'
            self.resolved_at = datetime.utcnow()
    
    def to_dict(self):
        return {
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
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
        }
