"""
SSH Certificate Authorities API

CRUD endpoints for SSH CAs + public key export + KRL download.
"""

import logging
from flask import Blueprint, request, g, Response

from auth.unified import require_auth
from utils.response import success_response, error_response, created_response, no_content_response
from services.ssh_ca_service import SSHCAService
from services.ssh_krl_service import SSHKRLService
from services.audit_service import AuditService
from models.ssh import SSHCertificateAuthority

logger = logging.getLogger(__name__)

bp = Blueprint('ssh_cas_v2', __name__)


@bp.route('/api/v2/ssh/cas', methods=['GET'])
@require_auth(['read:ssh'])
def list_ssh_cas():
    """List all SSH CAs with optional filtering."""
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(max(1, request.args.get('per_page', 20, type=int)), 100)
    search = request.args.get('search', '').strip()
    ca_type = request.args.get('type', '').strip()

    query = SSHCertificateAuthority.query

    if ca_type and ca_type in SSHCertificateAuthority.VALID_CA_TYPES:
        query = query.filter_by(ca_type=ca_type)

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


@bp.route('/api/v2/ssh/cas/<int:ca_id>/public-key', methods=['GET'])
@require_auth(['read:ssh'])
def get_ssh_ca_public_key(ca_id):
    """Download the CA's public key in OpenSSH format.

    Used for sshd_config TrustedUserCAKeys or ssh_known_hosts.
    """
    try:
        pub_key = SSHCAService.get_public_key(ca_id)
        ca = SSHCertificateAuthority.query.get(ca_id)

        return Response(
            pub_key,
            mimetype='text/plain',
            headers={
                'Content-Disposition': f'attachment; filename="ssh_ca_{ca.descr.replace(" ", "_")}.pub"'
            }
        )
    except ValueError as e:
        return error_response(str(e), 404)
    except Exception as e:
        logger.error(f"Failed to export SSH CA public key: {e}")
        return error_response('Failed to export public key', 500)


@bp.route('/api/v2/ssh/cas/<int:ca_id>/krl', methods=['GET'])
@require_auth(['read:ssh'])
def get_ssh_ca_krl(ca_id):
    """Download the KRL (Key Revocation List) for this CA."""
    try:
        krl_data = SSHKRLService.generate_krl(ca_id)
        ca = SSHCertificateAuthority.query.get(ca_id)
        ca_name = ca.descr if ca else 'unknown'

        return Response(
            krl_data,
            mimetype='application/octet-stream',
            headers={
                'Content-Disposition': f'attachment; filename="ssh_ca_{ca_name.replace(" ", "_")}_krl"'
            }
        )
    except ValueError as e:
        return error_response(str(e), 404)
    except RuntimeError as e:
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"Failed to generate KRL: {e}")
        return error_response('Failed to generate KRL', 500)
