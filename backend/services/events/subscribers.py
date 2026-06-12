"""Bus subscribers that adapt domain events to the email and WebSocket
notification systems.

These are thin adapters: they extract what each existing handler needs from
the event payload (re-querying the model by id for email, which renders from
the model object) and call the *unchanged* NotificationService / WebSocket
emitter functions. This lets lifecycle code emit ONE event instead of calling
three notification systems by hand.
"""
import logging

logger = logging.getLogger(__name__)


def _cert(payload):
    return (payload or {}).get('certificate') or {}


def _ca(payload):
    return (payload or {}).get('ca') or {}


def email_subscriber(event_type, payload, ca_refid, meta):
    """Send email notifications for the events email currently supports."""
    from services.notification import NotificationService
    from models import Certificate, CA
    actor = (meta or {}).get('actor')

    if event_type == 'certificate.issued':
        cid = _cert(payload).get('id')
        cert = Certificate.query.get(cid) if cid else None
        if cert:
            NotificationService.on_certificate_issued(cert, actor)
    elif event_type == 'certificate.revoked':
        cid = _cert(payload).get('id')
        cert = Certificate.query.get(cid) if cid else None
        if cert:
            NotificationService.on_certificate_revoked(cert, (meta or {}).get('reason'), actor)
    elif event_type == 'ca.created':
        cid = _ca(payload).get('id')
        ca = CA.query.get(cid) if cid else None
        if ca:
            NotificationService.on_ca_created(ca, actor)


def ws_subscriber(event_type, payload, ca_refid, meta):
    """Push live WebSocket updates for cert/CA lifecycle events."""
    from websocket import emitters as ws
    actor = (meta or {}).get('actor')
    c = _cert(payload)
    a = _ca(payload)

    if event_type == 'certificate.issued':
        ws.on_certificate_issued(c.get('id'), c.get('subject') or c.get('descr'),
                                 c.get('caref'), c.get('issuer'), c.get('valid_to'))
    elif event_type == 'certificate.revoked':
        ws.on_certificate_revoked(c.get('id'), c.get('subject') or c.get('descr'),
                                  (meta or {}).get('reason'), actor)
    elif event_type == 'certificate.renewed':
        ws.on_certificate_renewed(c.get('id'), c.get('id'), c.get('subject') or c.get('descr'))
    elif event_type == 'certificate.deleted':
        ws.on_certificate_deleted(c.get('id'), c.get('subject') or c.get('descr'), actor)
    elif event_type == 'ca.created':
        ws.on_ca_created(a.get('id'), a.get('descr'), a.get('descr'), actor)
    elif event_type == 'ca.updated':
        ws.on_ca_updated(a.get('id'), a.get('descr'), (meta or {}).get('changes') or {})
    elif event_type == 'ca.deleted':
        ws.on_ca_deleted(a.get('id'), a.get('descr'), actor)


_EMAIL_EVENTS = ('certificate.issued', 'certificate.revoked', 'ca.created')
_WS_EVENTS = ('certificate.issued', 'certificate.revoked', 'certificate.renewed',
              'certificate.deleted', 'ca.created', 'ca.updated', 'ca.deleted')


def register_notification_subscribers():
    """Wire email + WebSocket subscribers onto the bus (idempotent)."""
    from services.events import event_bus
    if getattr(register_notification_subscribers, '_done', False):
        return
    for ev in _EMAIL_EVENTS:
        event_bus.subscribe(ev, email_subscriber)
    for ev in _WS_EVENTS:
        event_bus.subscribe(ev, ws_subscriber)
    register_notification_subscribers._done = True
    logger.info("Registered email + WebSocket event-bus subscribers")
