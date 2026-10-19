"""
Group Model - User groups for permission management
"""

from models import db
from datetime import datetime
from utils.datetime_utils import utc_now, utc_isoformat


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
            'permissions': self.permissions or [],
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
