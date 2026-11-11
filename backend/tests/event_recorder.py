"""Record the certificate events the real bus dispatches during a test."""
import pytest


@pytest.fixture
def events(monkeypatch):
    """List of ``(event_type, certificate id)``; every subscriber still runs."""
    from services.events import event_bus
    seen = []
    real = event_bus.emit

    def record(event_type, payload, ca_refid=None, meta=None):
        seen.append((event_type, ((payload or {}).get('certificate') or {}).get('id')))
        return real(event_type, payload, ca_refid, meta)

    monkeypatch.setattr(event_bus, 'emit', record)
    return seen


def cert_events(seen, *ids):
    """The certificate.* events of *seen* about the rows *ids*."""
    return [(e, cid) for e, cid in seen if e.startswith('certificate.') and cid in ids]
