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
