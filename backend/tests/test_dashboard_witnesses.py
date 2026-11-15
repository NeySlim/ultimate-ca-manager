"""GET /api/v2/dashboard/health also carries the mail, webhook and auto-renewal witnesses of the
2.x home page, each only for a caller who may read the setting it reveals."""
import pytest

from models import SystemConfig, db
from models.email_notification import SMTPConfig
from services import dashboard_aggregates as agg
from services.webhook_service import WebhookEndpoint
from tests.conftest import get_json

URL = '/api/v2/dashboard/health'


@pytest.fixture
def settings(app):
    """Mail, webhooks and the renewal switch emptied for the test, and again after it."""
    def clear():
        with app.app_context():
            SMTPConfig.query.delete()
            WebhookEndpoint.query.delete()
            SystemConfig.query.filter_by(key='auto_renewal_enabled').delete()
            db.session.commit()
    clear()

    def put(smtp=None, webhooks=(), renewal=None):
        with app.app_context():
            if smtp is not None:
                db.session.add(SMTPConfig(**smtp))
            for i, enabled in enumerate(webhooks):
                db.session.add(WebhookEndpoint(name=f'witness-{i}', url='https://hook.example.com/x', enabled=enabled))
            if renewal is not None:
                db.session.add(SystemConfig(key='auto_renewal_enabled', value=renewal))
            db.session.commit()
    yield put
    clear()


def _witnesses(app, permissions=None):
    with app.app_context():
        protocols = agg.protocol_health(db.session, 7, permissions=permissions)['protocols']
    return {k: protocols.get(k) for k in ('smtp', 'webhooks', 'auto_renewal')}


def _brief(w):
    return None if w is None else (w['state'], w['alert'])


READY = dict(smtp_host='mail.example.com', smtp_port=587, smtp_from='ucm@example.com', enabled=True)


@pytest.mark.parametrize('smtp, expected', [
    (None, ('not_configured', False)),
    (dict(smtp_host='', enabled=True), ('not_configured', False)),
    ({**READY, 'enabled': False}, ('disabled', True)),
    ({**READY, 'smtp_from': ''}, ('incomplete', True)),
    ({**READY, 'smtp_port': 0}, ('incomplete', True)),
    (READY, ('ready', False)),
])
def test_smtp_states(app, settings, smtp, expected):
    settings(smtp=smtp)
    assert _brief(_witnesses(app)['smtp']) == expected


@pytest.mark.parametrize('hooks, expected, count', [
    ((), ('not_configured', False), 0),
    ((False, False), ('none_active', True), 2),
    ((True, False), ('active', False), 1),
])
def test_webhook_states(app, settings, hooks, expected, count):
    settings(webhooks=hooks)
    w = _witnesses(app)['webhooks']
    assert _brief(w) == expected and w['count'] == count


@pytest.mark.parametrize('renewal, expected', [
    (None, ('disabled', False)), ('false', ('disabled', False)), ('true', ('enabled', False)),
])
def test_auto_renewal_states(app, settings, renewal, expected):
    settings(renewal=renewal)
    assert _brief(_witnesses(app)['auto_renewal']) == expected


def test_no_permission_no_witness(app, settings):
    settings(smtp=READY, webhooks=(True,), renewal='true')
    assert _witnesses(app, ['read:dashboard']) == {'smtp': None, 'webhooks': None, 'auto_renewal': None}


@pytest.mark.parametrize('witness', ['smtp', 'webhooks', 'auto_renewal'])
def test_each_witness_follows_its_own_permission(app, settings, monkeypatch, witness):
    settings(smtp=READY, webhooks=(True,), renewal='true')
    monkeypatch.setitem(agg.WITNESS_PERMISSION, witness, 'read:witness_only')
    seen = _witnesses(app, ['read:dashboard', 'read:settings'])
    assert {k: v is not None for k, v in seen.items()} == {k: k != witness for k in seen}
    assert _witnesses(app, ['read:dashboard', 'read:witness_only'])[witness] is not None


def test_the_route_serves_admin_and_withholds_from_a_scoped_key(app, auth_client, settings):
    settings(smtp=READY, webhooks=(True,), renewal='true')
    full = get_json(auth_client.get(URL))['data']['protocols']
    assert (full['smtp']['state'], full['webhooks']['state'], full['auto_renewal']['state']) == ('ready', 'active', 'enabled')
    r = auth_client.post('/api/v2/account/apikeys', json={'name': 'health-no-settings', 'permissions': ['read:dashboard']})
    assert r.status_code == 201, r.data
    key = get_json(r)['data']
    try:
        r = app.test_client().get(URL, headers={'X-API-Key': key['key']})
        assert r.status_code == 200, r.data
        protocols = get_json(r)['data']['protocols']
        assert not {'smtp', 'webhooks', 'auto_renewal'} & set(protocols)
        assert 'acme' in protocols
    finally:
        auth_client.delete(f"/api/v2/account/apikeys/{key['id']}")


def test_legacy_system_status_withholds_the_witnesses_from_a_key_without_read_settings(app, auth_client, settings):
    settings(smtp=READY, webhooks=(True,), renewal='true')
    legacy = '/api/v2/dashboard/system-status'
    r = auth_client.post('/api/v2/account/apikeys', json={'name': 'legacy-no-settings', 'permissions': ['read:certificates']})
    assert r.status_code == 201, r.data
    key = get_json(r)['data']
    try:
        r = app.test_client().get(legacy, headers={'X-API-Key': key['key']})
        assert r.status_code == 200, r.data
        data = get_json(r)['data']
        assert not {'smtp', 'webhooks', 'auto_renewal'} & set(data)
        assert 'mail.example.com' not in r.get_data(as_text=True)
    finally:
        auth_client.delete(f"/api/v2/account/apikeys/{key['id']}")
    full = get_json(auth_client.get(legacy))['data']
    assert {'smtp', 'webhooks', 'auto_renewal'} <= set(full)


@pytest.mark.parametrize('witness', ['smtp', 'webhooks', 'auto_renewal'])
def test_a_failing_witness_reads_unavailable_and_alerts(app, settings, monkeypatch, caplog, witness):
    def boom():
        raise RuntimeError('db password=hunter2')
    monkeypatch.setitem(agg._WITNESSES, witness, boom)
    with caplog.at_level('WARNING', logger=agg.logger.name):
        seen = _witnesses(app)
    assert _brief(seen[witness]) == ('unavailable', True)
    assert all(v is not None for v in seen.values())
    warned = [r for r in caplog.records if r.levelname == 'WARNING' and witness in r.getMessage()]
    assert warned and 'hunter2' not in caplog.text


LEGACY = '/api/v2/dashboard/system-status'
SCENARIOS = [
    ('smtp', dict(), 'not_configured', 'offline'),
    ('smtp', dict(smtp={**READY, 'enabled': False}), 'disabled', 'warning'),
    ('smtp', dict(smtp={**READY, 'smtp_port': 0}), 'incomplete', 'warning'),
    ('smtp', dict(smtp=READY), 'ready', 'online'),
    ('webhooks', dict(), 'not_configured', 'offline'),
    ('webhooks', dict(webhooks=(False, False)), 'none_active', 'warning'),
    ('webhooks', dict(webhooks=(True, False)), 'active', 'online'),
    ('auto_renewal', dict(), 'disabled', 'offline'),
    ('auto_renewal', dict(renewal='true'), 'enabled', 'online'),
]


@pytest.mark.parametrize('witness, setup, state, status', SCENARIOS)
def test_both_routes_rule_each_witness_the_same(app, auth_client, settings, witness, setup, state, status):
    settings(**setup)
    health = get_json(auth_client.get(URL))['data']['protocols'][witness]
    legacy = get_json(auth_client.get(LEGACY))['data'][witness]
    assert health['state'] == state
    assert legacy['status'] == status and isinstance(legacy['message'], str)


@pytest.mark.parametrize('witness', ['smtp', 'webhooks', 'auto_renewal'])
def test_both_routes_say_unavailable_when_a_witness_cannot_be_read(app, auth_client, settings, monkeypatch, witness):
    def boom():
        raise RuntimeError('unreadable')
    monkeypatch.setitem(agg._WITNESSES, witness, boom)
    assert get_json(auth_client.get(URL))['data']['protocols'][witness]['state'] == 'unavailable'
    legacy = get_json(auth_client.get(LEGACY))['data'][witness]
    assert legacy == {'status': 'warning', 'message': 'Status unavailable'}


class _Unreadable:
    """A model query that answers *good* times, then fails like a lost connection."""
    def __init__(self, real, good):
        self.real, self.good = real, good

    def __getattr__(self, name):
        if self.good <= 0:
            raise RuntimeError('unreadable')
        self.good -= 1
        return getattr(self.real, name)


def test_legacy_route_keeps_the_state_when_the_smtp_host_cannot_be_read(app, auth_client, settings, monkeypatch):
    from models.email_notification import SMTPConfig
    settings(smtp=READY)
    with app.app_context(), monkeypatch.context() as patch:
        patch.setattr(SMTPConfig, 'query', _Unreadable(SMTPConfig.query, 1))
        r = auth_client.get(LEGACY)
    assert r.status_code == 200
    assert get_json(r)['data']['smtp'] == {'status': 'online', 'message': 'Configured'}


def test_legacy_route_keeps_the_state_when_the_pending_renewals_cannot_be_read(app, auth_client, settings, monkeypatch, caplog):
    from models import Certificate
    settings(renewal='true')
    with app.app_context(), monkeypatch.context() as patch:
        patch.setattr(Certificate, 'query', _Unreadable(Certificate.query, 0))
        import api.v2.dashboard as route
        resets = []
        patch.setattr(route, '_status_rollback', lambda: resets.append(1) or db.session.rollback())
        with caplog.at_level('DEBUG', logger=route.__name__):
            r = auth_client.get(LEGACY)
    assert 'legacy status detail unreadable' in caplog.text
    assert resets, 'a failed read must reset the session: on PostgreSQL the next statement would fail'
    assert r.status_code == 200
    assert get_json(r)['data']['auto_renewal'] == {'status': 'online', 'message': 'Scheduled'}
