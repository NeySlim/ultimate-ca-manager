"""
Custom Role Model - UCM Pro
"""

from models import db
from datetime import datetime
from utils.datetime_utils import utc_now, utc_isoformat

class CustomRole(db.Model):
    """Custom role for fine-grained RBAC"""
    __tablename__ = 'pro_custom_roles'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, default='')
    permissions = db.Column(db.JSON, default=list)  # List of permission strings
    inherits_from = db.Column(db.Integer, db.ForeignKey('pro_custom_roles.id'), nullable=True)
    is_system = db.Column(db.Boolean, default=False)  # Built-in roles can't be deleted
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    
    # Self-referential relationship for inheritance
    parent = db.relationship('CustomRole', remote_side=[id], backref='children')
    
    def get_all_permissions(self):
        """What the role grants, inherited permissions included (cycle-safe)."""
        from auth.permissions import custom_role_permissions
        return custom_role_permissions(self)
    
    def to_dict(self):
        from models import User
        try:
            user_count = User.query.filter_by(custom_role_id=self.id).count()
        except Exception:
            user_count = 0
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'permissions': self.permissions or [],
            'all_permissions': self.get_all_permissions(),
            'inherits_from': self.inherits_from,
            'parent_name': self.parent.name if self.parent else None,
            'is_system': self.is_system,
            'user_count': user_count,
            'created_at': utc_isoformat(self.created_at),
            'updated_at': utc_isoformat(self.updated_at)
        }


class RolePermission(db.Model):
    """Permission assignment to role (for complex scenarios)"""
    __tablename__ = 'pro_role_permissions'
    
    id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey('pro_custom_roles.id'), nullable=False)
    permission = db.Column(db.String(100), nullable=False)
    resource_type = db.Column(db.String(50), nullable=True)  # e.g., 'ca', 'cert'
    resource_id = db.Column(db.Integer, nullable=True)  # Specific resource ID
    
    # Unique constraint
    __table_args__ = (db.UniqueConstraint('role_id', 'permission', 'resource_type', 'resource_id'),)
    
    def to_dict(self):
        return {
            'id': self.id,
            'role_id': self.role_id,
            'permission': self.permission,
            'resource_type': self.resource_type,
            'resource_id': self.resource_id
        }
