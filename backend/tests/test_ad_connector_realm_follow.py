"""A connector's new domain: the realm of its keytab-less profiles follows, any other profile
refuses the save; a profile whose realm differs from its connector's domain is flagged."""
import json

import pytest
from sqlalchemy import event

from models import AuditLog, WindowsEnrollmentProfile, db
from services.ad_connector import lookup
from tests.ad_connector_support import add_connector, clear_connectors
from tests.keytab_support import keytab
from tests.windows_profile_support import connectors_kept

URL = '/api/v2/ad-connectors'
PROFILES = '/api/v2/windows-profiles'


@pytest.fixture
def world(app, monkeypatch):
    """One disabled connector on OLD.EXAMPLE; the profiles a test makes are removed afterwards."""
    monkeypatch.setattr(lookup, '_connect', lambda config: (_ for _ in ()).throw(OSError('down')))
    with connectors_kept(app):
        with app.app_context():
            clear_connectors()
            connector = add_connector('c10-forest', server='dc.old.example', base_dn='DC=old,DC=example',
                                      bind_dn='svc', enabled=False)
            connector_id = connector.id
        yield connector_id
        with app.app_context():
            WindowsEnrollmentProfile.query.filter(
                WindowsEnrollmentProfile.name.like('c10-%')).delete(synchronize_session=False)
            db.session.commit()


def _profile(app, name, realm, connector_id=None, with_keytab=False):
    with app.app_context():
        profile = WindowsEnrollmentProfile(name=f'c10-{name}', realm=realm, enabled=True,
                                           connector_id=connector_id)
        if with_keytab:
            profile.set_keytab(keytab(f'HTTP/ucm.example@{realm}'))
        db.session.add(profile)
        db.session.commit()
        return profile.id


def _realm(app, profile_id):
    with app.app_context():
        return db.session.get(WindowsEnrollmentProfile, profile_id).realm


def _base_dn(app, connector_id):
    from models import ADConnectorConfig
    with app.app_context():
        return db.session.get(ADConnectorConfig, connector_id).base_dn


def _move(client, connector_id, base_dn='DC=new,DC=example'):
    return client.put(f'{URL}/{connector_id}', data=json.dumps({'base_dn': base_dn}),
                      content_type='application/json')


def _nothing_written(app, connector_id, realms):
    assert _base_dn(app, connector_id) == 'DC=old,DC=example'
    for profile_id, realm in realms.items():
        assert _realm(app, profile_id) == realm


def test_a_profile_without_keytab_follows_the_new_domain_and_the_audit_says_so(app, auth_client, world):
    follower = _profile(app, 'follower', 'OLD.EXAMPLE', world)
    elsewhere = _profile(app, 'elsewhere', 'ELSE.EXAMPLE')
    with app.app_context():
        floor = db.session.query(db.func.max(AuditLog.id)).scalar() or 0
    r = _move(auth_client, world)
    assert r.status_code == 200, r.data
    assert _realm(app, follower) == 'NEW.EXAMPLE' and _realm(app, elsewhere) == 'ELSE.EXAMPLE'
    with app.app_context():
        entry = AuditLog.query.filter(AuditLog.id > floor, AuditLog.action == 'ad_connector_update').one()
        assert 'c10-follower' in entry.details and 'OLD.EXAMPLE' in entry.details
        assert 'NEW.EXAMPLE' in entry.details


def test_a_profile_with_a_keytab_refuses_the_move_and_is_named(app, auth_client, world):
    bound = _profile(app, 'bound', 'OLD.EXAMPLE', world, with_keytab=True)
    r = _move(auth_client, world)
    assert r.status_code == 409, r.data
    message = r.get_json()['message']
    assert 'c10-bound' in message and 'keytab fixes its realm' in message
    # Only exits that exist: a keytab holds the realm, so "change the realm" is not offered
    assert 'another connector' in message and 'change the realm' not in message.lower()
    _nothing_written(app, world, {bound: 'OLD.EXAMPLE'})


def test_a_profile_whose_realm_was_not_the_old_domain_refuses_the_move(app, auth_client, world):
    other = _profile(app, 'other', 'ELSE.EXAMPLE', world)
    r = _move(auth_client, world)
    assert r.status_code == 409, r.data
    message = r.get_json()['message']
    assert 'c10-other' in message and 'change the realm of the other profiles' in message
    _nothing_written(app, world, {other: 'ELSE.EXAMPLE'})


def test_a_new_realm_another_profile_holds_refuses_the_move(app, auth_client, world):
    follower = _profile(app, 'follower', 'OLD.EXAMPLE', world)
    holder = _profile(app, 'holder', 'NEW.EXAMPLE')
    r = _move(auth_client, world)
    assert r.status_code == 409, r.data
    message = r.get_json()['message']
    assert 'c10-follower' in message and 'NEW.EXAMPLE' in message
    _nothing_written(app, world, {follower: 'OLD.EXAMPLE', holder: 'NEW.EXAMPLE'})


def test_one_profile_that_blocks_leaves_the_one_that_follows_unchanged(app, auth_client, world):
    other = _profile(app, 'other', 'ELSE.EXAMPLE', world)
    follower = _profile(app, 'follower', 'OLD.EXAMPLE', world)
    r = _move(auth_client, world)
    assert r.status_code == 409, r.data
    assert 'c10-other' in r.get_json()['message']
    _nothing_written(app, world, {other: 'ELSE.EXAMPLE', follower: 'OLD.EXAMPLE'})


def test_a_save_that_keeps_the_domain_touches_no_profile(app, auth_client, world):
    bound = _profile(app, 'bound', 'OLD.EXAMPLE', world, with_keytab=True)
    r = auth_client.put(f'{URL}/{world}', data=json.dumps({'base_dn': 'OU=x,DC=old,DC=example'}),
                        content_type='application/json')
    assert r.status_code == 200, r.data
    assert _realm(app, bound) == 'OLD.EXAMPLE'


def _rows(client, query=''):
    r = client.get(f'{PROFILES}?q=c10-&per_page=200{query}')
    assert r.status_code == 200, r.data
    return {row['name']: row for row in r.get_json()['data']}


def test_the_mismatch_is_flagged_in_the_list_and_the_detail(app, auth_client, world):
    ids = {
        'apart': _profile(app, 'apart', 'ELSE.EXAMPLE', world),
        'agree': _profile(app, 'agree', 'OLD.EXAMPLE', world),
        'alone': _profile(app, 'alone', 'ALONE.EXAMPLE'),
        'norealm': _profile(app, 'norealm', None, world),
    }
    rows = _rows(auth_client)
    flags = {name[4:]: row['connector_domain_mismatch'] for name, row in rows.items()}
    assert flags == {'apart': True, 'agree': False, 'alone': False, 'norealm': False}
    for key, expected in (('apart', True), ('agree', False)):
        detail = auth_client.get(f'{PROFILES}/{ids[key]}').get_json()['data']
        assert detail['connector_domain_mismatch'] is expected


def test_the_list_costs_the_same_queries_for_any_number_of_flagged_profiles(app, auth_client, world):
    def count():
        seen = []

        def hook(conn, cursor, statement, *a):
            seen.append(statement)
        with app.app_context():
            event.listen(db.engine, 'before_cursor_execute', hook)
            try:
                assert auth_client.get(f'{PROFILES}?q=c10-&per_page=200').status_code == 200
            finally:
                event.remove(db.engine, 'before_cursor_execute', hook)
        return len(seen)
    _profile(app, 'p00', 'ELSE0.EXAMPLE', world)
    few = count()
    for i in range(1, 12):
        _profile(app, f'p{i:02d}', f'ELSE{i}.EXAMPLE', world)
    assert count() == few


def test_a_profile_with_no_realm_or_already_on_the_new_domain_does_not_block_the_save(app, auth_client, world):
    keyed = _profile(app, 'keyed', 'NEW.EXAMPLE', world, with_keytab=True)
    blank = _profile(app, 'blank', None, world)
    r = _move(auth_client, world)
    assert r.status_code == 200, r.data
    assert _realm(app, keyed) == 'NEW.EXAMPLE' and _realm(app, blank) is None


def test_the_connector_row_is_not_written_before_the_domain_sid_is_read(app, auth_client, world, monkeypatch):
    """The SID read binds to the DCs: no write lock may be held while it runs."""
    _profile(app, 'follower', 'OLD.EXAMPLE', world)
    order = []

    def fetch(config):
        order.append('fetch')
        return None
    monkeypatch.setattr(lookup, 'fetch_domain_sid', fetch)

    def record(conn, cursor, statement, *args):
        if statement.lstrip().lower().startswith('update ad_connector_config'):
            order.append('update')
    with app.app_context():
        event.listen(db.engine, 'before_cursor_execute', record)
        try:
            r = _move(auth_client, world)
        finally:
            event.remove(db.engine, 'before_cursor_execute', record)
    assert r.status_code == 200, r.data
    assert order.index('fetch') < order.index('update')


def test_a_realm_taken_between_the_check_and_the_write_is_named_as_such(app, auth_client, world, monkeypatch):
    """The unique index refuses it: the answer names the realm, not the connector name."""
    from services import windows_profiles
    follower = _profile(app, 'follower', 'OLD.EXAMPLE', world)
    holder = _profile(app, 'holder', 'NEW.EXAMPLE')
    # As if the holder took the realm after the check
    monkeypatch.setattr(windows_profiles, 'realm_problem', lambda *a, **k: None)
    r = _move(auth_client, world)
    assert r.status_code == 409, r.data
    assert r.get_json()['message'] == 'NEW.EXAMPLE is already served by another profile'
    _nothing_written(app, world, {follower: 'OLD.EXAMPLE', holder: 'NEW.EXAMPLE'})

