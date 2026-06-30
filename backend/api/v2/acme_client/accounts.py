"""
ACME Client CA Accounts — multi-CA management.

CRUD over ``acme_client_accounts`` (the external ACME authorities UCM can
request certificates from: Let's Encrypt, Actalis, ZeroSSL, ...). Each row is
one directory URL + its registration credentials and optional EAB. One row can
be flagged ``is_default`` and is used when a request does not select a CA.

Routes (all under /api/v2):
  GET    /acme/client/accounts              list
  POST   /acme/client/accounts              create
  GET    /acme/client/accounts/<id>         detail
  PATCH  /acme/client/accounts/<id>         update
  DELETE /acme/client/accounts/<id>         delete (detaches orders)
  POST   /acme/client/accounts/<id>/register  register with the CA
  POST   /acme/client/accounts/<id>/default   mark as default
"""

import logging

from flask import request

from api.v2.acme_client import bp
from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit
from models import db
from models.acme_client_account import AcmeClientAccount
from models.acme_models import AcmeClientOrder
from services.acme.acme_client_service import AcmeClientService, ACCOUNT_KEY_TYPES
from services.audit_service import AuditService

logger = logging.getLogger(__name__)


def _clear_other_defaults(except_id=None):
    q = AcmeClientAccount.query.filter(AcmeClientAccount.is_default.is_(True))
    if except_id is not None:
        q = q.filter(AcmeClientAccount.id != except_id)
    for acct in q.all():
        acct.is_default = False


@bp.route('/api/v2/acme/client/accounts', methods=['GET'])
@require_auth(['read:acme'])
def list_ca_accounts():
    """List all configured external ACME CA accounts."""
    accounts = AcmeClientAccount.query.order_by(
        AcmeClientAccount.is_default.desc(), AcmeClientAccount.label.asc()
    ).all()
    return success_response(data=[a.to_dict() for a in accounts])


@bp.route('/api/v2/acme/client/accounts/<int:account_id>', methods=['GET'])
@require_auth(['read:acme'])
def get_ca_account(account_id):
    acct = AcmeClientAccount.query.get(account_id)
    if not acct:
        return error_response('ACME account not found', 404)
    return success_response(data=acct.to_dict())


@bp.route('/api/v2/acme/client/accounts', methods=['POST'])
@require_auth(['write:acme'])
def create_ca_account():
    """Create a new external ACME CA account.

    Body: { directory_url, label, email, account_key_algorithm?, eab_kid?,
            eab_hmac_key?, is_default? }
    """
    data = request.json or {}

    directory_url = (data.get('directory_url') or '').strip()
    label = (data.get('label') or '').strip()
    email = (data.get('email') or '').strip()

    if not directory_url:
        return error_response('directory_url is required', 400)
    if not directory_url.startswith('https://'):
        return error_response('directory_url must be an https:// URL', 400)
    if len(directory_url) > 500:
        return error_response('directory_url too long (max 500 chars)', 400)
    if not label:
        return error_response('label is required', 400)
    if len(label) > 100:
        return error_response('label too long (max 100 chars)', 400)
    if not email:
        return error_response('email is required', 400)
    if len(email) > 254:
        return error_response('email too long (max 254 chars)', 400)

    if AcmeClientAccount.query.filter_by(directory_url=directory_url).first():
        return error_response('An account for this directory_url already exists', 409)

    algorithm = data.get('account_key_algorithm') or 'ES256'
    if algorithm not in ACCOUNT_KEY_TYPES:
        return error_response(
            f'Invalid account_key_algorithm (allowed: {", ".join(ACCOUNT_KEY_TYPES)})', 400
        )

    is_default = bool(data.get('is_default'))
    # First account is implicitly the default so issuance has a target.
    if AcmeClientAccount.query.count() == 0:
        is_default = True
    if is_default:
        _clear_other_defaults()

    acct = AcmeClientAccount(
        directory_url=directory_url,
        label=label,
        email=email,
        account_key_algorithm=algorithm,
        eab_kid=(data.get('eab_kid') or '').strip() or None,
        eab_hmac_key=(data.get('eab_hmac_key') or '').strip() or None,
        is_default=is_default,
    )
    db.session.add(acct)
    ok, err = safe_commit(logger, 'Failed to create ACME CA account')
    if not ok:
        return err

    AuditService.log_action(
        action='acme_ca_account_create',
        resource_type='acme_client_account',
        resource_id=str(acct.id),
        resource_name=label,
        details=f'Created ACME CA account {label} ({directory_url})',
        success=True,
    )
    return success_response(data=acct.to_dict(), status=201)


@bp.route('/api/v2/acme/client/accounts/<int:account_id>', methods=['PATCH'])
@require_auth(['write:acme'])
def update_ca_account(account_id):
    """Update mutable fields of a CA account.

    Editable: label, email, account_key_algorithm, eab_kid, eab_hmac_key,
    is_default. directory_url is immutable (it is the identity of the account;
    changing it would orphan the registration). EAB hmac is only overwritten
    when a non-empty value is supplied.
    """
    acct = AcmeClientAccount.query.get(account_id)
    if not acct:
        return error_response('ACME account not found', 404)

    data = request.json or {}

    if 'label' in data:
        label = (data.get('label') or '').strip()
        if not label or len(label) > 100:
            return error_response('label is required (max 100 chars)', 400)
        acct.label = label
    if 'email' in data:
        email = (data.get('email') or '').strip()
        if not email or len(email) > 254:
            return error_response('email is required (max 254 chars)', 400)
        acct.email = email
    if 'account_key_algorithm' in data:
        algorithm = data.get('account_key_algorithm') or 'ES256'
        if algorithm not in ACCOUNT_KEY_TYPES:
            return error_response('Invalid account_key_algorithm', 400)
        acct.account_key_algorithm = algorithm
    if 'eab_kid' in data:
        acct.eab_kid = (data.get('eab_kid') or '').strip() or None
    if 'eab_hmac_key' in data:
        hmac_val = (data.get('eab_hmac_key') or '').strip()
        if hmac_val:  # only overwrite when a real value is provided
            acct.eab_hmac_key = hmac_val
    if data.get('is_default') is True:
        _clear_other_defaults(except_id=acct.id)
        acct.is_default = True

    ok, err = safe_commit(logger, 'Failed to update ACME CA account')
    if not ok:
        return err

    AuditService.log_action(
        action='acme_ca_account_update',
        resource_type='acme_client_account',
        resource_id=str(acct.id),
        resource_name=acct.label,
        details=f'Updated ACME CA account {acct.label}',
        success=True,
    )
    return success_response(data=acct.to_dict())


@bp.route('/api/v2/acme/client/accounts/<int:account_id>', methods=['DELETE'])
@require_auth(['delete:acme'])
def delete_ca_account(account_id):
    """Delete a CA account. Orders pinned to it are detached (set NULL) so they
    fall back to the default account on the next renewal."""
    acct = AcmeClientAccount.query.get(account_id)
    if not acct:
        return error_response('ACME account not found', 404)

    label = acct.label
    was_default = acct.is_default

    AcmeClientOrder.query.filter_by(acme_client_account_id=acct.id).update(
        {AcmeClientOrder.acme_client_account_id: None}
    )
    db.session.delete(acct)

    # If we removed the default, promote another account so issuance keeps a target.
    if was_default:
        replacement = AcmeClientAccount.query.filter(
            AcmeClientAccount.id != acct.id
        ).order_by(AcmeClientAccount.id.asc()).first()
        if replacement:
            replacement.is_default = True

    ok, err = safe_commit(logger, 'Failed to delete ACME CA account')
    if not ok:
        return err

    AuditService.log_action(
        action='acme_ca_account_delete',
        resource_type='acme_client_account',
        resource_id=str(account_id),
        resource_name=label,
        details=f'Deleted ACME CA account {label}',
        success=True,
    )
    return success_response(message=f'Account {label} deleted')


@bp.route('/api/v2/acme/client/accounts/<int:account_id>/default', methods=['POST'])
@require_auth(['write:acme'])
def set_default_ca_account(account_id):
    """Mark a CA account as the default used when a request selects no CA."""
    acct = AcmeClientAccount.query.get(account_id)
    if not acct:
        return error_response('ACME account not found', 404)

    _clear_other_defaults(except_id=acct.id)
    acct.is_default = True
    ok, err = safe_commit(logger, 'Failed to set default ACME CA account')
    if not ok:
        return err

    AuditService.log_action(
        action='acme_ca_account_set_default',
        resource_type='acme_client_account',
        resource_id=str(acct.id),
        resource_name=acct.label,
        details=f'Set ACME CA account {acct.label} as default',
        success=True,
    )
    return success_response(data=acct.to_dict())


@bp.route('/api/v2/acme/client/accounts/<int:account_id>/register', methods=['POST'])
@require_auth(['write:acme'])
def register_ca_account(account_id):
    """Register (or re-register) the ACME account with its CA.

    Generates the account key if needed and performs newAccount (with EAB when
    the account has eab_kid/eab_hmac_key). Body may override the contact email.
    """
    acct = AcmeClientAccount.query.get(account_id)
    if not acct:
        return error_response('ACME account not found', 404)

    data = request.json or {}
    email = (data.get('email') or acct.email or '').strip()
    if not email or len(email) > 254:
        return error_response('A valid contact email is required', 400)

    try:
        client = AcmeClientService(account=acct)
        success, message, account_url = client.register_account(email)
        if not success:
            return error_response(message, 400)

        acct.email = email
        ok, err = safe_commit(logger, 'Failed to persist ACME account registration')
        if not ok:
            return err

        AuditService.log_action(
            action='acme_ca_account_register',
            resource_type='acme_client_account',
            resource_id=str(acct.id),
            resource_name=acct.label,
            details=f'Registered ACME CA account {acct.label} ({acct.directory_url})',
            success=True,
        )
        return success_response(
            data={'account_url': account_url, 'account': acct.to_dict()},
            message=message,
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f'ACME CA account registration failed: {e}')
        return error_response('Registration failed', 500)
