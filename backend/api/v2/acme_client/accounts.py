"""
ACME Client CA Accounts — multi-CA management.

CRUD over ``acme_client_accounts`` (the external ACME authorities UCM can
request certificates from: Let's Encrypt, ZeroSSL, ...). Each row is
one directory URL + its registration credentials and optional EAB. One row can
be flagged ``is_default`` and is used when a request does not select a CA.

Routes (all under /api/v2):
  GET    /acme/client/accounts              list
  POST   /acme/client/accounts              create (optional external key import)
  GET    /acme/client/accounts/<id>         detail
  PATCH  /acme/client/accounts/<id>         update
  DELETE /acme/client/accounts/<id>         delete (detaches orders)
  POST   /acme/client/accounts/<id>/register  register with the CA
  POST   /acme/client/accounts/<id>/default   mark as default
  POST   /acme/client/accounts/<id>/deactivate deactivate upstream (RFC 8555 §7.3.6) + remove
"""

import logging

from flask import request

from api.v2.acme_client import bp
from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit
from utils.ssrf_protection import validate_url_not_cloud_metadata
from models import db
from models.acme_client_account import AcmeClientAccount
from models.acme_models import AcmeClientOrder
from services.acme.acme_client_service import AcmeClientService, ACCOUNT_KEY_TYPES
from services.acme.dns_update.keys import invalidate_keys
from services.audit_service import AuditService

logger = logging.getLogger(__name__)


def _validate_imported_account_key(pem: str) -> str:
    """Validate an unencrypted PEM private key for use as an imported ACME
    account key. Returns the matching JWS algorithm (RS256/ES256/ES384).
    Raises ValueError on any problem."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa, ec

    pem = pem.strip()
    try:
        key = serialization.load_pem_private_key(pem.encode('utf-8'), password=None)
    except Exception:
        raise ValueError(
            'Invalid account key: expected an unencrypted RSA or ECDSA private key in PEM format'
        )
    if isinstance(key, rsa.RSAPrivateKey):
        if key.key_size < 2048:
            raise ValueError('RSA account keys must be at least 2048 bits')
        return 'RS256'
    if isinstance(key, ec.EllipticCurvePrivateKey):
        if isinstance(key.curve, ec.SECP256R1):
            return 'ES256'
        if isinstance(key.curve, ec.SECP384R1):
            return 'ES384'
        raise ValueError('EC account keys must use the P-256 or P-384 curve')
    raise ValueError('Unsupported key type: RSA and ECDSA (P-256/P-384) only')


def _validate_directory_url(url: str) -> None:
    """Reject loopback/cloud-metadata targets for outbound ACME directory fetches."""
    try:
        validate_url_not_cloud_metadata(url)
    except ValueError:
        raise ValueError('directory_url cannot target cloud metadata or loopback')


def _ensure_unique_proxy_slug(slug: str, except_id: int = None) -> str:
    from services.acme.acme_proxy_account import normalize_proxy_slug
    slug = normalize_proxy_slug(slug)
    q = AcmeClientAccount.query.filter_by(proxy_slug=slug)
    if except_id is not None:
        q = q.filter(AcmeClientAccount.id != except_id)
    if q.first():
        raise ValueError(f'proxy_slug {slug!r} is already in use')
    return slug


def _apply_proxy_endpoint_fields(acct: AcmeClientAccount, data: dict) -> None:
    from services.acme.acme_proxy_account import slugify_proxy_label

    if 'proxy_enabled' in data:
        acct.proxy_enabled = bool(data.get('proxy_enabled'))

    if 'proxy_slug' in data:
        raw = (data.get('proxy_slug') or '').strip()
        if raw:
            acct.proxy_slug = _ensure_unique_proxy_slug(raw, except_id=acct.id)
        elif not acct.proxy_enabled:
            acct.proxy_slug = None
    elif acct.proxy_enabled and not acct.proxy_slug:
        base = slugify_proxy_label(acct.label)
        acct.proxy_slug = _ensure_unique_proxy_slug(base, except_id=acct.id)

    if acct.proxy_enabled and not acct.proxy_slug:
        acct.proxy_slug = _ensure_unique_proxy_slug(
            slugify_proxy_label(acct.label), except_id=acct.id
        )
    if not acct.proxy_enabled and 'proxy_slug' in data and not (data.get('proxy_slug') or '').strip():
        acct.proxy_slug = None


def _validate_timing_int(value, field: str, min_val: int, max_val: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ValueError(f'{field} must be an integer')
    if n < min_val or n > max_val:
        raise ValueError(f'{field} must be between {min_val} and {max_val}')
    return n


def _apply_timing_fields(acct: AcmeClientAccount, data: dict) -> None:
    if 'order_poll_timeout_sec' in data:
        acct.order_poll_timeout_sec = _validate_timing_int(
            data['order_poll_timeout_sec'], 'order_poll_timeout_sec', 30, 600,
        )
    if 'order_poll_interval_sec' in data:
        acct.order_poll_interval_sec = _validate_timing_int(
            data['order_poll_interval_sec'], 'order_poll_interval_sec', 1, 30,
        )
    if 'http_timeout_sec' in data:
        acct.http_timeout_sec = _validate_timing_int(
            data['http_timeout_sec'], 'http_timeout_sec', 10, 120,
        )


def _apply_preferred_chain_field(acct: AcmeClientAccount, data: dict) -> None:
    if 'preferred_chain' not in data:
        return
    value = (data.get('preferred_chain') or '').strip()
    if value and len(value) > 255:
        raise ValueError('preferred_chain must be 255 characters or less')
    acct.preferred_chain = value or None


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
    acct = db.session.get(AcmeClientAccount, account_id)
    if not acct:
        return error_response('ACME account not found', 404)
    return success_response(data=acct.to_dict())


@bp.route('/api/v2/acme/client/accounts', methods=['POST'])
@require_auth(['write:acme'])
def create_ca_account():
    """Create a new external ACME CA account.

    Body: { directory_url, label, email, account_key_algorithm?, eab_kid?,
            eab_hmac_key?, is_default?, account_key_pem? }

    ``account_key_pem``: optional unencrypted PEM private key of an existing
    ACME account to import (key algorithm is derived from the key, the
    ``account_key_algorithm`` parameter is ignored when a key is provided).
    """
    data = request.json or {}

    directory_url = (data.get('directory_url') or '').strip()
    label = (data.get('label') or '').strip()
    email = (data.get('email') or '').strip()

    # Empty URL defaults to Let's Encrypt Production (matches the UI helper).
    if not directory_url:
        directory_url = AcmeClientAccount.LE_PRODUCTION_URL
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

    try:
        _validate_directory_url(directory_url)
    except ValueError as exc:
        return error_response(str(exc), 400)

    # Multiple accounts per directory URL are explicitly allowed (#276) — the
    # row id is the account identity.

    algorithm = data.get('account_key_algorithm') or 'ES256'
    imported_key_pem = None
    account_key_pem = (data.get('account_key_pem') or '').strip()
    if account_key_pem:
        if len(account_key_pem) > 64 * 1024:
            return error_response('account_key_pem too large (max 64 KB)', 413)
        try:
            # Algorithm is derived from the imported key, not trusted from input.
            algorithm = _validate_imported_account_key(account_key_pem)
        except ValueError as exc:
            return error_response(str(exc), 400)
        imported_key_pem = account_key_pem
    elif algorithm not in ACCOUNT_KEY_TYPES:
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
    if imported_key_pem:
        # Same at-rest treatment as a generated key (encrypt_text is a no-op
        # when no master key is configured — mirrors _get_account_key).
        from security.encryption import encrypt_text
        acct.account_key = encrypt_text(imported_key_pem)
    try:
        _apply_timing_fields(acct, data)
        _apply_proxy_endpoint_fields(acct, data)
        _apply_preferred_chain_field(acct, data)
    except ValueError as exc:
        return error_response(str(exc), 400)
    db.session.add(acct)
    ok, err = safe_commit(logger, 'Failed to create ACME CA account')
    if not ok:
        return err
    invalidate_keys()  # proxy_enabled/slug/deletion change usable TSIG keys

    AuditService.log_action(
        action='acme_ca_account_create',
        resource_type='acme_client_account',
        resource_id=str(acct.id),
        resource_name=label,
        details=(
            f'Created ACME CA account {label} ({directory_url})'
            + (' with imported account key' if imported_key_pem else '')
        ),
        success=True,
    )
    return success_response(data=acct.to_dict(), status=201)


@bp.route('/api/v2/acme/client/accounts/<int:account_id>', methods=['PATCH'])
@require_auth(['write:acme'])
def update_ca_account(account_id):
    """Update mutable fields of a CA account.

    Editable: label, email, account_key_algorithm, eab_kid, eab_hmac_key,
    is_default, preferred_chain. directory_url is immutable (it is the identity of the account;
    changing it would orphan the registration). EAB hmac is only overwritten
    when a non-empty value is supplied.
    """
    acct = db.session.get(AcmeClientAccount, account_id)
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

    try:
        _apply_timing_fields(acct, data)
        _apply_proxy_endpoint_fields(acct, data)
        _apply_preferred_chain_field(acct, data)
    except ValueError as exc:
        return error_response(str(exc), 400)

    ok, err = safe_commit(logger, 'Failed to update ACME CA account')
    if not ok:
        return err
    invalidate_keys()  # proxy_enabled/slug/deletion change usable TSIG keys

    AuditService.log_action(
        action='acme_ca_account_update',
        resource_type='acme_client_account',
        resource_id=str(acct.id),
        resource_name=acct.label,
        details=f'Updated ACME CA account {acct.label}',
        success=True,
    )
    return success_response(data=acct.to_dict())


def _remove_account_row(acct: AcmeClientAccount) -> None:
    """Detach orders and delete an account row; promotes a replacement default
    if needed. Does not commit — caller wraps in safe_commit."""
    was_default = acct.is_default
    AcmeClientOrder.query.filter_by(acme_client_account_id=acct.id).update(
        {AcmeClientOrder.acme_client_account_id: None}
    )
    # SQLite does not enforce the FK cascade: remove keys and expected values
    # in the same transaction so nothing outlives the account.
    from models.acme_dns_update import AcmeDnsUpdateKey, AcmeProxyDnsChallenge
    AcmeDnsUpdateKey.query.filter_by(acme_client_account_id=acct.id).delete(
        synchronize_session=False)
    AcmeProxyDnsChallenge.query.filter_by(acme_client_account_id=acct.id).delete(
        synchronize_session=False)
    db.session.delete(acct)
    if was_default:
        replacement = AcmeClientAccount.query.filter(
            AcmeClientAccount.id != acct.id
        ).order_by(AcmeClientAccount.id.asc()).first()
        if replacement:
            replacement.is_default = True


@bp.route('/api/v2/acme/client/accounts/<int:account_id>', methods=['DELETE'])
@require_auth(['delete:acme'])
def delete_ca_account(account_id):
    """Delete a CA account. Orders pinned to it are detached (set NULL) so they
    fall back to the default account on the next renewal."""
    acct = db.session.get(AcmeClientAccount, account_id)
    if not acct:
        return error_response('ACME account not found', 404)

    label = acct.label
    _remove_account_row(acct)

    ok, err = safe_commit(logger, 'Failed to delete ACME CA account')
    if not ok:
        return err
    invalidate_keys()  # proxy_enabled/slug/deletion change usable TSIG keys

    AuditService.log_action(
        action='acme_ca_account_delete',
        resource_type='acme_client_account',
        resource_id=str(account_id),
        resource_name=label,
        details=f'Deleted ACME CA account {label}',
        success=True,
    )
    return success_response(message=f'Account {label} deleted')


@bp.route('/api/v2/acme/client/accounts/<int:account_id>/deactivate', methods=['POST'])
@require_auth(['delete:acme'])
def deactivate_ca_account(account_id):
    """Deactivate the ACME account upstream (RFC 8555 §7.3.6), then remove it.

    Deactivation is permanent and server-side: the CA will refuse any further
    use of the account (orders, renewal) with the same key. Only on upstream
    success is the local row deleted; a failed deactivation keeps the row so
    the user can retry or simply delete it.
    """
    acct = db.session.get(AcmeClientAccount, account_id)
    if not acct:
        return error_response('ACME account not found', 404)
    if not acct.is_registered():
        return error_response(
            'Account is not registered with the CA: use Delete to remove it locally', 400
        )

    label = acct.label
    try:
        client = AcmeClientService(account=acct)
        success, message = client.deactivate_account()
        if not success:
            return error_response(message, 502)
    except Exception as e:
        logger.error(f'ACME CA account deactivation failed: {e}')
        return error_response('Deactivation failed', 502)

    _remove_account_row(acct)
    ok, err = safe_commit(logger, 'Failed to remove deactivated ACME CA account')
    if not ok:
        return err
    invalidate_keys()  # proxy_enabled/slug/deletion change usable TSIG keys

    AuditService.log_action(
        action='acme_ca_account_deactivate',
        resource_type='acme_client_account',
        resource_id=str(account_id),
        resource_name=label,
        details=f'Deactivated ACME CA account {label} upstream and removed it',
        success=True,
    )
    return success_response(message=f'Account {label} deactivated')


@bp.route('/api/v2/acme/client/accounts/<int:account_id>/default', methods=['POST'])
@require_auth(['write:acme'])
def set_default_ca_account(account_id):
    """Mark a CA account as the default used when a request selects no CA."""
    acct = db.session.get(AcmeClientAccount, account_id)
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
    acct = db.session.get(AcmeClientAccount, account_id)
    if not acct:
        return error_response('ACME account not found', 404)

    data = request.json or {}
    email = (data.get('email') or acct.email or '').strip()
    if not email or len(email) > 254:
        return error_response('A valid contact email is required', 400)

    try:
        _validate_directory_url(acct.directory_url)
    except ValueError as exc:
        return error_response(str(exc), 400)

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
