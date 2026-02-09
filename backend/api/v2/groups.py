"""
Groups API v2.0
/api/v2/groups/* - User group management
"""

from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response, error_response, created_response, no_content_response
from models import db, User
from models.group import Group, GroupMember
from services.audit_service import AuditService

bp = Blueprint('groups_v2', __name__)

# Valid permissions for groups
VALID_GROUP_PERMISSIONS = [
    'read:cas', 'write:cas', 'delete:cas',
    'read:certs', 'write:certs', 'delete:certs',
    'read:csrs', 'write:csrs', 'delete:csrs',
    'read:templates', 'write:templates',
    'read:users', 'write:users',
    'read:groups', 'write:groups', 'delete:groups',
    'read:audit', 'export:audit',
    'read:settings', 'write:settings',
]


def validate_permissions(permissions):
    """Validate permissions list"""
    if not isinstance(permissions, list):
        return False, "permissions must be an array"
    if len(permissions) > 50:
        return False, "Too many permissions (max 50)"
    invalid = [p for p in permissions if p not in VALID_GROUP_PERMISSIONS]
    if invalid:
        return False, f"Invalid permissions: {invalid}"
    return True, None


@bp.route('/api/v2/groups', methods=['GET'])
@require_auth(['read:groups'])
def list_groups():
    """
    List all groups
    
    GET /api/v2/groups
    Query params:
    - search: Search by name/description
    """
    search = request.args.get('search', '').strip()
    
    query = Group.query
    
    if search:
        search_pattern = f'%{search}%'
        query = query.filter(
            db.or_(
                Group.name.ilike(search_pattern),
                Group.description.ilike(search_pattern)
            )
        )
    
    groups = query.order_by(Group.name).all()
    return success_response(data=[g.to_dict() for g in groups])


@bp.route('/api/v2/groups', methods=['POST'])
@require_auth(['write:groups'])
def create_group():
    """
    Create a new group
    
    POST /api/v2/groups
    {
        "name": "Certificate Operators",
        "description": "Team responsible for certificate management",
        "permissions": ["read:certs", "write:certs"]
    }
    """
    # Only admins can create groups
    if g.current_user.role != 'admin':
        return error_response('Insufficient permissions', 403)
    
    data = request.get_json()
    
    if not data.get('name'):
        return error_response("Group name is required", 400)
    
    if len(data['name']) > 100:
        return error_response("Group name too long (max 100 chars)", 400)
    
    if Group.query.filter_by(name=data['name']).first():
        return error_response("Group already exists", 409)
    
    # Validate permissions if provided
    permissions = data.get('permissions', [])
    if permissions:
        valid, error = validate_permissions(permissions)
        if not valid:
            return error_response(error, 400)
    
    group = Group(
        name=data['name'],
        description=data.get('description', '')[:500],
        permissions=permissions
    )
    
    try:
        db.session.add(group)
        db.session.commit()
        AuditService.log_action(
            action='group_create',
            resource_type='group',
            resource_id=str(group.id),
            resource_name=group.name,
            details=f'Created group: {group.name}',
            success=True
        )
        return created_response(data=group.to_dict(), message="Group created")
    except Exception as e:
        db.session.rollback()
        return error_response('Failed to create group', 500)


@bp.route('/api/v2/groups/<int:group_id>', methods=['GET'])
@require_auth(['read:groups'])
def get_group(group_id):
    """Get group details with members"""
    group = Group.query.get(group_id)
    if not group:
        return error_response('Group not found', 404)
    return success_response(data=group.to_dict(include_members=True))


@bp.route('/api/v2/groups/<int:group_id>', methods=['PUT'])
@require_auth(['write:groups'])
def update_group(group_id):
    """Update a group"""
    if g.current_user.role != 'admin':
        return error_response('Insufficient permissions', 403)
    
    group = Group.query.get(group_id)
    if not group:
        return error_response('Group not found', 404)
    
    data = request.get_json()
    
    if 'name' in data:
        if len(data['name']) > 100:
            return error_response("Group name too long (max 100 chars)", 400)
        existing = Group.query.filter_by(name=data['name']).first()
        if existing and existing.id != group_id:
            return error_response("Group name already exists", 409)
        group.name = data['name']
    
    if 'description' in data:
        group.description = data['description'][:500]
    
    if 'permissions' in data:
        valid, error = validate_permissions(data['permissions'])
        if not valid:
            return error_response(error, 400)
        group.permissions = data['permissions']
    
    try:
        db.session.commit()
        AuditService.log_action(
            action='group_update',
            resource_type='group',
            resource_id=str(group_id),
            resource_name=group.name,
            details=f'Updated group: {group.name}',
            success=True
        )
        return success_response(data=group.to_dict(), message="Group updated")
    except Exception as e:
        db.session.rollback()
        return error_response('Failed to update group', 500)


@bp.route('/api/v2/groups/<int:group_id>', methods=['DELETE'])
@require_auth(['delete:groups'])
def delete_group(group_id):
    """Delete a group"""
    if g.current_user.role != 'admin':
        return error_response('Insufficient permissions', 403)
    
    group = Group.query.get(group_id)
    if not group:
        return error_response('Group not found', 404)
    
    group_name = group.name
    try:
        db.session.delete(group)
        db.session.commit()
        AuditService.log_action(
            action='group_delete',
            resource_type='group',
            resource_id=str(group_id),
            resource_name=group_name,
            details=f'Deleted group: {group_name}',
            success=True
        )
        return no_content_response(message="Group deleted")
    except Exception as e:
        db.session.rollback()
        return error_response('Failed to delete group', 500)


@bp.route('/api/v2/groups/<int:group_id>/members', methods=['GET'])
@require_auth(['read:groups'])
def list_group_members(group_id):
    """List members of a group"""
    group = Group.query.get(group_id)
    if not group:
        return error_response('Group not found', 404)
    return success_response(data=[m.to_dict() for m in group.members])


@bp.route('/api/v2/groups/<int:group_id>/members', methods=['POST'])
@require_auth(['write:groups'])
def add_group_member(group_id):
    """Add a user to a group"""
    if g.current_user.role != 'admin':
        return error_response('Insufficient permissions', 403)
    
    group = Group.query.get(group_id)
    if not group:
        return error_response('Group not found', 404)
    
    data = request.get_json()
    user_id = data.get('user_id')
    
    if not user_id:
        return error_response("user_id is required", 400)
    
    user = User.query.get(user_id)
    if not user:
        return error_response(f"User not found", 404)
    
    existing = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()
    if existing:
        return error_response("User is already a member", 409)
    
    role = data.get('role', 'member')
    if role not in ['member', 'admin']:
        return error_response("Invalid role. Must be 'member' or 'admin'", 400)
    
    member = GroupMember(group_id=group_id, user_id=user_id, role=role)
    
    try:
        db.session.add(member)
        db.session.commit()
        AuditService.log_action(
            action='group_member_add',
            resource_type='group',
            resource_id=str(group_id),
            resource_name=group.name,
            details=f'Added user {user.username} to group {group.name}',
            success=True
        )
        return created_response(data=member.to_dict(), message="Member added")
    except Exception as e:
        db.session.rollback()
        return error_response('Failed to add member', 500)


@bp.route('/api/v2/groups/<int:group_id>/members/<int:user_id>', methods=['DELETE'])
@require_auth(['write:groups'])
def remove_group_member(group_id, user_id):
    """Remove a user from a group"""
    if g.current_user.role != 'admin':
        return error_response('Insufficient permissions', 403)
    
    member = GroupMember.query.filter_by(group_id=group_id, user_id=user_id).first()
    if not member:
        return error_response('Member not found', 404)
    
    group = Group.query.get(group_id)
    try:
        db.session.delete(member)
        db.session.commit()
        AuditService.log_action(
            action='group_member_remove',
            resource_type='group',
            resource_id=str(group_id),
            resource_name=group.name if group else str(group_id),
            details=f'Removed user {user_id} from group {group_id}',
            success=True
        )
        return no_content_response(message="Member removed")
    except Exception as e:
        db.session.rollback()
        return error_response('Failed to remove member', 500)


@bp.route('/api/v2/groups/stats', methods=['GET'])
@require_auth(['read:groups'])
def get_groups_stats():
    """Get groups statistics"""
    total_groups = Group.query.count()
    total_members = GroupMember.query.count()
    
    return success_response(data={
        'total_groups': total_groups,
        'total_memberships': total_members
    })
