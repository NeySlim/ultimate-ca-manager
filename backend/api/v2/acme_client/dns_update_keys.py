"""
TSIG keys of the DNS UPDATE (RFC 2136) listener, per ACME proxy account.

  GET    /acme/client/accounts/<id>/dns-update-keys            list (no secrets)
  POST   /acme/client/accounts/<id>/dns-update-keys            create (secret shown once)
  DELETE /acme/client/accounts/<id>/dns-update-keys/<key_id>   revoke, or delete if revoked

The secret is never logged and never written to the audit log.
"""
import base64
import secrets

import dns.name
from flask import request, g

from api.v2.acme_client import bp, logger
from auth.unified import require_auth
from models import db, AcmeClientAccount, AcmeEabCredential
from models.acme_dns_update import AcmeDnsUpdateKey
from services.acme.dns_update.keys import invalidate_keys
from services.audit_service import AuditService
from utils.datetime_utils import utc_now
from utils.db_transaction import safe_commit
from utils.response import success_response, error_response, no_content_response

DEFAULT_ALGORITHM = 'hmac-sha256'
MAX_NOTES_LENGTH = 1000


def _current_user_id():
    user = getattr(g, 'current_user', None)
    return getattr(g, 'user_id', None) or (user.id if user else None)


@bp.route('/api/v2/acme/client/accounts/<int:account_id>/dns-update-keys', methods=['GET'])
@require_auth(['read:acme'])
def list_dns_update_keys(account_id):
    """List TSIG keys of an account. The secret is never returned here."""
    if not db.session.get(AcmeClientAccount, account_id):
        return error_response('ACME account not found', 404)
    keys = (AcmeDnsUpdateKey.query
            .filter_by(acme_client_account_id=account_id)
            .order_by(AcmeDnsUpdateKey.id.asc()).all())
    return success_response(data=[k.to_dict() for k in keys])


@bp.route('/api/v2/acme/client/accounts/<int:account_id>/dns-update-keys', methods=['POST'])
@require_auth(['write:acme'])
def create_dns_update_key(account_id):
    """Create a TSIG key. The secret is in this response only."""
    acct = db.session.get(AcmeClientAccount, account_id)
    if not acct:
        return error_response('ACME account not found', 404)

    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return error_response('Request body must be a JSON object', 400)

    algorithm = data.get('algorithm')
    if algorithm is None:
        algorithm = DEFAULT_ALGORITHM
    if not isinstance(algorithm, str) or algorithm.strip().lower() not in AcmeDnsUpdateKey.ALGORITHMS:
        return error_response(
            f'algorithm must be one of: {", ".join(AcmeDnsUpdateKey.ALGORITHMS)}', 400)
    algorithm = algorithm.strip().lower()

    notes = data.get('notes')
    if notes is not None:
        if not isinstance(notes, str):
            return error_response('notes must be a string', 400)
        if len(notes) > MAX_NOTES_LENGTH:
            return error_response(f'notes must not exceed {MAX_NOTES_LENGTH} characters', 400)
        notes = notes.strip() or None

    eab_credential_id = data.get('eab_credential_id')
    if eab_credential_id is not None:
        if isinstance(eab_credential_id, bool) or not isinstance(eab_credential_id, int):
            return error_response('eab_credential_id must be an integer', 400)
        cred = db.session.get(AcmeEabCredential, eab_credential_id)
        if not cred or cred.status == 'revoked':
            return error_response('eab_credential_id must reference an existing, non-revoked EAB credential', 400)

    raw_name = data.get('name')
    try:
        if raw_name is None or (isinstance(raw_name, str) and not raw_name.strip()):
            base = acct.proxy_slug or f'proxy{account_id}'
            name = AcmeDnsUpdateKey.normalize_name(f'{base}-{secrets.token_hex(4)}.')
        else:
            name = AcmeDnsUpdateKey.normalize_name(raw_name)
    except ValueError as e:
        return error_response(str(e), 400)

    if AcmeDnsUpdateKey.query.filter_by(name=name).first():
        return error_response('A key with this name already exists', 409)

    from services.acme.dns_update import tsig
    raw = tsig.generate_secret(dns.name.from_text(algorithm))
    secret_b64 = base64.b64encode(raw).decode('ascii')

    key = AcmeDnsUpdateKey(
        acme_client_account_id=account_id,
        eab_credential_id=eab_credential_id,
        name=name,
        algorithm=algorithm,
        status='active',
        created_by_user_id=_current_user_id(),
        notes=notes,
    )
    key.secret = secret_b64
    db.session.add(key)
    ok, err = safe_commit(logger, 'Failed to create DNS UPDATE key')
    if not ok:
        return err
    invalidate_keys()

    AuditService.log_action(
        action='acme.dns_update.key.create',
        resource_type='acme_dns_update_key',
        resource_id=str(key.id),
        resource_name=name,
        details=(f'Created DNS UPDATE key {name} ({algorithm}) for ACME account {account_id}'
                 + (f', EAB credential {eab_credential_id}' if eab_credential_id else '')),
        success=True,
    )

    payload = key.to_dict()
    payload['secret'] = secret_b64
    return success_response(
        data=payload,
        message='DNS UPDATE key created. Copy the secret now: it is not shown again.',
        status=201,
    )


@bp.route('/api/v2/acme/client/accounts/<int:account_id>/dns-update-keys/<int:key_id>',
          methods=['DELETE'])
@require_auth(['delete:acme'])
def delete_dns_update_key(account_id, key_id):
    """Revoke an active key. Delete an already revoked one."""
    key = db.session.get(AcmeDnsUpdateKey, key_id)
    if not key or key.acme_client_account_id != account_id:
        return error_response('DNS UPDATE key not found', 404)

    name = key.name
    if key.status == 'revoked':
        db.session.delete(key)
        ok, err = safe_commit(logger, 'Failed to delete DNS UPDATE key')
        if not ok:
            return err
        invalidate_keys()
        AuditService.log_action(
            action='acme.dns_update.key.delete',
            resource_type='acme_dns_update_key',
            resource_id=str(key_id),
            resource_name=name,
            details=f'Deleted revoked DNS UPDATE key {name}',
            success=True,
        )
        return no_content_response()

    key.status = 'revoked'
    key.revoked_at = utc_now()
    ok, err = safe_commit(logger, 'Failed to revoke DNS UPDATE key')
    if not ok:
        return err
    invalidate_keys()
    AuditService.log_action(
        action='acme.dns_update.key.revoke',
        resource_type='acme_dns_update_key',
        resource_id=str(key_id),
        resource_name=name,
        details=f'Revoked DNS UPDATE key {name}',
        success=True,
    )
    return success_response(data=key.to_dict(), message='DNS UPDATE key revoked')
