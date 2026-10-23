"""Account request rules shared by the ACME server and the ACME proxy (RFC 8555 §7.3)."""
import base64
import json
import logging
from typing import Any, Dict, Optional, Tuple

from models import db

logger = logging.getLogger(__name__)

NOT_AN_OBJECT = "The request payload is not a JSON object"
CLOSED_ACCOUNT = "This ACME account is not valid"


class AccountRequestError(Exception):
    """An ACME problem (error type, detail, HTTP status) for an account request."""

    def __init__(self, error_type: str, detail: str, status: int = 400):
        super().__init__(detail)
        self.error_type = error_type
        self.detail = detail
        self.status = status


def validate_contact_uris(contact: Any) -> Tuple[bool, Optional[str], Optional[str]]:
    """Validate RFC 8555 account contact URIs supported by this server."""
    if not isinstance(contact, list):
        return False, 'invalidContact', 'Contact must be an array of mailto URIs'

    for contact_uri in contact:
        if not isinstance(contact_uri, str):
            return False, 'invalidContact', 'Contact URI must be a string'
        scheme, separator, target = contact_uri.partition(':')
        if not separator or scheme.lower() != 'mailto':
            return False, 'unsupportedContact', 'Only mailto contact URIs are supported'

        address = target.split('?', 1)[0]
        if (
            not address
            or address.count('@') != 1
            or any(character.isspace() for character in address)
        ):
            return False, 'invalidContact', 'Malformed mailto contact URI'
        local_part, domain = address.rsplit('@', 1)
        if (
            not local_part
            or not domain
            or domain.startswith('.')
            or domain.endswith('.')
            or '..' in domain
        ):
            return False, 'invalidContact', 'Malformed mailto contact URI'

    return True, None, None


def _contact(payload: Dict[str, Any]) -> list:
    contact = payload.get('contact')
    if contact is None:
        return []
    valid, error_type, detail = validate_contact_uris(contact)
    if not valid:
        raise AccountRequestError(error_type, detail)
    return contact


def _boolean(payload: Dict[str, Any], field: str) -> bool:
    """A boolean field; JSON null counts as absent."""
    value = payload.get(field)
    if value is None:
        return False
    if not isinstance(value, bool):
        raise AccountRequestError('malformed', f'{field} must be a boolean')
    return value


def parse_new_account(payload: Any) -> Dict[str, Any]:
    """Validated newAccount fields (RFC 8555 §7.3); raises AccountRequestError."""
    if not isinstance(payload, dict):
        raise AccountRequestError('malformed', NOT_AN_OBJECT)
    return {
        'contact': _contact(payload),
        'terms_of_service_agreed': _boolean(payload, 'termsOfServiceAgreed'),
        'only_return_existing': _boolean(payload, 'onlyReturnExisting'),
        'external_account_binding': payload.get('externalAccountBinding'),
    }


def require_valid_account(account) -> None:
    """RFC 8555 §7.3.6: a deactivated or revoked account is refused, never served."""
    if account.status != 'valid':
        raise AccountRequestError('unauthorized', closed_account_detail(account), 401)


def closed_account_detail(account) -> str:
    return f'{CLOSED_ACCOUNT} (status: {account.status})'


def consume_eab(service, eab_data: Dict[str, Any], account) -> None:
    """Consume the single-use EAB credential of a just-created account (RFC 8555 §7.3.4).

    If another registration won the credential, the unbound account is removed."""
    protected_b64 = eab_data['protected']
    protected = json.loads(base64.urlsafe_b64decode(protected_b64 + '=' * (-len(protected_b64) % 4)))
    eab_kid = protected.get('kid', '')
    if eab_kid and service.mark_eab_used(eab_kid, account.account_id):
        return
    try:
        db.session.delete(account)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f'Failed to remove account after EAB race: {e}')
        raise AccountRequestError('serverInternal', 'Internal server error', 500)
    raise AccountRequestError('malformed', 'External account binding credential is no longer usable')


def apply_account_update(account, payload: Any) -> bool:
    """Apply an account update (RFC 8555 §7.3.2, §7.3.6) without committing.

    An empty payload is a POST-as-GET. Returns whether the account changed."""
    if payload in (None, {}):
        return False
    if not isinstance(payload, dict):
        raise AccountRequestError('malformed', NOT_AN_OBJECT)
    # Validate everything before touching the account. Any status other than
    # "deactivated" is ignored, like unknown fields (§7.3.2): clients echo "valid".
    contact = _contact(payload) if 'contact' in payload else None
    deactivate = payload.get('status') == 'deactivated'
    if deactivate:
        account.status = 'deactivated'
    if contact is not None:
        account.contact = json.dumps(contact)
    return deactivate or contact is not None
