"""The state of every CA's SCEP challenge, listed without the secret and without an audited read."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from models import SystemConfig, User, db
from models.audit_log import AuditLog

SECRET = 'state-list-secret-never-shown'

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


def _set(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if row is None:
        db.session.add(SystemConfig(key=key, value=value))
    else:
        row.value = value


@pytest.fixture
def challenge_cas(app, create_ca):
    tag = uuid.uuid4().hex[:8]
    fresh, old, legacy, bare = (create_ca(cn=f'SCEP state {name} CA {tag}') for name in ('fresh', 'expired', 'legacy', 'bare'))
    now = datetime.now(timezone.utc)
    keys = []
    with app.app_context():
        for ca, stamp in ((fresh, now - timedelta(hours=1)), (old, now - timedelta(hours=30)), (legacy, None)):
            _set(f'scep_challenge_{ca["id"]}', SECRET)
            keys.append(f'scep_challenge_{ca["id"]}')
            if stamp:
                _set(f'scep_challenge_{ca["id"]}_generated_at', stamp.isoformat())
                keys.append(f'scep_challenge_{ca["id"]}_generated_at')
        _set('scep_challenge_validity', '24')
        keys.append('scep_challenge_validity')
        db.session.commit()
    yield {'fresh': fresh['id'], 'old': old['id'], 'legacy': legacy['id'], 'bare': bare['id']}
    with app.app_context():
        SystemConfig.query.filter(SystemConfig.key.in_(keys)).delete(synchronize_session=False)
        db.session.commit()


def _reads(app):
    with app.app_context():
        return AuditLog.query.filter_by(action='scep_challenge_read').count()


def _states(client):
    r = client.get('/api/v2/scep/challenges')
    assert r.status_code == 200, r.data
    return {row['ca_id']: row for row in r.get_json()['data']}


def test_the_list_gives_each_state_without_the_secret(app, auth_client, challenge_cas):
    r = auth_client.get('/api/v2/scep/challenges')
    assert r.status_code == 200
    assert SECRET not in r.get_data(as_text=True)
    states = _states(auth_client)
    fresh, old = states[challenge_cas['fresh']], states[challenge_cas['old']]
    assert fresh['configured'] is True and fresh['expired'] is False
    assert fresh['generated_at'] and fresh['expires_at']
    assert old['configured'] is True and old['expired'] is True
    bare = states[challenge_cas['bare']]
    assert bare == {'ca_id': challenge_cas['bare'], 'configured': False, 'expired': False,
                    'generated_at': None, 'expires_at': None}


def test_a_challenge_without_its_stamp_is_listed_as_configured_and_left_untouched(app, auth_client, challenge_cas):
    legacy = _states(auth_client)[challenge_cas['legacy']]
    assert legacy['configured'] is True and legacy['expired'] is False and legacy['generated_at'] is None
    with app.app_context():
        assert SystemConfig.query.filter_by(key=f'scep_challenge_{challenge_cas["legacy"]}_generated_at').first() is None


def test_listing_the_states_writes_no_audited_read(app, auth_client, challenge_cas):
    before = _reads(app)
    _states(auth_client)
    assert _reads(app) == before


def test_reading_one_secret_is_still_one_audited_read(app, auth_client, challenge_cas):
    before = _reads(app)
    r = auth_client.get(f'/api/v2/scep/challenge/{challenge_cas["fresh"]}')
    assert r.status_code == 200 and r.get_json()['data']['challenge'] == SECRET
    assert _reads(app) == before + 1


@pytest.fixture
def auditor_client(app, auth_client):
    """A session of the built-in auditor role: read:scep without write:scep."""
    name = f'scep_auditor_{uuid.uuid4().hex[:8]}'
    r = auth_client.post('/api/v2/users', json={'username': name, 'password': 'AuditorPass123!', 'email': f'{name}@test.local', 'role': 'auditor'})
    assert r.status_code in (200, 201), r.data
    with app.app_context():
        user_id = User.query.filter_by(username=name).one().id
    c = app.test_client()
    assert c.post('/api/v2/auth/login', json={'username': name, 'password': 'AuditorPass123!'}).status_code == 200
    yield c
    auth_client.delete(f'/api/v2/users/{user_id}')


def test_read_scep_lists_the_states_but_reads_no_secret(auditor_client, challenge_cas):
    assert challenge_cas['fresh'] in _states(auditor_client)
    assert auditor_client.get(f'/api/v2/scep/challenge/{challenge_cas["fresh"]}').status_code == 403


def test_without_read_scep_the_states_are_refused(viewer_client, challenge_cas):
    assert viewer_client.get('/api/v2/scep/challenges').status_code == 403


def test_the_list_needs_a_session(client):
    assert client.get('/api/v2/scep/challenges').status_code == 401
