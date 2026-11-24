"""Certificate metadata update route: the display name and the comment"""
import logging
import unicodedata
from flask import request
from auth.unified import require_auth
from utils.db_transaction import safe_commit
from utils.response import success_response, error_response
from models import Certificate, db
from services.audit_service import AuditService
from . import bp

logger = logging.getLogger(__name__)

COMMENT_MAX_LENGTH = 4000
# Line feed and tab are the only control characters a comment keeps
COMMENT_CONTROLS_ALLOWED = frozenset('\n\t')


# Unicode Bidi_Control (UAX #9): a comment shown in the inspector must read as it is stored
BIDI_CONTROLS = frozenset('\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069')


def _unencodable(value):
    """A lone surrogate (half a UTF-16 pair): no UTF-8 spelling, the database refuses it."""
    try:
        value.encode('utf-8')
    except UnicodeEncodeError:
        return True
    return False


def _descr_error(value):
    if not isinstance(value, str) or not value.strip():
        return 'descr must be a non-empty string'
    if len(value.strip()) > 255:
        return 'descr must be 255 characters or fewer'
    if _unencodable(value):
        return 'descr may not hold a lone surrogate'
    return None


def _comment_error(value):
    if value is None:
        return None
    if not isinstance(value, str):
        return 'comment must be a string or null'
    if len(value) > COMMENT_MAX_LENGTH:
        return f'comment must be {COMMENT_MAX_LENGTH} characters or fewer'
    if any(unicodedata.category(ch) == 'Cc' and ch not in COMMENT_CONTROLS_ALLOWED for ch in value):
        return 'comment may not hold control characters other than line feed and tab'
    if _unencodable(value):
        return 'comment may not hold a lone surrogate'
    if any(ch in BIDI_CONTROLS for ch in value):
        return 'comment may not hold text direction controls'
    return None


@bp.route('/api/v2/certificates/<int:cert_id>', methods=['PATCH'])
@require_auth(['write:certificates'])
def update_certificate(cert_id):
    """Update the display name (descr), the plain-text comment, or both."""
    cert = db.session.get(Certificate, cert_id)
    if not cert:
        return error_response('Certificate not found', 404)

    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not {'descr', 'comment'} & data.keys():
        return error_response('descr or comment is required', 400)

    # Every field is checked before any is written: an invalid one refuses the whole request
    error = ('descr' in data and _descr_error(data['descr'])) or ('comment' in data and _comment_error(data['comment']))
    if error:
        return error_response(error, 400)

    old_descr = cert.descr
    old_comment = cert.comment or ''
    if 'descr' in data:
        cert.descr = data['descr'].strip()
    new_comment = old_comment
    if 'comment' in data:
        # Blanks alone are no comment: stored as none, as an empty text is
        new_comment = data['comment'] if data['comment'] and data['comment'].strip() else ''
        cert.comment = new_comment or None
    ok, err = safe_commit(logger, "Failed to update certificate")
    if not ok:
        return err

    if 'descr' in data:
        AuditService.log_action(
            action='certificate_renamed',
            resource_type='certificate',
            resource_id=cert.id,
            resource_name=cert.descr,
            details=f'Renamed certificate: "{old_descr}" -> "{cert.descr}"',
            success=True
        )
    if new_comment != old_comment:
        # The lengths only: a comment may hold what the audit log should not copy
        verb = 'cleared' if not new_comment else 'changed'
        AuditService.log_action(
            action='certificate_comment_updated',
            resource_type='certificate',
            resource_id=cert.id,
            resource_name=cert.descr,
            details=f'Comment {verb}: {len(old_comment)} -> {len(new_comment)} characters',
            success=True
        )

    from .cert_get import certificate_detail
    return success_response(data=certificate_detail(cert), message='Certificate updated')
