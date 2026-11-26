"""SSH hosts and their enrollment tokens (issue #451): the management side of the host agent.

Reading needs read:ssh, creating or revoking a token and revoking or pausing a host write:ssh,
as for the certificates these hosts hold.
"""
import logging

from flask import Blueprint, g, request
from sqlalchemy import or_

from auth.unified import require_auth
from models import db
from models.ssh import SSHHost, SSHHostEnrollmentToken
from services import ssh_host_service as hosts
from services.audit_service import AuditService
from utils.pagination import parse_request_pagination
from utils.response import created_response, error_response, success_response

logger = logging.getLogger(__name__)

bp = Blueprint('ssh_hosts_v2', __name__)

HOST_STATES = ('valid', 'expired', 'revoked')


def _username():
    user = getattr(g, 'current_user', None)
    return user.username if user else None


@bp.route('/api/v2/ssh/hosts', methods=['GET'])
@require_auth(['read:ssh'])
def list_ssh_hosts():
    page, per_page = parse_request_pagination(default_per_page=25)
    query = SSHHost.query
    ca_id = request.args.get('ca_id', type=int)
    if ca_id:
        query = query.filter(SSHHost.ssh_ca_id == ca_id)
    search = request.args.get('search', '').strip()
    if search:
        safe = search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        query = query.filter(or_(SSHHost.name.ilike(f'%{safe}%', escape='\\'),
                                 SSHHost.principals.ilike(f'%{safe}%', escape='\\'),
                                 SSHHost.fingerprint.ilike(f'%{safe}%', escape='\\')))
    state = request.args.get('state', '').strip()
    if state and state not in HOST_STATES:
        return error_response(f"state must be one of: {', '.join(HOST_STATES)}", 400)
    rows = query.order_by(SSHHost.name, SSHHost.id).all()
    counts = {s: 0 for s in HOST_STATES}
    for row in rows:
        counts[row.state] += 1
    if state:
        rows = [row for row in rows if row.state == state]
    total = len(rows)
    items = rows[(page - 1) * per_page:page * per_page]
    return success_response(data=[h.to_dict() for h in items], meta={
        'total': total, 'page': page, 'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page, 'counts': {**counts, 'total': sum(counts.values())}})


@bp.route('/api/v2/ssh/hosts/<int:host_id>', methods=['GET'])
@require_auth(['read:ssh'])
def get_ssh_host(host_id):
    host = db.session.get(SSHHost, host_id)
    if not host:
        return error_response('SSH host not found', 404)
    return success_response(data=host.to_dict())


@bp.route('/api/v2/ssh/hosts/<int:host_id>/revoke', methods=['POST'])
@require_auth(['write:ssh'])
def revoke_ssh_host(host_id):
    data = request.get_json(silent=True) or {}
    reason = data.get('reason') or 'host revoked'
    if not isinstance(reason, str) or len(reason) > 255:
        return error_response('reason is text of 255 characters at most', 400)
    try:
        host, first = hosts.revoke_host(host_id, reason, _username())
    except LookupError as e:
        return error_response(str(e), 404)
    except ValueError as e:
        return error_response(str(e), 409)
    # The request that set revoked_at was audited by revoke_host; a later one only finished it
    if not first:
        AuditService.log_action(action='ssh_host_revocation_finished', resource_type='ssh_host',
                                resource_id=str(host.id), resource_name=host.name, success=True,
                                details=f'SSH host revocation finished, certificates left live revoked: {reason}')
    return success_response(data=host.to_dict(), message='SSH host revoked')


@bp.route('/api/v2/ssh/hosts/<int:host_id>/auto-renew', methods=['POST'])
@require_auth(['write:ssh'])
def set_ssh_host_auto_renew(host_id):
    data = request.get_json(silent=True) or {}
    try:
        host = hosts.set_auto_renew(host_id, data.get('enabled'))
    except LookupError as e:
        return error_response(str(e), 404)
    except ValueError as e:
        return error_response(str(e), 400)
    AuditService.log_action(action='ssh_host_auto_renew', resource_type='ssh_host', resource_id=str(host.id),
                            resource_name=host.name,
                            details=f"SSH host renewal {'enabled' if host.auto_renew else 'disabled'}", success=True)
    return success_response(data=host.to_dict())


@bp.route('/api/v2/ssh/enrollment-tokens', methods=['GET'])
@require_auth(['read:ssh'])
def list_enrollment_tokens():
    query = SSHHostEnrollmentToken.query
    ca_id = request.args.get('ca_id', type=int)
    if ca_id:
        query = query.filter(SSHHostEnrollmentToken.ssh_ca_id == ca_id)
    rows = query.order_by(SSHHostEnrollmentToken.created_at.desc(), SSHHostEnrollmentToken.id.desc()).all()
    return success_response(data=[t.to_dict() for t in rows])


@bp.route('/api/v2/ssh/enrollment-tokens', methods=['POST'])
@require_auth(['write:ssh'])
def create_enrollment_token():
    """The token is in this answer only: UCM keeps its SHA-256."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response('a JSON object is required', 400)
    try:
        token, secret = hosts.create_token(
            data.get('ca_id'), data.get('principals'), validity_seconds=data.get('validity_seconds'),
            lifetime_seconds=data.get('lifetime_seconds'), renew_percent=data.get('renew_percent'),
            descr=data.get('descr'), username=_username())
    except LookupError as e:
        return error_response(str(e), 404)
    except ValueError as e:
        return error_response(str(e), 400)
    AuditService.log_action(
        action='ssh_host_token_created', resource_type='ssh_host_token', resource_id=str(token.id),
        resource_name=token.token_prefix,
        details=(f"SSH host enrollment token for CA '{token.ca.descr}', "
                 f"{', '.join(token.get_principals())}, until {token.expires_at:%Y-%m-%d %H:%M} UTC"),
        success=True)
    return created_response({**token.to_dict(), 'token': secret}, message='Enrollment token created')


@bp.route('/api/v2/ssh/enrollment-tokens/<int:token_id>/revoke', methods=['POST'])
@require_auth(['write:ssh'])
def revoke_enrollment_token(token_id):
    try:
        token = hosts.revoke_token(token_id)
    except LookupError as e:
        return error_response(str(e), 404)
    except ValueError as e:
        return error_response(str(e), 409)
    AuditService.log_action(action='ssh_host_token_revoked', resource_type='ssh_host_token',
                            resource_id=str(token.id), resource_name=token.token_prefix,
                            details='SSH host enrollment token revoked', success=True)
    return success_response(data=token.to_dict(), message='Enrollment token revoked')
