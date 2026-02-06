"""
Group Model - User groups for permission management
"""

from models import db
from datetime import datetime


class Group(db.Model):
    """User group for organizing users and permissions"""
    __tablename__ = 'groups'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, default='')
    permissions = db.Column(db.JSON, default=list)  # List of permission strings
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    members = db.relationship('GroupMember', backref='group', lazy='dynamic', cascade='all, delete-orphan')
    
    def to_dict(self, include_members=False):
        result = {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'permissions': self.permissions or [],
            'member_count': self.members.count(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
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
    role = db.Column(db.String(20), default='member')  # member, admin
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Unique constraint: user can only be in a group once
    __table_args__ = (db.UniqueConstraint('group_id', 'user_id'),)
    
    def to_dict(self):
        from models import User
        user = User.query.get(self.user_id)
        return {
            'id': self.id,
            'group_id': self.group_id,
            'user_id': self.user_id,
            'username': user.username if user else None,
            'email': user.email if user else None,
            'full_name': user.full_name if user else None,
            'role': self.role,
            'joined_at': self.joined_at.isoformat() if self.joined_at else None
        }
