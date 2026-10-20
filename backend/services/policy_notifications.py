"""E-mail the recipients of a policy (notify_on_violation) when it refuses an
operation or queues one for approval. Never carries key material or secrets."""
import hashlib
import html
import json
import logging
import threading
import time
from datetime import timedelta

logger = logging.getLogger(__name__)

VIOLATION = 'policy_violation'
APPROVAL_PENDING = 'policy_approval_pending'
# A client retrying the same refused request is told once per window
DEDUP_WINDOW = timedelta(hours=1)
MAX_RECIPIENTS = 50

_recent = {}
_recent_lock = threading.Lock()

_OPERATION_LABELS = {
    'issuance': 'Issuance', 'renewal': 'Renewal', 'revocation': 'Revocation',
    'certificate': 'Issuance', 'csr': 'CSR signing',
    'ca_revocation': 'CA revocation', 'ca_creation': 'CA creation',
}


def validated_emails(value):
    """``(emails, error)``: a list of distinct mailbox addresses, or the reason
    it is refused."""
    from services.email_service import EmailService
    if value in (None, ''):
        return [], None
    if not isinstance(value, list):
        return None, 'notification_emails must be a list of e-mail addresses'
    emails = []
    for item in value:
        addr = item.strip() if isinstance(item, str) else None
        if not addr or not EmailService._is_valid_address(addr) or any(c in addr for c in '\r\n,;<>"'):
            return None, f'Invalid e-mail address: {item!r}'
        if addr.lower() not in (e.lower() for e in emails):
            emails.append(addr)
    if len(emails) > MAX_RECIPIENTS:
        return None, f'At most {MAX_RECIPIENTS} notification addresses'
    return emails, None


def recipients(policy) -> list:
    """The policy's own addresses, else the e-mails of its approvers: the
    members of its approval group, or without one every user who may approve."""
    try:
        own = json.loads(policy.notification_emails) if policy.notification_emails else []
    except (TypeError, ValueError):
        own = []
    own, _err = validated_emails(own if isinstance(own, list) else [])
    if own:
        return own
    from auth.permissions import get_effective_permissions
    from auth.unified import has_permission
    from models import User
    if policy.approval_group_id:
        from models.group import GroupMember
        users = User.query.join(GroupMember, GroupMember.user_id == User.id).filter(
            GroupMember.group_id == policy.approval_group_id).all()
    else:
        users = User.query.all()
    found = []
    for user in users:
        if not user.active or not user.email or user.email in found:
            continue
        if has_permission('write:approvals', get_effective_permissions(user)):
            found.append(user.email)
    return found[:MAX_RECIPIENTS]


def _current_requester():
    try:
        from flask import g, has_request_context, request
        if not has_request_context():
            return None
        user = getattr(g, 'current_user', None)
        if user is not None and getattr(user, 'username', None):
            return user.username
        return f'unauthenticated client ({request.path.split("/")[1] or "/"})'
    except Exception:
        return None


def violation(policies, reasons_by_policy: dict, context: dict = None):
    """Report refused rules: one message per policy and refusal, the repeats of
    the same refusal within DEDUP_WINDOW dropped."""
    context = dict(context or {})
    context.setdefault('requester', _current_requester())
    for policy in policies:
        reasons = reasons_by_policy.get(id(policy))
        if not reasons or not getattr(policy, 'notify_on_violation', False):
            continue
        if getattr(policy, 'id', None) is None:
            continue  # system policies (FIPS) have nobody to tell
        # created_at tells a policy apart from a deleted one whose id SQLite reused
        key = hashlib.sha256(json.dumps(
            [policy.id, context.get('operation'), context.get('subject'), sorted(reasons),
             getattr(policy, 'created_at', None)], default=str).encode()).hexdigest()[:32]
        _dispatch(policy.id, VIOLATION, f'{policy.id}:{key}', {
            'operation': context.get('operation') or 'issuance',
            'subject': context.get('subject'),
            'ca': context.get('ca') or _ca_name(context.get('ca_id')),
            'requester': context.get('requester'),
            'reasons': list(reasons),
        })


def approval_queued(policy, approval, request_data: dict):
    """Report an operation held for approval, once per request."""
    if not getattr(policy, 'notify_on_violation', False):
        return
    data = request_data or {}
    subject = data.get('cn') or data.get('target_ca_name')
    if data.get('serial_number'):
        subject = f"{subject or ''} (serial {data['serial_number']})".strip()
    requester = data.get('requested_by') or (approval.requester.username if approval.requester else None)
    # The id alone may be one SQLite reused from a deleted request
    born = approval.created_at.strftime('%Y%m%d%H%M%S%f') if approval.created_at else ''
    _dispatch(policy.id, APPROVAL_PENDING, f'approval:{approval.id}:{born}', {
        'operation': approval.request_type,
        'subject': subject,
        'ca': _ca_name(data.get('ca_id')),
        'requester': requester or _current_requester(),
        'reasons': [r for r in (data.get('reason'), approval.requester_comment) if r],
        'approval_id': approval.id,
        'link': _approvals_link(approval.id),
    })


def _ca_name(ca_id):
    if ca_id is None:
        return None
    try:
        from models import CA, db
        ca = db.session.get(CA, int(ca_id))
        return (ca.common_name or ca.descr) if ca is not None else None
    except Exception:
        return None


def _claim(key) -> bool:
    now = time.monotonic()
    with _recent_lock:
        for k in [k for k, t in _recent.items() if now - t > DEDUP_WINDOW.total_seconds()]:
            del _recent[k]
        if key in _recent:
            return False
        _recent[key] = now
        return True


def _release(key):
    with _recent_lock:
        _recent.pop(key, None)


def _dispatch(policy_id, kind, resource_id, details):
    if not _claim((kind, resource_id)):
        return
    from flask import current_app
    app = current_app._get_current_object()
    if app.config.get('TESTING'):
        # Inline on the caller's session (a single shared connection in tests)
        if not _send(policy_id, kind, resource_id, details, own_session=False):
            _release((kind, resource_id))
        return

    def run():
        with app.app_context():
            # A failed attempt leaves the next refusal free to try again
            if not _send(policy_id, kind, resource_id, details, own_session=True):
                _release((kind, resource_id))
    # Its own thread and session: the caller's transaction is never committed here
    threading.Thread(target=run, name=f'policy-notify-{policy_id}', daemon=True).start()


def _recently_logged(kind, resource_id, exclude_id=None):
    from models.email_notification import NotificationLog
    from utils.datetime_utils import utc_now
    # Sent, or being sent by another worker: a failed attempt does not count
    query = NotificationLog.query.filter(
        NotificationLog.type == kind, NotificationLog.resource_type == 'policy',
        NotificationLog.resource_id == resource_id,
        NotificationLog.status.in_(('sent', 'pending')),
        NotificationLog.sent_at >= utc_now() - DEDUP_WINDOW)
    if exclude_id is not None:
        query = query.filter(NotificationLog.id != exclude_id)
    return query.first() is not None


def _claim_in_db(kind, resource_id, recipients_label):
    """Record the notification before sending it; the id of that record, or
    None when another worker's falls in the window. The insert holds the
    SQLite write lock and PostgreSQL takes an advisory lock, so of two
    workers checking at once the second sees the first."""
    from sqlalchemy import text
    from models import db
    from models.email_notification import NotificationLog
    from utils.datetime_utils import utc_now
    if db.engine.dialect.name == 'postgresql':
        lock = int(hashlib.sha256(f'{kind}:{resource_id}'.encode()).hexdigest()[:15], 16)
        db.session.execute(text('SELECT pg_advisory_xact_lock(:k)'), {'k': lock})
    claim = NotificationLog(type=kind, recipient=recipients_label[:255], status='pending',
                            resource_type='policy', resource_id=resource_id, sent_at=utc_now())
    db.session.add(claim)
    db.session.flush()
    if _recently_logged(kind, resource_id, exclude_id=claim.id):
        db.session.rollback()
        return None
    db.session.commit()
    return claim.id


def _send(policy_id, kind, resource_id, details, *, own_session) -> bool:
    """True once the recipients are told, by this call or another worker."""
    from models import db
    from models.email_notification import NotificationLog
    from models.policy import CertificatePolicy
    from services.email_service import EmailService
    try:
        if not own_session and _recently_logged(kind, resource_id):
            return True
        policy = db.session.get(CertificatePolicy, policy_id)
        if policy is None:
            return False
        to = recipients(policy)
        if not to:
            logger.info("Policy %s: nobody to notify (%s)", policy.name, kind)
            return False
        subject, body = _render(policy, kind, details)
        claim_id = _claim_in_db(kind, resource_id, ', '.join(to)) if own_session else None
        if own_session and claim_id is None:
            return True  # another worker told them already
        ok, _msg = EmailService.send_email(recipients=to, subject=subject, body_html=body,
                                           notification_type=kind, resource_type='policy',
                                           resource_id=resource_id, release_session=own_session)
        if claim_id is not None:
            # The service logged the outcome per recipient; the claim has served
            NotificationLog.query.filter_by(id=claim_id).delete()
            db.session.commit()
        return ok
    except Exception as e:  # a notification never fails the operation
        if own_session:
            db.session.rollback()
        logger.warning("Policy notification failed: %s", e)
        return False


def _render(policy, kind, details):
    from services.notification.templates import NotificationTemplatesMixin
    e = lambda v: html.escape(str(v)) if v not in (None, '') else '-'  # noqa: E731
    operation = _OPERATION_LABELS.get(details.get('operation'), details.get('operation'))
    rows = [('Policy', policy.name), ('Operation', operation),
            ('Certificate / CA', details.get('subject')), ('Issuing CA', details.get('ca')),
            ('Requested by', details.get('requester'))]
    link = None
    if kind == APPROVAL_PENDING:
        title = 'Approval required'
        intro = 'An operation is waiting for approval under this policy.'
        subject = f"UCM: approval required ({operation}) - {details.get('subject') or policy.name}"
        rows.append(('Request', f"#{details['approval_id']}"))
        link = details.get('link')
    else:
        title = 'Policy violation'
        intro = 'An operation was refused because it breaks the rules of this policy.'
        subject = f"UCM: policy violation ({operation}) - {policy.name}"
    reasons = ''.join(f'<li>{e(r)}</li>' for r in details.get('reasons') or [])
    table = ''.join(f'<tr><td style="padding:6px;font-weight:bold;">{label}:</td>'
                    f'<td style="padding:6px;">{e(value)}</td></tr>' for label, value in rows)
    content = (f'<p>{intro}</p><table style="width:100%;border-collapse:collapse;">{table}</table>'
               + (f'<p><strong>Reason:</strong></p><ul>{reasons}</ul>' if reasons else '')
               + (f'<p><a href="{e(link)}">Open the request</a></p>' if link else ''))
    color = '#d97706' if kind == APPROVAL_PENDING else '#dc2626'
    return subject.replace('\r', ' ').replace('\n', ' '), \
        NotificationTemplatesMixin._base_template(title, color, content)


def _approvals_link(approval_id):
    try:
        from utils.public_endpoints import get_admin_canonical_origin
        origin = get_admin_canonical_origin()
    except Exception:
        origin = None
    if not origin:
        try:
            from flask import has_request_context, request
            origin = request.host_url.rstrip('/') if has_request_context() else None
        except Exception:
            origin = None
    return f"{origin or ''}/approvals?id={int(approval_id)}"
