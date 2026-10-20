"""
Group Model - User groups for permission management
"""

import json

from models import db
from datetime import datetime
from utils.datetime_utils import utc_now, utc_isoformat


# Seeded when no group exists. A group never grants the admin role, so there is no Administrators group.
DEFAULT_GROUPS = (
    {'name': 'Certificate Operators', 'description': 'Can manage certificates and CSRs',
     'permissions': ['read:certificates', 'write:certificates', 'read:csrs', 'write:csrs', 'read:cas']},
    {'name': 'Auditors', 'description': 'Read-only access to audit logs, certificates and CAs',
     'permissions': ['read:audit', 'read:certificates', 'read:cas']},
)


def seed_default_groups():
    """Create DEFAULT_GROUPS when no group exists; returns how many were created."""
    if Group.query.count():
        return 0
    for g in DEFAULT_GROUPS:
        db.session.add(Group(**{**g, 'permissions': list(g['permissions'])}))
    db.session.commit()
    return len(DEFAULT_GROUPS)


def permission_list(value):
    """Stored group permissions as a list; JSON text from an old backup is decoded."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
        if isinstance(value, str):
            return permission_list(value)
    return [p for p in value if isinstance(p, str)] if isinstance(value, list) else []


class Group(db.Model):
    """User group for organizing users and permissions"""
    __tablename__ = 'groups'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, default='')
    permissions = db.Column(db.JSON, default=list)  # List of permission strings
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    
    # Relationships
    members = db.relationship('GroupMember', backref='group', lazy='dynamic', cascade='all, delete-orphan')
    
    def to_dict(self, include_members=False):
        result = {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'permissions': permission_list(self.permissions),
            'member_count': self.members.count(),
            'created_at': utc_isoformat(self.created_at),
            'updated_at': utc_isoformat(self.updated_at)
        }
        if include_members:
            result['members'] = [m.to_dict() for m in self.members]
        return result


class GroupMember(db.Model):
    """Group membership linking users to groups"""
    __tablename__ = 'group_members'
    
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    # Never read: managing a group takes the global admin role. Kept for older backups.
    role = db.Column(db.String(20), default='member')
    joined_at = db.Column(db.DateTime, default=utc_now)
    
    # Unique constraint: user can only be in a group once
    __table_args__ = (db.UniqueConstraint('group_id', 'user_id'),)
    
    def to_dict(self):
        from models import User
        user = db.session.get(User, self.user_id)
        return {
            'id': self.id,
            'group_id': self.group_id,
            'user_id': self.user_id,
            'username': user.username if user else None,
            'email': user.email if user else None,
            'full_name': user.full_name if user else None,
            'joined_at': utc_isoformat(self.joined_at)
        }
