"""Behaviours the 3.0 upgrade notes state that no other test pins: discovery dates in UTC,
the activity feed failing loudly, expiry webhooks caught up after a stop, and the
connections a PostgreSQL deployment without Redis opens."""
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy import text as sql_text

from models import Certificate, SystemConfig, db
from utils.datetime_utils import utc_now


# --- Discovery: dates stored in naive UTC ---------------------------------------------------

def test_a_discovered_date_with_an_offset_is_stored_in_utc():
    from services.discovery.helpers import _parse_iso
    parsed = _parse_iso('2026-01-01T12:00:00+02:00')
    assert parsed == datetime(2026, 1, 1, 10, 0) and parsed.tzinfo is None
    aware = datetime.fromisoformat('2026-01-01T12:00:00+02:00')
    assert _parse_iso(aware) == datetime(2026, 1, 1, 10, 0)


# --- Dashboard activity: an error is an error -----------------------------------------------

def test_an_unreadable_audit_log_answers_500_not_an_empty_feed(auth_client, monkeypatch):
    import api.v2.dashboard as dashboard
    monkeypatch.setattr(dashboard, 'text', lambda _sql: sql_text('SELECT * FROM no_such_audit_table'))

    response = auth_client.get('/api/v2/dashboard/activity')

    assert response.status_code == 500, response.data
    assert 'Activity log unavailable' in response.get_data(as_text=True)


def test_a_readable_audit_log_still_answers_its_feed(auth_client):
    response = auth_client.get('/api/v2/dashboard/activity')
    assert response.status_code == 200, response.data
    assert isinstance(response.get_json()['data']['activity'], list)


# --- Expiry webhooks: from the last pass, at most 30 days back -------------------------------

@pytest.fixture
def expiry_bench(app, monkeypatch):
    """Certificates expired at chosen ages, the webhook mark saved and restored, emissions recorded."""
    from services.notification.scheduler import EXPIRY_WEBHOOKS_MARK_KEY
    import services.webhook_service as webhook_service
    announced, made = [], []
    monkeypatch.setattr(webhook_service, 'emit_cert_expired',
                        lambda cert, **_kw: announced.append(cert.get('id')))
    monkeypatch.setattr(webhook_service, 'emit_cert_expiring', lambda *_a, **_kw: None)
    with app.app_context():
        row = SystemConfig.query.filter_by(key=EXPIRY_WEBHOOKS_MARK_KEY).first()
        saved = row.value if row is not None else None

        def expired(age):
            now = utc_now()
            cert = Certificate(refid=str(uuid.uuid4()), descr=f'expiry-{uuid.uuid4().hex[:6]}',
                               valid_from=now - timedelta(days=400), valid_to=now - age, revoked=False)
            db.session.add(cert)
            db.session.commit()
            made.append(cert.id)
            return cert.id

        def mark(value):
            row = SystemConfig.query.filter_by(key=EXPIRY_WEBHOOKS_MARK_KEY).first()
            if value is None:
                if row is not None:
                    db.session.delete(row)
            elif row is None:
                db.session.add(SystemConfig(key=EXPIRY_WEBHOOKS_MARK_KEY, value=value.isoformat()))
            else:
                row.value = value.isoformat()
            db.session.commit()

        yield SimpleNamespace(expired=expired, mark=mark, announced=announced)
        Certificate.query.filter(Certificate.id.in_(made)).delete(synchronize_session=False)
        db.session.commit()
        mark(datetime.fromisoformat(saved) if saved else None)


def _pass():
    from services.notification.scheduler import _emit_webhooks_single_node
    _emit_webhooks_single_node()


def test_a_stop_of_days_announces_what_expired_meanwhile_up_to_a_month(expiry_bench):
    two_days = expiry_bench.expired(timedelta(days=2))
    ten_days = expiry_bench.expired(timedelta(days=10))
    forty_days = expiry_bench.expired(timedelta(days=40))
    expiry_bench.mark(utc_now() - timedelta(days=50))

    _pass()

    assert two_days in expiry_bench.announced and ten_days in expiry_bench.announced
    assert forty_days not in expiry_bench.announced


def test_without_a_mark_only_the_last_day_is_announced_and_never_twice(expiry_bench):
    recent = expiry_bench.expired(timedelta(hours=12))
    older = expiry_bench.expired(timedelta(days=2))
    expiry_bench.mark(None)

    _pass()
    _pass()

    assert expiry_bench.announced.count(recent) == 1
    assert older not in expiry_bench.announced


# --- PostgreSQL without Redis: the connections a process opens -------------------------------

def test_the_session_store_opens_a_pool_of_its_own_with_the_application_options(app, tmp_path):
    from utils.session_store import IsolatedSqlSessionInterface
    main = create_engine(f'sqlite:///{tmp_path / "sessions.db"}')
    store = IsolatedSqlSessionInterface.__new__(IsolatedSqlSessionInterface)
    store.client = SimpleNamespace(engine=main)
    try:
        with app.app_context():
            app.config['SQLALCHEMY_ENGINE_OPTIONS'], kept = (
                {'pool_size': 7, 'max_overflow': 3}, app.config.get('SQLALCHEMY_ENGINE_OPTIONS'))
            try:
                own = store._engine()
            finally:
                app.config['SQLALCHEMY_ENGINE_OPTIONS'] = kept
        assert own is not main
        assert own.pool.size() == 7 and own.pool._max_overflow == 3
    finally:
        main.dispose()
        cached = getattr(store, '_own_engine', None)
        if cached is not None:
            cached[1].dispose()


def test_each_web_worker_listens_for_events_on_postgresql_without_a_queue(app, monkeypatch):
    from services import ws_relay
    from websocket import events
    import utils.ha
    opened = []

    class Wakeup:
        def __init__(self, url):
            opened.append(url)

    class Reader:
        def __init__(self, engine, deliver, skip_origin=None, wakeup=None):
            self.wakeup = wakeup

        def start(self):
            return self

    engine = SimpleNamespace(dialect=SimpleNamespace(name='postgresql'), url='postgresql://db.invalid/ucm')
    monkeypatch.setattr(ws_relay, '_reader', None)
    monkeypatch.setattr(ws_relay, '_engine', lambda _app: engine)
    monkeypatch.setattr(ws_relay, 'PgWakeup', Wakeup)
    monkeypatch.setattr(ws_relay, 'RelayReader', Reader)
    monkeypatch.setattr(events, 'message_queue_in_use', lambda: False)
    monkeypatch.setattr(utils.ha, 'ha_enabled', lambda: False)

    reader = ws_relay.start_reader(app)

    assert opened == [engine.url] and isinstance(reader.wakeup, Wakeup)
    monkeypatch.setattr(ws_relay, '_reader', None)
