"""Bindings a protocol renewal left on the previous certificate.

The rule (services.ca.ca_signing._bindings_follow) keeps a binding that pushes the key,
and the HTTPS listener binding, on the old row when the successor has no key in UCM.
Such a binding carries a state, set in the renewal's commit and announced once on the
bus after it; reattachment, removal, or a key reaching the successor clears it.
"""
import logging

from models import db

logger = logging.getLogger(__name__)

EVENT = 'certificate.binding_left_behind'
REASON_SUCCESSOR_WITHOUT_KEY = 'successor_without_key'
# SystemConfig row: refid of the successor the HTTPS listener binding could not follow
HTTPS_LEFT_BEHIND_KEY = 'https_binding_left_behind_for'
_PENDING = 'ucm_bindings_left_behind'


def _pending():
    return db.session.info.setdefault(_PENDING, [])


def mark_deploy(binding, successor):
    binding.attention_reason = REASON_SUCCESSOR_WITHOUT_KEY
    binding.attention_successor_id = successor.id
    _pending().append(('deploy', binding.id, successor.id))


def mark_https(successor):
    from models import SystemConfig
    row = SystemConfig.query.filter_by(key=HTTPS_LEFT_BEHIND_KEY).first()
    if row is None:
        row = SystemConfig(key=HTTPS_LEFT_BEHIND_KEY,
                           description='Renewed certificate the HTTPS binding could not follow')
        db.session.add(row)
    row.value = successor.refid
    _pending().append(('https', None, successor.id))


def https_left_behind_for():
    """Refid of the successor the HTTPS listener binding waits for, or ''."""
    from models import SystemConfig
    row = SystemConfig.query.filter_by(key=HTTPS_LEFT_BEHIND_KEY).first()
    return (row.value or '').strip() if row else ''


def clear_https():
    """Drop the HTTPS state; the caller commits."""
    from models import SystemConfig
    SystemConfig.query.filter_by(key=HTTPS_LEFT_BEHIND_KEY).delete(synchronize_session='fetch')


def clear(binding):
    binding.attention_reason = None
    binding.attention_successor_id = None


def can_reattach(binding):
    """The successor exists and is live, holds the key or the binding sends none, and
    the target has no binding on it yet."""
    from models import DeployBinding
    from services.ca.ca_signing import _pushes_key
    successor = binding.attention_successor
    if successor is None or successor.archived:
        return False
    if not successor.has_private_key and _pushes_key(binding):
        return False
    return not DeployBinding.query.filter_by(
        target_id=binding.target_id, certificate_id=successor.id).count()


def forget_successor(cert):
    """*cert* is being deleted: no binding waits for it any more. The caller commits."""
    from models import DeployBinding
    DeployBinding.query.filter_by(attention_successor_id=cert.id).update(
        {'attention_reason': None, 'attention_successor_id': None}, synchronize_session='fetch')
    if cert.refid and https_left_behind_for() == cert.refid:
        clear_https()


def follow_key(cert, actor='system', queue=True):
    """*cert* now holds its key: the bindings left behind for it follow it, as they would
    have at renewal. Deliveries are queued unless *queue* is False (a renewal event
    deploys them). Returns True when the HTTPS binding moved. The caller commits."""
    from sqlalchemy import select
    from models import Certificate, DeployBinding, DeployDelivery, SystemConfig
    from services.deploy import DeployService
    from services.https_binding import BOUND_REFID_KEY
    if not cert.has_private_key:
        return False
    # The row lock orders us with a renewal of *cert* (its claim archives the row): an
    # archived row's bindings already wait for, or moved to, its successor.
    archived = db.session.execute(select(Certificate.archived).where(Certificate.id == cert.id)
                                  .with_for_update()).scalar()
    if archived:
        return False
    taken = {t for (t,) in db.session.query(DeployBinding.target_id)
             .filter(DeployBinding.certificate_id == cert.id)}
    for binding in (DeployBinding.query.filter_by(attention_successor_id=cert.id)
                    .order_by(DeployBinding.id).with_for_update().populate_existing()):
        clear(binding)
        if binding.target_id in taken:
            continue  # that target already receives the successor
        binding.certificate_id = cert.id
        taken.add(binding.target_id)
        if queue:
            DeployService.enqueue_binding_update(
                binding, DeployDelivery.BINDING_CERTIFICATE, actor=actor)
    awaited = SystemConfig.query.filter_by(key=HTTPS_LEFT_BEHIND_KEY).with_for_update().first()
    if not cert.refid or awaited is None or (awaited.value or '').strip() != cert.refid:
        return False
    clear_https()
    bound = SystemConfig.query.filter_by(key=BOUND_REFID_KEY).with_for_update().first()
    if bound is None:
        return False
    bound.value = cert.refid
    return True


def _snapshot(kind, binding_id, successor_id):
    """The event payload from the committed state, or None when the mark did not last."""
    from models import Certificate, DeployBinding, SystemConfig
    from services.https_binding import BOUND_REFID_KEY
    successor = db.session.get(Certificate, successor_id)
    if successor is None:
        return None
    if kind == 'deploy':
        binding = db.session.get(DeployBinding, binding_id)
        if binding is None or binding.attention_successor_id != successor_id:
            return None
        previous_id = binding.certificate_id
        described = {'type': 'deploy', 'id': binding.id, 'target_id': binding.target_id,
                     'target_name': binding.target.name if binding.target else None}
    else:
        if https_left_behind_for() != successor.refid:
            return None
        row = SystemConfig.query.filter_by(key=BOUND_REFID_KEY).first()
        previous = Certificate.query.filter_by(refid=row.value).first() if row and row.value else None
        previous_id = previous.id if previous else None
        described = {'type': 'https'}
    previous = db.session.get(Certificate, previous_id) if previous_id else None
    return {
        'certificate': successor.to_dict(),
        'previous_certificate': ({'id': previous.id, 'refid': previous.refid, 'descr': previous.descr}
                                 if previous else None),
        'binding': described,
        'reason': REASON_SUCCESSOR_WITHOUT_KEY,
    }


def emit_pending():
    """After the renewal's commit: one event per binding it left behind, never twice."""
    marks = db.session.info.pop(_PENDING, [])
    if not marks:
        return
    from services.webhook_service import _emit
    # A savepoint retried after a serial collision leaves its marks behind: same mark, one event
    for kind, binding_id, successor_id in dict.fromkeys(marks):
        try:
            payload = _snapshot(kind, binding_id, successor_id)
        except Exception as e:  # never break the renewal that already committed
            logger.error(f"Left-behind binding event skipped: {e}")
            continue
        if payload is not None:
            _emit(EVENT, payload, payload['certificate'].get('caref'))
