"""What the profile screens read and write: states and filters, template subset, per-profile
keytab with its entries, shared settings."""
import io
import json
import uuid

import pytest

from models import ADConnectorConfig, CA, CertificateTemplate, SystemConfig, WindowsEnrollmentProfile, db
from services.kerberos import negotiate_auth
from tests.keytab_support import keytab
from tests.test_keytab_composed import HOST, ONE, TWO, profiles  # noqa: F401
from tests.windows_profile_support import connectors_kept

URL = '/api/v2/windows-profiles'


@pytest.fixture
def seeded(app):
    """Four profiles, one per state, plus a connector that is down; all removed afterwards."""
    tag = uuid.uuid4().hex[:6]
    with connectors_kept(app):
        with app.app_context():
            down = ADConnectorConfig(name=f'ui-down-{tag}', enabled=True, server='x',
                                     base_dn='DC=ui,DC=test')
            down.health = {'state': 'down'}
            up = ADConnectorConfig(name=f'ui-up-{tag}', enabled=True, server='x', base_dn='DC=ui,DC=test')
            up.health = {'state': 'up'}
            db.session.add_all([down, up])
            db.session.flush()
            rows = {
                'complete': dict(enabled=True, keytab=True, connector_id=up.id),
                'bare': dict(enabled=True, keytab=True, connector_id=None),
                'nokt': dict(enabled=True, keytab=False, connector_id=up.id),
                'failing': dict(enabled=True, keytab=True, connector_id=down.id),
                'off': dict(enabled=False, keytab=True, connector_id=None),
            }
            ids = {}
            for key, spec in rows.items():
                p = WindowsEnrollmentProfile(name=f'ui-{key}-{tag}', realm=f'UI{key.upper()}{tag}.TEST'.upper(),
                                             enabled=spec['enabled'], connector_id=spec['connector_id'],
                                             issuing_ca_refid=f'refid-{key}-{tag}')
                if spec['keytab']:
                    p.set_keytab(keytab(f'HTTP/{HOST}@{p.realm}'))
                db.session.add(p)
                db.session.flush()
                ids[key] = p.id
            db.session.commit()
        yield tag, ids
        with app.app_context():
            WindowsEnrollmentProfile.query.filter(
                WindowsEnrollmentProfile.name.like(f'ui-%-{tag}')).delete(synchronize_session=False)
            db.session.commit()


def _names(client, query):
    r = client.get(f'{URL}?per_page=200&{query}')
    assert r.status_code == 200, r.data
    return {p['name'] for p in r.get_json()['data']}


@pytest.mark.parametrize('state,expected', [
    ('complete', {'complete', 'bare'}), ('keytab_missing', {'nokt'}),
    ('connector_failing', {'failing'}), ('disabled', {'off'})])
def test_state_filter_is_decided_by_the_server(auth_client, seeded, state, expected):
    tag, _ = seeded
    got = _names(auth_client, f'q={tag}&state={state}')
    assert got == {f'ui-{k}-{tag}' for k in expected}


def test_each_profile_reports_the_state_the_filter_uses(auth_client, seeded):
    tag, ids = seeded
    got = {p['name']: p['state'] for p in auth_client.get(f'{URL}?q={tag}&per_page=50').get_json()['data']}
    assert got[f'ui-failing-{tag}'] == 'connector_failing'
    assert got[f'ui-off-{tag}'] == 'disabled'
    assert got[f'ui-nokt-{tag}'] == 'keytab_missing'
    assert got[f'ui-complete-{tag}'] == 'complete'


def test_ca_filter_matches_the_issuing_or_policy_ca(auth_client, seeded):
    tag, ids = seeded
    assert _names(auth_client, f'q={tag}&ca=refid-nokt-{tag}') == {f'ui-nokt-{tag}'}
    assert _names(auth_client, f'q={tag}&ca=unknown-{tag}') == set()


def test_an_unknown_state_is_refused(auth_client):
    assert auth_client.get(f'{URL}?state=sleeping').status_code == 400


def test_the_list_names_the_connector_and_its_realm(auth_client, seeded):
    tag, ids = seeded
    row = auth_client.get(f"{URL}/{ids['failing']}").get_json()['data']
    assert row['connector_name'] == f'ui-down-{tag}'
    assert row['connector_health'] == 'down' and row['connector_realm'] == 'UI.TEST'


def test_templates_are_a_validated_subset_that_reads_back(app, auth_client, seeded):
    tag, ids = seeded
    with app.app_context():
        tpl = CertificateTemplate(name=f'ui-tpl-{tag}', template_type='custom', key_type='RSA-2048',
                                  validity_days=30, digest='sha256',
                                  extensions_template=json.dumps({'key_usage': [], 'extended_key_usage': []}))
        db.session.add(tpl)
        db.session.commit()
        tpl_id = tpl.id
    try:
        url = f"{URL}/{ids['complete']}"
        assert auth_client.put(url, json={'template_ids': [tpl_id]}).status_code == 200
        assert auth_client.get(url).get_json()['data']['template_ids'] == [tpl_id]
        assert auth_client.put(url, json={'template_ids': [tpl_id + 9999]}).status_code == 400
        assert auth_client.put(url, json={'template_ids': ['x']}).status_code == 400
        assert auth_client.put(url, json={'template_ids': []}).status_code == 200
        assert auth_client.get(url).get_json()['data']['template_ids'] == []
    finally:
        with app.app_context():
            from models import WindowsProfileTemplate
            WindowsProfileTemplate.query.filter_by(template_id=tpl_id).delete()
            CertificateTemplate.query.filter_by(id=tpl_id).delete()
            db.session.commit()


def _post_keytab(client, profile_id, data, **form):
    body = {'file': (io.BytesIO(data), 'k.keytab'), **form}
    return client.post(f'{URL}/{profile_id}/keytab', data=body, content_type='multipart/form-data')


def test_the_keytab_of_a_profile_is_uploaded_on_its_own_route_with_its_entries(auth_client, profiles):  # noqa: F811
    r = _post_keytab(auth_client, profiles.two, TWO)
    assert r.status_code == 200, r.data
    data = r.get_json()['data']
    assert data['keytab_set'] is True
    assert {e['realm'] for e in data['keytab_entries']} == {'TWO.TEST'}
    detail = auth_client.get(f'{URL}/{profiles.two}').get_json()['data']
    assert detail['keytab_entries'] == data['keytab_entries']
    assert 'keytab_entries' not in auth_client.get(f'{URL}?q=c03-two').get_json()['data'][0]


def test_a_dry_run_lists_the_realms_and_stores_nothing(app, auth_client, profiles):  # noqa: F811
    both = keytab(f'HTTP/{HOST}@TWO.TEST', f'HTTP/{HOST}@OTHER.TEST')
    r = _post_keytab(auth_client, profiles.two, both, dry_run='1')
    assert r.status_code == 200, r.data
    data = r.get_json()['data']
    assert data['realms'] == ['OTHER.TEST', 'TWO.TEST']
    assert data['foreign_entries'] == [f'HTTP/{HOST}@OTHER.TEST']
    with app.app_context():
        assert db.session.get(WindowsEnrollmentProfile, profiles.two).keytab is None


def test_a_keytab_of_another_realm_is_refused_naming_the_entries(auth_client, profiles):  # noqa: F811
    r = _post_keytab(auth_client, profiles.two, ONE)
    assert r.status_code == 400 and f'HTTP/{HOST}@ONE.TEST' in r.get_json()['message']


def test_a_keytab_needs_the_write_scope_of_profiles(viewer_client, profiles):  # noqa: F811
    assert _post_keytab(viewer_client, profiles.two, TWO).status_code in (401, 403)


def test_settings_round_trip_and_the_kerberos_part_needs_its_scope(app, auth_client, viewer_client):
    with app.app_context():
        saved = {r.key: r.value for r in SystemConfig.query.filter(
            SystemConfig.key.in_(['xcep_enabled', 'kerberos_enabled', 'kerberos_spn'])).all()}
    try:
        r = auth_client.patch(f'{URL}/settings', json={'xcep_enabled': True, 'kerberos_enabled': True,
                                                      'kerberos_spn': f'HTTP/{HOST}@ONE.TEST'})
        assert r.status_code == 200, r.data
        got = auth_client.get(f'{URL}/settings').get_json()['data']
        assert got['xcep_enabled'] is True and got['kerberos_enabled'] is True
        assert got['kerberos_spn'] == f'HTTP/{HOST}@ONE.TEST'
        assert 'keytab_entries' in got and 'library_available' in got
        default = got['default_profile']
        with app.app_context():
            expected = WindowsEnrollmentProfile.query.filter_by(is_default=True).first()
            assert default == ({'id': expected.id, 'name': expected.name, 'realm': expected.realm,
                                'enabled': bool(expected.enabled)} if expected else None)
        assert auth_client.patch(f'{URL}/settings', json={'xcep_enabled': 'yes'}).status_code == 400
        assert viewer_client.patch(f'{URL}/settings', json={'kerberos_enabled': False}).status_code in (401, 403)
    finally:
        with app.app_context():
            for key in ('xcep_enabled', 'kerberos_enabled', 'kerberos_spn'):
                row = SystemConfig.query.filter_by(key=key).first()
                if key in saved:
                    row.value = saved[key]
                elif row is not None:
                    db.session.delete(row)
            db.session.commit()


@pytest.fixture
def xcep_only(app, auth_client):
    """An account holding read:xcep and write:xcep and no WSTEP or Kerberos scope."""
    r = auth_client.post('/api/v2/rbac/roles', json={'name': 'wp-ui-xcep',
                                                     'permissions': ['read:xcep', 'write:xcep']})
    assert r.status_code == 200, r.data
    role_id = r.get_json()['data']['id']
    body = {'username': 'wp_ui_xcep', 'password': 'TestPass123!', 'email': 'wpuix@test.local',
            'role': 'viewer', 'custom_role_id': role_id}
    assert auth_client.post('/api/v2/users', json=body).status_code in (200, 201)
    c = app.test_client()
    assert c.post('/api/v2/auth/login', json={'username': body['username'],
                                              'password': body['password']}).status_code == 200
    yield c
    with app.app_context():
        from models import User
        from models.rbac import CustomRole
        User.query.filter_by(username=body['username']).delete()
        CustomRole.query.filter_by(id=role_id).delete()
        db.session.commit()


def test_wstep_and_kerberos_settings_need_their_own_write_scope(xcep_only):
    for body in ({'wstep_enabled': True}, {'kerberos_enabled': True}, {'kerberos_spn': 'HTTP/h@R'}):
        assert xcep_only.patch(f'{URL}/settings', json=body).status_code == 403, body
    got = xcep_only.get(f'{URL}/settings').get_json()['data']
    assert 'xcep_enabled' in got and 'wstep_enabled' not in got and 'kerberos_enabled' not in got


@pytest.mark.parametrize('method, path', [
    ('get', '/api/v2/ad-connector'), ('put', '/api/v2/ad-connector'),
    ('post', '/api/v2/ad-connector/test'), ('post', '/api/v2/ad-connector/test-saved'),
    ('get', '/api/v2/xcep/config'), ('patch', '/api/v2/xcep/config'),
    ('get', '/api/v2/wstep/config'), ('patch', '/api/v2/wstep/config'),
    ('get', '/api/v2/kerberos/config'), ('patch', '/api/v2/kerberos/config'),
    ('post', '/api/v2/kerberos/keytab')])
def test_the_single_row_configuration_routes_are_gone(auth_client, method, path):
    """Answered as a path that never existed is (the catch-all route makes it 405 for a write)."""
    gone = getattr(auth_client, method)(path, json={}).status_code
    never = getattr(auth_client, method)('/api/v2/never-existed-route', json={}).status_code
    assert gone == never and gone in (404, 405)


def _key(auth_client, permissions):
    r = auth_client.post('/api/v2/account/apikeys', json={'name': 'wp-scope', 'permissions': permissions})
    assert r.status_code == 201, r.data
    data = r.get_json()['data']
    return data['id'], {'X-API-Key': data['key']}


@pytest.mark.parametrize('scopes, status', [
    (['write:xcep'], 403), (['write:kerberos'], 403), (['write:xcep', 'write:kerberos'], 200)])
def test_a_keytab_needs_both_the_xcep_and_kerberos_write_scopes(app, auth_client, profiles,  # noqa: F811
                                                                scopes, status):
    key_id, headers = _key(auth_client, ['read:xcep', *scopes])
    try:
        r = app.test_client().post(f'{URL}/{profiles.two}/keytab', headers=headers,
                                   data={'file': (io.BytesIO(TWO), 'k.keytab'), 'dry_run': '1'},
                                   content_type='multipart/form-data')
        assert r.status_code == status, r.data
        if status == 403:
            assert r.get_json()['message'] == 'Insufficient permissions'
    finally:
        auth_client.delete(f'/api/v2/account/apikeys/{key_id}')


def test_the_kerberos_refusal_names_the_profile_or_what_the_binding_lacks(app, monkeypatch):
    from services.windows_profiles import kerberos_refusal, kerberos_unserved_reason
    served = WindowsEnrollmentProfile(name='k-off', realm='K.EXAMPLE', enabled=False)
    monkeypatch.setattr(negotiate_auth, 'not_configured_reason', lambda: None)
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    with app.app_context():
        assert kerberos_refusal(served) == 'profile k-off is disabled'
        assert kerberos_unserved_reason(served) == 'profile k-off is disabled'
        served.enabled = True
        # A realm whose profile holds no key is a 401 at the acceptor, whatever the profile says
        assert kerberos_unserved_reason(served) == 'no key for realm K.EXAMPLE: upload the keytab of this profile'
        served.keytab = 'stored'
        assert kerberos_unserved_reason(served) is None
        monkeypatch.setattr(negotiate_auth, 'not_configured_reason', lambda: 'no keytab uploaded')
        assert kerberos_unserved_reason(served) == 'no keytab uploaded'
        # A configured binding is no excuse for a profile that serves nothing
        assert kerberos_refusal(served) is None


def test_a_missing_kerberos_library_is_said_before_the_binding_settings(app, monkeypatch):
    from services.windows_profiles import kerberos_binding_reason
    monkeypatch.setattr(negotiate_auth, 'not_configured_reason', lambda: 'no SPN set')
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: False)
    with app.app_context():
        assert kerberos_binding_reason() == 'the Kerberos library is not installed'
        monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
        assert kerberos_binding_reason() == 'no SPN set'


@pytest.mark.parametrize('extra, binding_shown', [([], False), (['read:kerberos'], True)])
def test_the_binding_reason_needs_the_kerberos_read_scope(app, auth_client, profiles, monkeypatch,  # noqa: F811
                                                          extra, binding_shown):
    monkeypatch.setattr(negotiate_auth, 'not_configured_reason', lambda: 'no SPN set')
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    key_id, headers = _key(auth_client, ['read:xcep', *extra])
    try:
        client = app.test_client()
        one = client.get(f'{URL}/{profiles.two}', headers=headers).get_json()['data']
        listed = client.get(f'{URL}?q=c03-two', headers=headers).get_json()['data']
        row = next(r for r in listed if r['id'] == profiles.two)
        assert one['kerberos_refusal'] == row['kerberos_refusal'] == (
            'no SPN set' if binding_shown else 'no key for realm TWO.TEST: upload the keytab of this profile')
    finally:
        auth_client.delete(f'/api/v2/account/apikeys/{key_id}')


def test_a_profile_without_a_realm_is_refused_by_its_own_name(app):
    from services.windows_profiles import kerberos_refusal
    with app.app_context():
        named = WindowsEnrollmentProfile(name='no-realm', realm=None, enabled=True, is_default=False)
        assert kerberos_refusal(named) == 'profile no-realm has no realm: Kerberos refused until one is set'
        default = WindowsEnrollmentProfile(name='no-realm', realm=None, enabled=True, is_default=True)
        assert kerberos_refusal(default) == 'default profile has no realm: Kerberos refused until one is set'


def test_the_profile_api_gives_the_reason_the_binding_is_not_configured(app, auth_client, profiles, monkeypatch):  # noqa: F811
    monkeypatch.setattr(negotiate_auth, 'not_configured_reason', lambda: 'no SPN set')
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    # Rows other files left behind, sorted before ours, must not push it off the first page
    with app.app_context():
        db.session.add_all(WindowsEnrollmentProfile(name=f'a-pad-{i:02d}', enabled=True) for i in range(30))
        db.session.commit()
    try:
        for read in (auth_client.get(f'{URL}/{profiles.two}'), auth_client.get(f'{URL}?q=c03-two')):
            body = read.get_json()['data']
            row = body if isinstance(body, dict) else next(r for r in body if r['id'] == profiles.two)
            assert row['kerberos_refusal'] == 'no SPN set'
    finally:
        with app.app_context():
            WindowsEnrollmentProfile.query.filter(
                WindowsEnrollmentProfile.name.like('a-pad-%')).delete(synchronize_session=False)
            db.session.commit()


def test_the_list_and_the_detail_agree_on_a_realm_without_key(
        app, auth_client, profiles, monkeypatch):  # noqa: F811
    monkeypatch.setattr(negotiate_auth, 'not_configured_reason', lambda: None)
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    with app.app_context():
        db.session.get(WindowsEnrollmentProfile, profiles.default).keytab = 'stored'
        db.session.commit()
    reason = 'no key for realm TWO.TEST: upload the keytab of this profile'
    one = auth_client.get(f'{URL}/{profiles.two}').get_json()['data']
    row = next(r for r in auth_client.get(f'{URL}?q=c03-two').get_json()['data'] if r['id'] == profiles.two)
    assert one['kerberos_refusal'] == row['kerberos_refusal'] == reason
    keyed = auth_client.get(f'{URL}/{profiles.default}').get_json()['data']
    assert keyed['keytab_set'] and keyed['kerberos_refusal'] is None
