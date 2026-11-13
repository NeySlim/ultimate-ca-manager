"""Windows enrollment profiles API: CRUD, validation, paging, permissions, deletion."""
import json
import threading
import uuid

import pytest
from sqlalchemy import event

from models import ADConnectorConfig, CA, Certificate, WindowsEnrollmentProfile, db
from models.audit_log import AuditLog
from utils.datetime_utils import utc_now
from utils.revocation_reasons import HOLD_REASONS
from tests.windows_profile_support import default_profile_id, put_default_profile
from datetime import timedelta

URL = '/api/v2/windows-profiles'


@pytest.fixture(autouse=True, scope='module')
def _profiles_stay_in_this_module(app, drop_new_cas_and_certificates):
    with app.app_context():
        keep = {p.id for p in WindowsEnrollmentProfile.query.all()}
        from models import User
        users = {u.id for u in User.query.all()}
    yield
    with app.app_context():
        # The shared viewer_client fixture leaves its account behind
        for u in User.query.all():
            if u.id not in users:
                db.session.delete(u)
        Certificate.query.filter(Certificate.descr.like('wp-api-%')).delete(synchronize_session=False)
        for p in WindowsEnrollmentProfile.query.all():
            if p.id not in keep:
                db.session.delete(p)
        db.session.commit()


def _new(auth_client, **fields):
    body = {'name': f'p-{uuid.uuid4().hex[:8]}', **fields}
    return auth_client.post(URL, data=json.dumps(body), content_type='application/json')


def _created(auth_client, **fields):
    r = _new(auth_client, **fields)
    assert r.status_code == 201, r.data
    return r.get_json()['data']


def _signer(create_ca):
    return create_ca(cn=f'WP signer {uuid.uuid4().hex[:5]}')


def _refid(app, ca):
    with app.app_context():
        return db.session.get(CA, ca['id']).refid


def test_crud_never_renders_secrets_and_audits_by_name(app, auth_client, create_ca):
    refid = _refid(app, _signer(create_ca))
    p = _created(auth_client, realm='crud.example', issuing_ca_refid=refid, validity_days=90)
    put_default_profile(auth_client, xcep_username='u', xcep_password='Sup3rSecret!',
                        wstep_username='w', wstep_password='Another#Secret1')
    assert p['realm'] == 'CRUD.EXAMPLE'
    default_id = default_profile_id(auth_client)
    shown = auth_client.get(f'{URL}/{default_id}').get_json()['data']
    assert shown['xcep_password_set'] and shown['wstep_password_set']
    for blob in (json.dumps(p), json.dumps(shown), auth_client.get(f"{URL}/{p['id']}").get_data(as_text=True),
                 auth_client.get(f"{URL}?per_page=100").get_data(as_text=True)):
        assert 'Sup3rSecret' not in blob and 'Another#Secret1' not in blob
        assert '"xcep_password"' not in blob and '"keytab"' not in blob
    r = auth_client.put(f"{URL}/{p['id']}", json={'enabled': False, 'validity_days': 30})
    assert r.status_code == 200, r.data
    got = auth_client.get(f"{URL}/{p['id']}").get_json()['data']
    assert got['enabled'] is False and got['validity_days'] == 30
    assert auth_client.delete(f"{URL}/{p['id']}").status_code == 200
    assert auth_client.get(f"{URL}/{p['id']}").status_code == 404
    with app.app_context():
        for action in ('windows_profile_create', 'windows_profile_update', 'windows_profile_delete'):
            row = AuditLog.query.filter_by(action=action, resource_name=p['name']).first()
            assert row is not None, action


def test_a_name_is_required_and_unique(auth_client):
    assert auth_client.post(URL, json={}).status_code == 400
    p = _created(auth_client)
    assert _new(auth_client, name=p['name']).status_code == 409


def test_realm_is_upper_cased_and_a_duplicate_refused(auth_client):
    a = _created(auth_client, realm='  dup.example ')
    assert a['realm'] == 'DUP.EXAMPLE'
    r = _new(auth_client, realm='Dup.Example')
    assert r.status_code == 409
    b = _created(auth_client)
    r = auth_client.put(f"{URL}/{b['id']}", json={'realm': 'DUP.EXAMPLE'})
    assert r.status_code == 409
    assert auth_client.put(f"{URL}/{a['id']}", json={'realm': 'dup.example'}).status_code == 200


def test_one_default_which_is_not_deleted(app, auth_client):
    with app.app_context():
        existing = WindowsEnrollmentProfile.query.filter_by(is_default=True).first()
        if existing is None:
            db.session.add(WindowsEnrollmentProfile(name='wp-api-default', is_default=True))
            db.session.commit()
            existing = WindowsEnrollmentProfile.query.filter_by(is_default=True).first()
        default_id = existing.id
    assert _new(auth_client, is_default=True).status_code == 409
    other = _created(auth_client)
    assert auth_client.put(f"{URL}/{other['id']}", json={'is_default': True}).status_code == 409
    r = auth_client.delete(f'{URL}/{default_id}')
    assert r.status_code == 409 and 'default' in r.get_json()['message']
    assert auth_client.put(f'{URL}/{default_id}', json={'enabled': False}).status_code == 200
    auth_client.put(f'{URL}/{default_id}', json={'enabled': True})


def test_a_connector_of_another_domain_is_refused(app, auth_client):
    with app.app_context():
        # A connector of its own: the rows other files mount are left alone
        connector = ADConnectorConfig(name='wp-api-other', base_dn='DC=other,DC=example')
        db.session.add(connector)
        db.session.commit()
        cid = connector.id
    try:
        r = _new(auth_client, realm='MINE.EXAMPLE', connector_id=cid)
        assert r.status_code == 400 and 'OTHER.EXAMPLE' in r.get_json()['message']
        p = _created(auth_client, realm='OTHER.EXAMPLE', connector_id=cid)
        r = auth_client.put(f"{URL}/{p['id']}", json={'realm': 'MINE.EXAMPLE'})
        assert r.status_code == 400
        assert auth_client.put(f"{URL}/{p['id']}", json={'connector_id': 99999}).status_code == 404
        # A connector moved to another domain elsewhere still lets the profile be disabled
        with app.app_context():
            db.session.get(ADConnectorConfig, cid).base_dn = 'DC=two,DC=example'
            db.session.commit()
        assert auth_client.put(f"{URL}/{p['id']}", json={'enabled': False}).status_code == 200
        r = auth_client.put(f"{URL}/{p['id']}", json={'connector_id': cid})
        assert r.status_code == 400 and 'TWO.EXAMPLE' in r.get_json()['message']
    finally:
        with app.app_context():
            WindowsEnrollmentProfile.query.filter_by(connector_id=cid).update({'connector_id': None})
            ADConnectorConfig.query.filter_by(id=cid).delete()
            db.session.commit()


def test_cas_are_checked_as_the_legacy_routes_do(app, auth_client, create_ca):
    keyless = _signer(create_ca)
    with app.app_context():
        db.session.get(CA, keyless['id']).prv = None
        db.session.commit()
    keyless_refid = _refid(app, keyless)
    r = _new(auth_client, issuing_ca_refid=keyless_refid)
    assert r.status_code == 400 and 'no private key' in r.get_json()['message']
    eddsa = create_ca(cn=f'WP ed {uuid.uuid4().hex[:5]}', keyAlgo='EdDSA', keySize='Ed25519')
    ed_refid = _refid(app, eddsa)
    r = _new(auth_client, policy_ca_refid=ed_refid)
    assert r.status_code == 400 and 'EdDSA' in r.get_json()['message']
    assert _new(auth_client, issuing_ca_refid='nope').status_code == 404
    # a CA already saved stays saveable after it lost its key
    good = _refid(app, _signer(create_ca))
    p = _created(auth_client, issuing_ca_refid=good)
    with app.app_context():
        CA.query.filter_by(refid=good).first().prv = None
        db.session.commit()
    assert auth_client.put(f"{URL}/{p['id']}", json={'issuing_ca_refid': good,
                                                     'validity_days': 40}).status_code == 200


def _seed(app, n):
    with app.app_context():
        for i in range(n):
            db.session.add(WindowsEnrollmentProfile(
                name=f'wp-seed-{i:03d}', realm=f'WPAPI{i:03d}.EXAMPLE' if i % 2 else None))
        db.session.commit()


def _count(app, client, query):
    seen, mine = [], threading.get_ident()

    def hook(conn, cursor, statement, *rest):
        if threading.get_ident() == mine:
            seen.append(statement)

    from utils.admin_allowlist import invalidate_cache
    with app.app_context():
        invalidate_cache()
        event.listen(db.engine, 'before_cursor_execute', hook)
        try:
            r = client.get(f'{URL}?{query}')
        finally:
            event.remove(db.engine, 'before_cursor_execute', hook)
    assert r.status_code == 200, r.data
    return len(seen), r.get_json()


def test_150_profiles_page_search_and_constant_sql(app, auth_client, create_ca):
    refid = _refid(app, _signer(create_ca))
    _seed(app, 150)
    with app.app_context():
        WindowsEnrollmentProfile.query.filter(WindowsEnrollmentProfile.name.like('wp-seed-%')).update(
            {'issuing_ca_refid': refid}, synchronize_session=False)
        db.session.commit()
    n_small, small = _count(app, auth_client, 'q=wp-seed-&per_page=5&page=1')
    n_big, big = _count(app, auth_client, 'q=wp-seed-&per_page=100&page=1')
    assert n_small == n_big
    assert small['meta']['total'] == 150 and small['meta']['total_pages'] == 30
    seen = []
    for page in range(1, 4):
        r = auth_client.get(f'{URL}?q=wp-seed-&per_page=60&page={page}').get_json()
        seen += [p['name'] for p in r['data']]
    assert seen == sorted(seen) and len(seen) == len(set(seen)) == 150
    _, by_realm = _count(app, auth_client, 'q=wpapi007.example')
    assert [p['name'] for p in by_realm['data']] == ['wp-seed-007']
    _, none = _count(app, auth_client, 'q=%25')
    assert none['meta']['total'] == 0


@pytest.fixture(scope='module')
def auditor_client(app, auth_client):
    """An account that holds read:xcep and no write:xcep."""
    body = {'username': 'wp_auditor', 'password': 'AuditorPass123!', 'email': 'wpa@test.local',
            'role': 'auditor'}
    auth_client.post('/api/v2/users', json=body)
    c = app.test_client()
    r = c.post('/api/v2/auth/login', json={'username': body['username'], 'password': body['password']})
    assert r.status_code == 200, r.data
    yield c
    with app.app_context():
        from models import User
        User.query.filter_by(username=body['username']).delete()
        db.session.commit()


def test_read_and_write_permissions_are_distinct(app, client, viewer_client, auditor_client):
    assert client.get(URL).status_code == 401
    assert client.post(URL, json={'name': 'x'}).status_code == 401
    assert viewer_client.get(URL).status_code == 403
    assert auditor_client.get(URL).status_code == 200
    name = f'v-{uuid.uuid4().hex[:6]}'
    assert auditor_client.post(URL, json={'name': name}).status_code == 403
    with app.app_context():
        row = WindowsEnrollmentProfile(name=f'wp-api-v-{name}')
        db.session.add(row)
        db.session.commit()
        pid = row.id
    assert auditor_client.put(f'{URL}/{pid}', json={'enabled': False}).status_code == 403
    assert auditor_client.delete(f'{URL}/{pid}').status_code == 403
    with app.app_context():
        assert WindowsEnrollmentProfile.query.filter_by(name=name).first() is None
        assert db.session.get(WindowsEnrollmentProfile, pid).enabled is True


def _cert(profile_id, **fields):
    return Certificate(refid=uuid.uuid4().hex, descr=f'wp-api-{uuid.uuid4().hex[:6]}',
                       windows_profile_id=profile_id, crt='x', subject='CN=x', issuer='CN=x',
                       valid_to=fields.pop('valid_to', utc_now() + timedelta(days=30)), **fields)


def test_a_profile_with_valid_certificates_is_not_deleted_but_can_be_disabled(app, auth_client):
    p = _created(auth_client)
    with app.app_context():
        db.session.add_all([_cert(p['id']), _cert(p['id']),
                            _cert(p['id'], revoked=True),
                            _cert(p['id'], revoked=True, revoke_reason='certificateHold'),
                            _cert(p['id'], valid_to=utc_now() - timedelta(days=1))])
        db.session.commit()
    r = auth_client.delete(f"{URL}/{p['id']}")
    # A certificate on hold may be released (RFC 5280 5.3.1): it still counts as valid
    assert r.status_code == 409 and '3 valid certificate' in r.get_json()['message']
    assert auth_client.put(f"{URL}/{p['id']}", json={'enabled': False}).status_code == 200
    with app.app_context():
        Certificate.query.filter_by(windows_profile_id=p['id']).delete()
        db.session.commit()
    assert auth_client.delete(f"{URL}/{p['id']}").status_code == 200


def test_deleting_a_profile_releases_its_certificates(app, auth_client):
    p = _created(auth_client)
    with app.app_context():
        c = _cert(p['id'], revoked=True)
        db.session.add(c)
        db.session.commit()
        cid = c.id
    assert auth_client.delete(f"{URL}/{p['id']}").status_code == 200
    with app.app_context():
        assert db.session.get(Certificate, cid).windows_profile_id is None


def test_the_default_is_created_beside_a_profile_named_default(app, auth_client):
    with app.app_context():
        aside = WindowsEnrollmentProfile.query.filter_by(is_default=True).all()
        saved = [(p.id, p.name) for p in aside]
        for p in aside:
            p.is_default = False
            p.name = f'wp-api-aside-{p.id}'
        db.session.commit()
    try:
        assert _new(auth_client, name='default').status_code == 201
        with app.app_context():
            from services import windows_profiles
            made = windows_profiles.default_for_write('test')
            made.wstep_username = 'zz'
            db.session.commit()
            assert made.is_default and made.name != 'default'
    finally:
        with app.app_context():
            for p in WindowsEnrollmentProfile.query.filter_by(is_default=True).all():
                db.session.delete(p)
            WindowsEnrollmentProfile.query.filter_by(name='default').delete()
            db.session.commit()
            for pid, name in saved:
                p = db.session.get(WindowsEnrollmentProfile, pid)
                p.is_default, p.name = True, name
            db.session.commit()


@pytest.mark.parametrize('field, value', [
    ('connector_id', '1'), ('connector_id', True), ('connector_id', 1.5), ('connector_id', [1]),
    ('issuing_ca_refid', 5), ('issuing_ca_refid', True), ('issuing_ca_refid', ['x']),
    ('policy_ca_refid', 5), ('policy_ca_refid', {'a': 1}),
])
def test_identifiers_of_the_wrong_type_are_a_400(auth_client, field, value):
    assert _new(auth_client, **{field: value}).status_code == 400
    p = _created(auth_client)
    assert auth_client.put(f"{URL}/{p['id']}", json={field: value}).status_code == 400


@pytest.mark.parametrize('field', ['is_default', 'enabled'])
@pytest.mark.parametrize('value', ['false', 'true', 0, 1, None, []])
def test_flags_must_be_json_booleans(app, auth_client, field, value):
    assert _new(auth_client, **{field: value}).status_code == 400
    p = _created(auth_client)
    assert auth_client.put(f"{URL}/{p['id']}", json={field: value}).status_code == 400
    with app.app_context():
        assert WindowsEnrollmentProfile.query.filter_by(is_default=True).count() <= 1


def test_the_realm_is_cleared_by_null_only(auth_client):
    p = _created(auth_client, realm='clear.example')
    for blank in ('', '   '):
        r = auth_client.put(f"{URL}/{p['id']}", json={'realm': blank})
        assert r.status_code == 400, blank
    assert auth_client.get(f"{URL}/{p['id']}").get_json()['data']['realm'] == 'CLEAR.EXAMPLE'
    r = auth_client.put(f"{URL}/{p['id']}", json={'realm': None})
    assert r.status_code == 200 and r.get_json()['data']['realm'] is None


def test_an_undecryptable_keytab_names_its_own_profile(app, auth_client, monkeypatch):
    p = _created(auth_client, name=f"keytab-{uuid.uuid4().hex[:6]}")

    def broken(self):
        raise ValueError('no key')
    monkeypatch.setattr(WindowsEnrollmentProfile, 'keytab_bytes', broken)
    r = auth_client.put(f"{URL}/{p['id']}", json={'realm': 'KT.EXAMPLE'})
    assert r.status_code == 409
    message = r.get_json()['message']
    assert p['name'] in message and 'default profile' not in message


def test_the_default_name_taken_in_a_race_is_chosen_again(app, auth_client, monkeypatch):
    from services import windows_profiles
    with app.app_context():
        aside = WindowsEnrollmentProfile.query.filter_by(is_default=True).all()
        saved = [(p.id, p.name) for p in aside]
        for p in aside:
            p.is_default = False
            p.name = f'wp-api-aside-{p.id}'
        db.session.commit()
    names = iter(['default'])
    real = windows_profiles._unused_name
    # The name looks free once while a profile already holds it
    monkeypatch.setattr(windows_profiles, '_unused_name', lambda: next(names, None) or real())
    try:
        assert _new(auth_client, name='default').status_code == 201
        with app.app_context():
            profile = windows_profiles.default_for_write('tester')
            assert profile.is_default and profile.name == 'default-2'
            db.session.commit()
    finally:
        with app.app_context():
            for p in WindowsEnrollmentProfile.query.filter_by(is_default=True).all():
                db.session.delete(p)
            WindowsEnrollmentProfile.query.filter_by(name='default').delete()
            db.session.commit()
            for pid, name in saved:
                p = db.session.get(WindowsEnrollmentProfile, pid)
                p.is_default, p.name = True, name
            db.session.commit()


@pytest.mark.parametrize('reason', HOLD_REASONS)
def test_a_certificate_on_hold_blocks_deleting_its_profile(app, auth_client, reason):
    p = _created(auth_client)
    with app.app_context():
        db.session.add(_cert(p['id'], revoked=True, revoke_reason=reason))
        db.session.commit()
    r = auth_client.delete(f"{URL}/{p['id']}")
    assert r.status_code == 409 and '1 valid certificate' in r.get_json()['message']
    with app.app_context():
        Certificate.query.filter_by(windows_profile_id=p['id']).update({'revoke_reason': 'keyCompromise'})
        db.session.commit()
    assert auth_client.delete(f"{URL}/{p['id']}").status_code == 200


@pytest.mark.parametrize('value', ['[]', '{"C": "USA"}', '{"CN": "x"}', 'not json', ['O'], {'C': 'USA'}, {'O': 5}])
def test_pinned_subject_fields_are_validated_as_the_template_s(app, auth_client, value):
    """A3: an object of O/OU/C/ST/L only, C of two letters, on create as on update."""
    assert _new(auth_client, pinned_subject_fields=value).status_code == 400
    p = _created(auth_client)
    r = auth_client.put(f"{URL}/{p['id']}", data=json.dumps({'pinned_subject_fields': value}),
                        content_type='application/json')
    assert r.status_code == 400
    with app.app_context():
        assert db.session.get(WindowsEnrollmentProfile, p['id']).pinned_subject_fields is None


@pytest.mark.parametrize('value, stored', [({'O': ' Org ', 'C': 'fr'}, {'O': 'Org', 'C': 'FR'}),
                                           ('{"OU": "Site", "L": ""}', {'OU': 'Site'}),
                                           ('{}', None), ({}, None), ('', None), (None, None)])
def test_pinned_subject_fields_are_stored_cleaned_and_none_when_empty(app, auth_client, value, stored):
    r = _new(auth_client, pinned_subject_fields=value)
    assert r.status_code == 201, r.data
    with app.app_context():
        saved = db.session.get(WindowsEnrollmentProfile, r.get_json()['data']['id']).pinned_subject_fields
    assert (json.loads(saved) if saved else None) == stored


@pytest.mark.parametrize('field,value', [('xcep_username', 'u'), ('xcep_password', 'Sup3rSecret!'),
                                         ('wstep_username', 'w'), ('wstep_password', 'Another#Secret1')])
def test_shared_credentials_are_refused_on_a_profile_that_is_not_the_default(auth_client, field, value):
    """Only the default profile's binding reads them: saved elsewhere they would never be used."""
    default_profile_id(auth_client)
    r = auth_client.post(URL, json={'name': f'wp-cred-{uuid.uuid4().hex[:5]}', field: value})
    assert r.status_code == 400, r.data
    assert 'default profile' in r.get_json()['message']
    other = _created(auth_client, name=f'wp-cred-{uuid.uuid4().hex[:5]}')
    r = auth_client.put(f"{URL}/{other['id']}", json={field: value})
    assert r.status_code == 400, r.data
    # Clearing one is not setting one
    clear = {field: ''} if field.endswith('username') else {}
    assert auth_client.put(f"{URL}/{other['id']}", json=clear).status_code == 200
    assert put_default_profile(auth_client, **{field: value}).status_code == 200
