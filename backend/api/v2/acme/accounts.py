"""ACME account management routes"""
import json
import base64

from flask import request
from models import db, AcmeAccount, AcmeOrder, AcmeAuthorization, AcmeChallenge, SystemConfig
from models.acme_models import AcmeClientOrder
from services.audit_service import AuditService
from cryptography.hazmat.primitives.asymmetric import rsa, ec
from cryptography.hazmat.primitives import serialization
from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit
from utils.datetime_utils import utc_isoformat
from services.acme.acme_client_service import CERT_KEY_TYPES
from services.acme.jwk_thumbprint import jwk_thumbprint
from utils import key_algorithms

from . import bp, logger, resolve_acme_account

# RFC 7518 §6.2.1.1 curve names, keyed by the pyca curve name.
_JWK_CURVES = {'secp256r1': 'P-256', 'secp384r1': 'P-384', 'secp521r1': 'P-521'}


def _b64url_uint(value: int, length: int) -> str:
    return base64.urlsafe_b64encode(value.to_bytes(length, byteorder='big')).rstrip(b'=').decode()


def _has_jwk(label) -> bool:
    """Whether a key of *label* has a JWK form (RSA, or an EC curve RFC 7518 names)."""
    alg = key_algorithms.get(label)
    return alg is not None and (alg.family == 'RSA' or bool(set(alg.curve_names) & set(_JWK_CURVES)))


def _public_jwk(private_key) -> dict:
    """RFC 7517 public JWK of an RSA or NIST EC key; ValueError for anything else."""
    public_key = private_key.public_key()
    if isinstance(public_key, rsa.RSAPublicKey):
        numbers = public_key.public_numbers()
        return {
            'kty': 'RSA',
            'e': _b64url_uint(numbers.e, 3),
            'n': _b64url_uint(numbers.n, (public_key.key_size + 7) // 8),
        }
    if isinstance(public_key, ec.EllipticCurvePublicKey):
        crv = _JWK_CURVES.get(public_key.curve.name)
        if crv is None:
            raise ValueError(f'No JWK curve name for {public_key.curve.name}')
        numbers = public_key.public_numbers()
        size = (public_key.curve.key_size + 7) // 8
        return {'kty': 'EC', 'crv': crv,
                'x': _b64url_uint(numbers.x, size), 'y': _b64url_uint(numbers.y, size)}
    raise ValueError(f'Unsupported ACME account key: {type(public_key).__name__}')


def _jwk_key_label(jwk_text):
    """Registry label of the key a stored JWK holds ('RSA-2048', 'EC-P256'), None if unreadable."""
    try:
        jwk = json.loads(jwk_text) if isinstance(jwk_text, str) else jwk_text
        if jwk.get('kty') == 'RSA':
            n = base64.urlsafe_b64decode(jwk['n'] + '=' * (-len(jwk['n']) % 4))
            bits = int.from_bytes(n, 'big').bit_length()
            return f'RSA-{bits}' if bits else None
        if jwk.get('kty') in ('EC', 'OKP'):
            return key_algorithms.normalize_label(jwk.get('crv'))
    except (AttributeError, KeyError, TypeError, ValueError):
        pass
    return None


@bp.route('/api/v2/acme/accounts', methods=['GET'])
@require_auth(['read:acme'])
def list_acme_accounts():
    """List ACME accounts"""
    accounts = AcmeAccount.query.order_by(AcmeAccount.created_at.desc()).limit(100).all()

    # One grouped count rather than one query per account.
    order_counts = dict(
        db.session.query(AcmeOrder.account_id, db.func.count(AcmeOrder.id))
        .group_by(AcmeOrder.account_id)
        .all()
    )

    data = []
    for acc in accounts:
        data.append({
            'id': acc.id,
            'account_id': acc.account_id,
            'status': acc.status,
            'contact': acc.contact_list,
            'terms_of_service_agreed': acc.terms_of_service_agreed,
            'jwk_thumbprint': acc.jwk_thumbprint,
            'key_type': _jwk_key_label(acc.jwk),
            'orders_count': order_counts.get(acc.account_id, 0),
            'created_at': utc_isoformat(acc.created_at)
        })

    return success_response(data=data)


@bp.route('/api/v2/acme/accounts', methods=['POST'])
@require_auth(['write:acme'])
def create_acme_account():
    """Create a new ACME account"""
    data = request.get_json()
    if not data:
        return error_response('Request body required', 400)

    email = data.get('email', '').strip()
    key_type = data.get('key_type', 'RSA-2048')
    agree_tos = data.get('agree_tos', False)

    if not email:
        return error_response('Email is required', 400)

    # Judged against the same table the generator uses, the way the client
    # settings route does it. Nothing compared this value before: an EC label
    # this route did not know fell through to P-256 while the JWK went on to
    # say P-256, and every other label fell through to the RSA branch, where
    # the bit count came from the label itself with no ceiling.
    account_types = [k for k in CERT_KEY_TYPES if _has_jwk(k)]
    if key_type not in account_types:
        return error_response(f'Key type must be one of: {", ".join(account_types)}', 400)

    # Check for existing account with same email
    existing = AcmeAccount.query.filter(
        AcmeAccount.contact.like(f'%{email}%')
    ).first()
    if existing:
        return error_response(f'An account with email {email} already exists', 409)

    try:
        import secrets
        account_id = f'acme-{secrets.token_hex(8)}'

        # The JWK describes the key actually generated, never the requested label.
        private_key = key_algorithms.generate(key_type)
        jwk_dict = _public_jwk(private_key)

        # The same RFC 7638 canonicalization the ACME service and the proxy
        # use, so the thumbprint stored here is the one they compare against.
        thumbprint = jwk_thumbprint(jwk_dict)

        # Store the private key in system_config for later use.
        # Encrypted at rest with the master key (no-op if encryption disabled).
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode()
        from security.encryption import encrypt_text
        config_key = f'acme.account.{account_id}.private_key'
        db.session.add(SystemConfig(
            key=config_key,
            value=encrypt_text(pem),
            description=f'Private key for ACME account {account_id}'
        ))

        account = AcmeAccount(
            account_id=account_id,
            jwk=json.dumps(jwk_dict),
            jwk_thumbprint=thumbprint,
            status='valid',
            contact=json.dumps([f'mailto:{email}']),
            terms_of_service_agreed=agree_tos,
        )
        db.session.add(account)
        ok, _err = safe_commit(logger, "Failed to create ACME account")
        if not ok:
            return _err

        AuditService.log_action(
            action='acme.account.create',
            resource_type='acme_account',
            resource_id=str(account.id),
            details=f'Created ACME account: {account_id} ({email})'
        )

        return success_response(data={
            'id': account.id,
            'account_id': account.account_id,
            'status': account.status,
            'contact': account.contact_list,
            'key_type': key_type,
            'terms_of_service_agreed': account.terms_of_service_agreed,
            'created_at': utc_isoformat(account.created_at)
        }, message='Account created')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to create ACME account: {e}")
        return error_response('Failed to create account', 500)


@bp.route('/api/v2/acme/accounts/<string:account_id>/deactivate', methods=['POST'])
@require_auth(['write:acme'])
def deactivate_acme_account(account_id):
    """Deactivate an ACME account (accepts numeric PK or RFC 8555 account_id)"""
    acc = resolve_acme_account(account_id)
    if not acc:
        return error_response('Account not found', 404)

    try:
        acc.status = 'deactivated'
        db.session.commit()

        AuditService.log_action(
            action='acme.account.deactivate',
            resource_type='acme_account',
            resource_id=str(account_id),
            details=f'Deactivated ACME account: {acc.account_id}'
        )

        return success_response(message=f'Account {acc.account_id} deactivated')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to deactivate ACME account {account_id}: {e}")
        return error_response('Failed to deactivate account', 500)


@bp.route('/api/v2/acme/accounts/<string:account_id>', methods=['GET'])
@require_auth(['read:acme'])
def get_acme_account(account_id):
    """Get single ACME account details (accepts numeric PK or RFC 8555 account_id)"""
    acc = resolve_acme_account(account_id)
    if not acc:
        return error_response('Account not found', 404)

    return success_response(data={
        'id': acc.id,
        'account_id': acc.account_id,
        'status': acc.status,
        'contact': acc.contact_list,
        'terms_of_service_agreed': acc.terms_of_service_agreed,
        'jwk_thumbprint': acc.jwk_thumbprint,
        'key_type': _jwk_key_label(acc.jwk),
        'created_at': utc_isoformat(acc.created_at)
    })


@bp.route('/api/v2/acme/accounts/<string:account_id>', methods=['PATCH'])
@require_auth(['write:acme'])
def update_acme_account(account_id):
    """Admin edit of a local ACME account's contact e-mail (#303 major 4).

    Per RFC 8555 the ``contact`` field belongs to the ACME client, which may
    silently overwrite this value on its next account update; the UI spells
    that caveat out. An empty value clears the contact. No shape validation
    here: "tag only" values are legitimate, invalid addresses are skipped at
    send time by the e-mail service.
    """
    account = resolve_acme_account(account_id)
    if not account:
        return error_response('Account not found', 404)

    data = request.json or {}
    if 'email' not in data:
        return error_response('email field required', 400)
    email = data.get('email')
    if email is not None and not isinstance(email, str):
        return error_response('email must be a string', 400)
    email = (email or '').strip()
    if len(email) > 254:
        return error_response('contact value too long', 400)

    account.contact = json.dumps([f'mailto:{email}']) if email else None
    ok, err = safe_commit(logger, 'Failed to update ACME account')
    if not ok:
        return err

    AuditService.log_action(
        action='acme_account_update', resource_type='acme_account',
        resource_id=account.account_id, resource_name=email or '(cleared)',
        details=f'ACME account contact e-mail set to {email or "(empty)"} by admin',
        success=True,
    )
    return success_response(
        data={'account_id': account.account_id, 'contact': account.contact_list},
        message='Account updated',
    )


@bp.route('/api/v2/acme/accounts/<string:account_id>', methods=['DELETE'])
@require_auth(['delete:acme'])
def delete_acme_account(account_id):
    """Delete an ACME account and its related orders/authorizations/challenges
    (accepts numeric PK or RFC 8555 account_id)"""
    acc = resolve_acme_account(account_id)
    if not acc:
        return error_response('Account not found', 404)

    account_name = acc.account_id
    try:
        # Found by the account each row names, not by walking the orders:
        # RFC 8555 allows an authorization before any order exists. Matched on
        # the protocol's text identifiers, never on the numeric keys.
        order_ids = [row.order_id for row in acc.orders]
        # Either way round, because `AcmeAuthorization.account_id` is
        # nullable and the protocol code reads it as such:
        # `auth.account_id or (auth.order.account_id if auth.order else None)`
        # in `api/acme/acme_api.py`. Looking only at the account misses one
        # that names just its order; looking only at the orders misses one
        # asked for before any order exists, which RFC 8555 allows.
        belongs_here = [AcmeAuthorization.account_id == acc.account_id]
        if order_ids:
            belongs_here.append(AcmeAuthorization.order_id.in_(order_ids))
        authorizations = AcmeAuthorization.query.filter(
            db.or_(*belongs_here))

        authorization_ids = [row.authorization_id for row in authorizations]
        if authorization_ids:
            AcmeChallenge.query.filter(
                AcmeChallenge.authorization_id.in_(authorization_ids)
            ).delete(synchronize_session=False)
            AcmeAuthorization.query.filter(
                AcmeAuthorization.authorization_id.in_(authorization_ids)
            ).delete(synchronize_session=False)
        AcmeOrder.query.filter_by(
            account_id=acc.account_id).delete(synchronize_session=False)

        # The client order outlives the account: it is an order placed at an
        # external authority, and only the link is dropped. Left pointing at a
        # row that is gone, it is what a database enforcing its foreign keys
        # refuses.
        AcmeClientOrder.query.filter_by(account_id=acc.account_id).update(
            {'account_id': None}, synchronize_session=False)

        db.session.delete(acc)
        db.session.commit()

        AuditService.log_action(
            action='acme.account.delete',
            resource_type='acme_account',
            resource_id=str(account_id),
            details=f'Deleted ACME account: {account_name}'
        )

        return success_response(message=f'Account {account_name} deleted')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete ACME account {account_id}: {e}")
        return error_response('Failed to delete ACME account', 500)
