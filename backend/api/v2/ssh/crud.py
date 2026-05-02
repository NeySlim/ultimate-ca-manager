"""
SSH CA CRUD routes — list, get, import, create, update, delete.
"""

from flask import request, g

from auth.unified import require_auth
from utils.response import success_response, error_response, created_response, no_content_response
from services.ssh_ca_service import SSHCAService
from services.audit_service import AuditService
from models.ssh import SSHCertificateAuthority

from .helpers import bp, logger


@bp.route('/api/v2/ssh/cas', methods=['GET'])
@require_auth(['read:ssh'])
def list_ssh_cas():
    """List all SSH CAs with optional filtering."""
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(max(1, request.args.get('per_page', 20, type=int)), 100)
    search = request.args.get('search', '').strip()
    ca_types = request.args.getlist('type')

    query = SSHCertificateAuthority.query

    if ca_types:
        valid = [t for t in ca_types if t in SSHCertificateAuthority.VALID_CA_TYPES]
        if valid:
            query = query.filter(SSHCertificateAuthority.ca_type.in_(valid))

    if search:
        safe = search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        query = query.filter(
            SSHCertificateAuthority.descr.ilike(f'%{safe}%', escape='\\')
        )

    query = query.order_by(SSHCertificateAuthority.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return success_response(
        data=[ca.to_dict() for ca in pagination.items],
        meta={
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'total_pages': (pagination.total + per_page - 1) // per_page
        }
    )


@bp.route('/api/v2/ssh/cas/<int:ca_id>', methods=['GET'])
@require_auth(['read:ssh'])
def get_ssh_ca(ca_id):
    """Get SSH CA details."""
    ca = SSHCertificateAuthority.query.get(ca_id)
    if not ca:
        return error_response('SSH CA not found', 404)

    return success_response(data=ca.to_dict())


@bp.route('/api/v2/ssh/cas/import', methods=['POST'])
@require_auth(['write:ssh'])
def import_ssh_ca():
    """Import an existing SSH CA from a private key."""
    try:
        data = request.json or {}

        private_key = (data.get('private_key') or '').strip()
        if not private_key:
            return error_response('Private key is required', 400)
        if len(private_key) > 16384:
            return error_response('Private key data too large', 400)

        descr = (data.get('descr') or data.get('name') or '').strip()[:255]
        if not descr:
            return error_response('Description is required', 400)

        ca_type = (data.get('ca_type') or 'user').strip().lower()
        if ca_type not in ('user', 'host'):
            return error_response('Invalid CA type. Must be "user" or "host".', 400)
        username = g.current_user.username if hasattr(g, 'current_user') else 'system'

        ca = SSHCAService.import_ca(
            descr=descr,
            ca_type=ca_type,
            private_key_pem=private_key,
            username=username,
            default_ttl=data.get('default_ttl'),
            max_ttl=data.get('max_ttl', 0),
            comment=data.get('comment'),
            owner_group_id=data.get('owner_group_id'),
        )

        AuditService.log_action(
            action='ssh_ca_imported',
            resource_type='ssh_ca',
            resource_id=str(ca.id),
            resource_name=ca.descr,
            details=f'SSH CA "{ca.descr}" imported ({ca_type}, {ca.key_type})',
            success=True,
            username=username,
        )

        try:
            from websocket.emitters import on_ssh_ca_created
            on_ssh_ca_created(ca.id, ca.descr, ca_type, username)
        except Exception:
            pass

        return created_response(
            data=ca.to_dict(),
            message='SSH CA imported successfully'
        )

    except ValueError as e:
        AuditService.log_action(
            action='ssh_ca_import_failed',
            resource_type='ssh_ca',
            details=str(e)[:200],
            success=False,
            username=g.current_user.username if hasattr(g, 'current_user') else 'system',
        )
        return error_response(str(e), 400)
    except Exception as e:
        logger.error(f"Failed to import SSH CA: {e}")
        AuditService.log_action(
            action='ssh_ca_import_failed',
            resource_type='ssh_ca',
            details='Internal error during SSH CA import',
            success=False,
            username=g.current_user.username if hasattr(g, 'current_user') else 'system',
        )
        return error_response('Failed to import SSH CA', 500)


@bp.route('/api/v2/ssh/cas', methods=['POST'])
@require_auth(['write:ssh'])
def create_ssh_ca():
    """Create a new SSH CA."""
    try:
        data = request.json or {}

        descr = (data.get('descr') or data.get('name') or '').strip()
        if not descr:
            return error_response('Description is required', 400)

        ca_type = (data.get('ca_type') or 'user').strip().lower()
        key_type = (data.get('key_type') or 'ed25519').strip().lower()

        username = g.current_user.username if hasattr(g, 'current_user') else 'system'

        ca = SSHCAService.create_ca(
            descr=descr,
            ca_type=ca_type,
            key_type=key_type,
            username=username,
            default_ttl=data.get('default_ttl'),
            max_ttl=data.get('max_ttl', 0),
            default_extensions=data.get('default_extensions'),
            allowed_principals=data.get('allowed_principals'),
            comment=data.get('comment'),
            owner_group_id=data.get('owner_group_id'),
        )

        AuditService.log_action(
            action='ssh_ca_created',
            resource_type='ssh_ca',
            resource_id=str(ca.id),
            resource_name=ca.descr,
            details=f'SSH CA "{ca.descr}" created ({ca_type}, {key_type})',
            success=True,
            username=username,
        )

        try:
            from websocket.emitters import on_ssh_ca_created
            on_ssh_ca_created(ca.id, ca.descr, ca_type, username)
        except Exception:
            pass

        return created_response(
            data=ca.to_dict(),
            message='SSH CA created successfully'
        )

    except ValueError as e:
        return error_response(str(e), 400)
    except Exception as e:
        logger.error(f"Failed to create SSH CA: {e}")
        return error_response('Failed to create SSH CA', 500)


@bp.route('/api/v2/ssh/cas/<int:ca_id>', methods=['PUT'])
@require_auth(['write:ssh'])
def update_ssh_ca(ca_id):
    """Update SSH CA metadata."""
    try:
        data = request.json or {}
        username = g.current_user.username if hasattr(g, 'current_user') else 'system'

        kwargs = {}
        if 'descr' in data or 'name' in data:
            descr = (data.get('descr') or data.get('name') or '').strip()
            if descr:
                kwargs['descr'] = descr
        if 'default_ttl' in data:
            kwargs['default_ttl'] = data['default_ttl']
        if 'max_ttl' in data:
            kwargs['max_ttl'] = data['max_ttl']
        if 'comment' in data:
            kwargs['comment'] = data['comment']
        if 'owner_group_id' in data:
            kwargs['owner_group_id'] = data['owner_group_id']
        if 'default_extensions' in data:
            kwargs['default_extensions'] = data['default_extensions']
        if 'allowed_principals' in data:
            kwargs['allowed_principals'] = data['allowed_principals']

        ca = SSHCAService.update_ca(ca_id, **kwargs)

        AuditService.log_action(
            action='ssh_ca_updated',
            resource_type='ssh_ca',
            resource_id=str(ca.id),
            resource_name=ca.descr,
            details=f'SSH CA "{ca.descr}" updated',
            success=True,
            username=username,
        )

        try:
            from websocket.emitters import on_ssh_ca_updated
            on_ssh_ca_updated(ca.id, ca.descr, username)
        except Exception:
            pass

        return success_response(
            data=ca.to_dict(),
            message='SSH CA updated successfully'
        )

    except ValueError as e:
        return error_response(str(e), 400)
    except Exception as e:
        logger.error(f"Failed to update SSH CA {ca_id}: {e}")
        return error_response('Failed to update SSH CA', 500)


@bp.route('/api/v2/ssh/cas/<int:ca_id>', methods=['DELETE'])
@require_auth(['delete:ssh'])
def delete_ssh_ca(ca_id):
    """Delete an SSH CA."""
    ca = SSHCertificateAuthority.query.get(ca_id)
    if not ca:
        return error_response('SSH CA not found', 404)

    ca_name = ca.descr
    username = g.current_user.username if hasattr(g, 'current_user') else 'system'

    try:
        SSHCAService.delete_ca(ca_id)

        AuditService.log_action(
            action='ssh_ca_deleted',
            resource_type='ssh_ca',
            resource_id=str(ca_id),
            resource_name=ca_name,
            details=f'SSH CA "{ca_name}" deleted',
            success=True,
            username=username,
        )

        try:
            from websocket.emitters import on_ssh_ca_deleted
            on_ssh_ca_deleted(ca_id, ca_name, username)
        except Exception:
            pass

        return no_content_response()

    except ValueError as e:
        return error_response(str(e), 409)
    except Exception as e:
        logger.error(f"Failed to delete SSH CA {ca_id}: {e}")
        return error_response('Failed to delete SSH CA', 500)
