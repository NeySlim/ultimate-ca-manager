"""Connectors in N rows: an explicit connector per lookup, the collection API, the bounded probe."""
import ast
import json
from pathlib import Path

import pytest

from models import AuditLog, WindowsEnrollmentProfile, ADConnectorConfig, db
from services.ad_connector import health, lookup
from tests.ad_connector_support import add_connector, clear_connectors, save_connector
from tests.windows_profile_support import connectors_kept

DOMAIN_SID = 'S-1-5-21-1608104657-630783805-1473387121'
URL = '/api/v2/ad-connectors'


@pytest.fixture(autouse=True)
def _connectors_put_back(app):
    with connectors_kept(app):
        with app.app_context():
            clear_connectors()
        yield


def _sid_bytes(sid):
    parts = [int(p) for p in sid.split('-')[3:]]
    return bytes([1, len(parts), 0, 0, 0, 0, 0, 5]) + b''.join(p.to_bytes(4, 'little') for p in parts)


class _Attr:
    def __init__(self, raw):
        self.value = raw
        self.raw_values = [raw]


class _Entry:
    def __init__(self, entry_dn='CN=x', **attrs):
        self.entry_dn = entry_dn
        self._attrs = attrs
        for key, raw in attrs.items():
            setattr(self, key, _Attr(raw))

    def __contains__(self, key):
        return key in self._attrs


class _Conn:
    """A bound connection answering every search with *entries*."""

    def __init__(self, entries):
        self.entries = entries
        self.result = {'result': 0, 'description': 'success'}

    def search(self, *args, **kwargs):
        return True

    def unbind(self):
        pass


class _Directory:
    """Simulated LDAP servers: a DC listed in *down* refuses, every bind is recorded."""

    def __init__(self, monkeypatch, entries, down=()):
        self.binds = []
        self._entries, self._down = entries, set(down)
        monkeypatch.setattr(lookup, '_connect_to', self._bind)

    def _bind(self, config, host, tls):
        self.binds.append((getattr(config, 'name', None), host))
        if host in self._down:
            raise OSError('refused')
        return _Conn(self._entries)


def _pair(app):
    with app.app_context():
        a = add_connector('forest-a', server='dc1.a.example\ndc2.a.example', base_dn='DC=a,DC=example',
                          bind_dn='svc', enabled=True)
        b = add_connector('forest-b', server='dc1.b.example', base_dn='DC=b,DC=example',
                          bind_dn='svc', enabled=True)
        return a.id, b.id


# Criterion 1
def test_a_lookup_binds_only_to_the_domain_controllers_of_its_connector(app, monkeypatch):
    sid = _sid_bytes(DOMAIN_SID + '-1105')
    directory = _Directory(monkeypatch, [_Entry(objectSid=sid)], down={'dc1.a.example'})
    a, b = _pair(app)
    with app.app_context():
        config_a = db.session.get(ADConnectorConfig, a)
        assert lookup.lookup_object_sid(config_a, 'X$') == DOMAIN_SID + '-1105'
        assert directory.binds == [('forest-a', 'dc1.a.example'), ('forest-a', 'dc2.a.example')]
        directory.binds.clear()
        config_b = db.session.get(ADConnectorConfig, b)
        assert lookup.lookup_object_sid(config_b, 'X$') == DOMAIN_SID + '-1105'
        assert directory.binds == [('forest-b', 'dc1.b.example')]



@pytest.mark.parametrize('returned, expected', [
    ('S-1-5-21-1-2-3-1105', 'S-1-5-21-1-2-3-1105'),
    ('S-1-5-21-9-9-9-1105', lookup.UNUSABLE_SID),
    ('S-1-5-21-1-2-34-1105', lookup.UNUSABLE_SID),
    ('S-1-5-21-1-2-3-5-1105', lookup.UNUSABLE_SID),
], ids=['own-domain', 'other-domain', 'longer-sub-authority', 'extra-sub-authority'])
def test_a_sid_outside_the_connector_domain_is_refused(app, monkeypatch, returned, expected):
    """C-02b criterion 3: a base DN reaching another domain cannot lend its SID."""
    _Directory(monkeypatch, [_Entry(objectSid=_sid_bytes(returned))])
    with app.app_context():
        config = add_connector('forest-a', server='dc1.a.example', base_dn='DC=a,DC=example',
                               bind_dn='svc', enabled=True, domain_sid='S-1-5-21-1-2-3')
        assert lookup.lookup_object_sid(config, 'X$') == expected
        config.domain_sid = None
        assert lookup.lookup_object_sid(config, 'X$') == returned  # domain never read: not checked

# Criterion 2
def test_a_probe_pass_stops_at_its_budget_and_the_next_one_resumes(app, monkeypatch):
    with app.app_context():
        for i in range(150):
            add_connector(f'forest-{i:03d}', server=f'dc.f{i}.example', base_dn=f'DC=f{i},DC=example',
                          bind_dn='svc', enabled=True)
        names = {c.id: c.name for c in ADConnectorConfig.query.all()}
        unreachable = {c_id for c_id, name in names.items() if int(name[-3:]) % 7 == 3}
        unreachable = set(sorted(unreachable)[:20])

    now = [0.0]
    probed = []

    def fake_probe(config):
        now[0] += 1.0
        probed.append(config.id)
        return [(config.server, config.id not in unreachable, 'ok' if config.id not in unreachable else 'down')]

    monkeypatch.setattr(health, 'probe', fake_probe)
    passes = []
    for _ in range(5):
        probed.clear()
        with app.app_context():
            result = health.run_health_probe(budget=40, clock=lambda: now[0])
        passes.append((list(probed), result))

    first, second = passes[0][0], passes[1][0]
    assert len(first) == 40 and passes[0][1]['pending'] == 110
    assert not set(first) & set(second)
    assert second == sorted(names)[40:80]
    seen = [c for ids, _r in passes for c in ids]
    assert sorted(seen) == sorted(names) and len(seen) == 150
    assert passes[4][1]['status'] == 'skipped'
    with app.app_context():
        states = {c.id: c.health['state'] for c in ADConnectorConfig.query.all()}
    assert {i for i, state in states.items() if state == health.STATE_DOWN} == unreachable


def test_a_pass_probes_the_never_probed_and_then_the_oldest_verdict_first(app, monkeypatch):
    """A pass sorted by id would probe the due head again and starve the tail."""
    from datetime import timedelta
    from utils.datetime_utils import utc_isoformat, utc_now
    with app.app_context():
        ids = [add_connector(f'order-{i}', server=f'dc.o{i}.example', base_dn=f'DC=o{i},DC=example',
                             bind_dn='svc', enabled=True).id for i in range(4)]
        for connector_id, hours in ((ids[0], 1), (ids[1], 2)):
            db.session.get(ADConnectorConfig, connector_id).health = {
                'state': health.STATE_UP, 'checked_at': utc_isoformat(utc_now() - timedelta(hours=hours))}
        db.session.commit()
    now, probed = [0.0], []

    def fake_probe(config):
        now[0] += 1.0
        probed.append(config.id)
        return [(config.server, True, 'ok')]

    monkeypatch.setattr(health, 'probe', fake_probe)
    passes = []
    for _ in range(2):
        probed.clear()
        with app.app_context():
            health.run_health_probe(budget=2, clock=lambda: now[0])
        passes.append(list(probed))
    assert passes == [[ids[2], ids[3]], [ids[1], ids[0]]]


# Criterion 3
_SINGLE_ROW = {'first', 'one', 'one_or_none', 'scalar', 'scalar_one', 'scalar_one_or_none'}
# The one implicit read allowed: the lowest-id row a 2.x install without a profile has alone
_ALLOWED = {('services/windows_profiles/__init__.py', 'lowest_connector')}


def _violations(source, path=''):
    found = []
    tree = ast.parse(source)
    allowed = {id(node) for fn in ast.walk(tree)
               if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and (path, fn.name) in _ALLOWED
               for node in ast.walk(fn)}
    for node in ast.walk(tree):
        if id(node) in allowed:
            continue
        if isinstance(node, ast.Attribute) and node.attr == 'get_singleton':
            found.append(node.lineno)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in _SINGLE_ROW
                and any(isinstance(n, ast.Name) and n.id == 'ADConnectorConfig' for n in ast.walk(node.func.value))):
            found.append(node.lineno)
    return found


def test_the_guard_sees_an_implicit_connector_read():
    assert _violations('x = ADConnectorConfig.get_singleton()') == [1]
    assert _violations('x = ADConnectorConfig.query.first()') == [1]
    assert _violations('x = ADConnectorConfig.query.filter_by(a=1).first()') == [1]
    limited = 'x = db.session.scalars(select(ADConnectorConfig).order_by(ADConnectorConfig.id).limit(1)).one_or_none()'
    assert _violations(limited) == [1]
    assert _violations(f'def lowest_connector():\n    {limited}', 'api/v2/other.py') == [2]
    assert _violations(f'def other():\n    {limited}', 'services/windows_profiles/__init__.py') == [2]
    assert _violations(f'def lowest_connector():\n    {limited}', 'services/windows_profiles/__init__.py') == []
    assert _violations('x = Other.query.first()\ny = ADConnectorConfig.query.all()') == []


def test_no_code_reads_the_connector_without_naming_it():
    root = Path(__file__).resolve().parents[1]
    offenders = []
    for path in root.rglob('*.py'):
        relative = path.relative_to(root).parts
        if relative[0] in ('tests', 'data') or any(part.startswith('.') or part == 'node_modules' for part in relative):
            continue
        name = '/'.join(relative)
        offenders += [f'{name}:{line}' for line in _violations(path.read_text(), name)]
    assert offenders == []


# Criterion 4
def _body(**values):
    body = {'name': 'forest-a', 'servers': ['dc1.a.example'], 'base_dn': 'DC=a,DC=example',
            'bind_dn': 'svc', 'bind_password': 'sekret-pw', 'enabled': True}
    body.update(values)
    return body


def _post(client, **values):
    return client.post(URL, data=json.dumps(_body(**values)), content_type='application/json')


def test_a_connector_is_created_with_the_domain_sid_and_no_secret(auth_client, app, monkeypatch):
    with app.app_context():
        AuditLog.query.filter_by(action='ad_connector_create', resource_name='forest-a').delete()
        db.session.commit()
    _Directory(monkeypatch, [_Entry(objectSid=_sid_bytes(DOMAIN_SID))])
    monkeypatch.setattr(lookup, '_connect', lambda config: _Conn([_Entry(objectSid=_sid_bytes(DOMAIN_SID))]))
    response = _post(auth_client)
    assert response.status_code == 201, response.data
    data = response.get_json()['data']
    assert (data['name'], data['domain_sid'], data['realm']) == ('forest-a', DOMAIN_SID, 'A.EXAMPLE')
    assert data['bind_password'] == '***' and 'sekret-pw' not in response.get_data(as_text=True)
    listing = auth_client.get(URL).get_json()['data']
    assert [row['name'] for row in listing] == ['forest-a']
    assert 'sekret-pw' not in json.dumps(listing)
    with app.app_context():
        assert AuditLog.query.filter_by(action='ad_connector_create', resource_name='forest-a').count() == 1


def test_the_domain_sid_is_read_at_the_domain_head_whatever_the_base_dn_depth(auth_client, monkeypatch):
    searched = []

    class Conn(_Conn):
        def search(self, base, *args, **kwargs):
            searched.append(base)
            self.entries = [_Entry(objectSid=_sid_bytes(DOMAIN_SID))] if base == 'DC=a,DC=example' else []
            return True

    monkeypatch.setattr(lookup, '_connect', lambda config: Conn([]))
    response = _post(auth_client, base_dn='OU=Computers,DC=a,DC=example')
    assert response.status_code == 201, response.data
    data = response.get_json()['data']
    assert (data['realm'], data['domain_sid']) == ('A.EXAMPLE', DOMAIN_SID)
    assert searched == ['DC=a,DC=example']


def test_a_created_connector_serves_a_default_profile_that_had_none(auth_client, app, monkeypatch):
    from services import windows_profiles
    from tests.windows_profile_support import default_profile

    monkeypatch.setattr(lookup, '_connect', lambda config: (_ for _ in ()).throw(OSError('down')))
    with app.app_context():
        made = default_profile() is None
        profile = default_profile(create=True)
        profile.connector_id = None
        db.session.commit()
        profile_id = profile.id
    try:
        created = _post(auth_client).get_json()['data']
        with app.app_context():
            assert windows_profiles.default_connector().id == created['id']
        other = _post(auth_client, name='forest-b', servers=['dc.b.example'],
                      base_dn='DC=b,DC=example').get_json()['data']
        with app.app_context():
            assert windows_profiles.default_connector().id == created['id'] != other['id']
    finally:
        # A profile this test made would hide the no-profile fallback from later tests
        if made:
            with app.app_context():
                WindowsEnrollmentProfile.query.filter_by(id=profile_id).delete()
                db.session.commit()


def test_a_second_connector_coexists_and_a_duplicate_name_is_refused(auth_client, monkeypatch):
    monkeypatch.setattr(lookup, '_connect', lambda config: (_ for _ in ()).throw(OSError('down')))
    assert _post(auth_client).status_code == 201
    assert _post(auth_client, servers=['dc.b.example'], base_dn='DC=b,DC=example').status_code == 409
    other = _post(auth_client, name='forest-b', servers=['dc.b.example'], base_dn='DC=b,DC=example')
    assert other.status_code == 201
    assert other.get_json()['data']['domain_sid'] is None
    assert len(auth_client.get(URL).get_json()['data']) == 2


@pytest.mark.parametrize('base_dn', ['', 'OU=People', 'not a dn'])
def test_a_base_dn_without_a_realm_is_refused(auth_client, app, base_dn):
    response = _post(auth_client, base_dn=base_dn)
    assert response.status_code == 400
    with app.app_context():
        assert ADConnectorConfig.query.count() == 0


def test_an_update_renames_and_a_new_base_dn_drops_the_old_domain_sid(auth_client, app, monkeypatch):
    monkeypatch.setattr(lookup, '_connect', lambda config: _Conn([_Entry(objectSid=_sid_bytes(DOMAIN_SID))]))
    created = _post(auth_client).get_json()['data']
    with app.app_context():
        # A default profile another file left, keytab and all, took the new connector: the move is not its test
        WindowsEnrollmentProfile.query.filter_by(connector_id=created['id']).update({'connector_id': None})
        db.session.commit()
    monkeypatch.setattr(lookup, '_connect', lambda config: (_ for _ in ()).throw(OSError('down')))
    updated = auth_client.put(f"{URL}/{created['id']}", data=json.dumps({'name': 'renamed', 'base_dn': 'DC=c,DC=example'}),
                              content_type='application/json')
    assert updated.status_code == 200, updated.data
    data = updated.get_json()['data']
    assert (data['name'], data['domain_sid'], data['realm']) == ('renamed', None, 'C.EXAMPLE')
    assert data['bind_password'] == '***'


def test_a_saved_connector_is_tested_by_id_and_the_test_stores_its_domain_sid(auth_client, app, monkeypatch):
    monkeypatch.setattr(lookup, '_connect', lambda config: (_ for _ in ()).throw(OSError('down')))
    created = _post(auth_client).get_json()['data']
    _Directory(monkeypatch, [_Entry(objectSid=_sid_bytes(DOMAIN_SID))])
    response = auth_client.post(f"{URL}/{created['id']}/test")
    assert response.status_code == 200, response.data
    assert response.get_json()['data']['domain_sid'] == DOMAIN_SID
    with app.app_context():
        assert db.session.get(ADConnectorConfig, created['id']).domain_sid == DOMAIN_SID
    assert auth_client.post(f'{URL}/987654/test').status_code == 404


def test_unsaved_values_are_tested_and_a_blank_password_only_follows_its_target(auth_client, monkeypatch):
    monkeypatch.setattr(lookup, '_connect', lambda config: (_ for _ in ()).throw(OSError('down')))
    created = _post(auth_client).get_json()['data']
    seen = []
    directory = _Directory(monkeypatch, [_Entry(objectSid=_sid_bytes(DOMAIN_SID))])
    original = directory._bind

    def recording(config, host, tls):
        seen.append(config.bind_password)
        return original(config, host, tls)

    monkeypatch.setattr(lookup, '_connect_to', recording)
    values = {'servers': ['dc1.a.example'], 'bind_dn': 'svc', 'port': 389, 'base_dn': 'DC=a,DC=example'}
    ok = auth_client.post(f'{URL}/test', data=json.dumps({**values, 'id': created['id']}), content_type='application/json')
    assert ok.status_code == 200, ok.data
    assert ok.get_json()['data']['domain_sid'] == DOMAIN_SID
    assert seen == ['sekret-pw']
    elsewhere = auth_client.post(f'{URL}/test', data=json.dumps({**values, 'servers': ['evil.example'], 'id': created['id']}),
                                 content_type='application/json')
    assert elsewhere.status_code == 400 and seen == ['sekret-pw']


def _using(connector_id):
    return [{'id': p.id, 'name': p.name} for p in WindowsEnrollmentProfile.query.filter_by(
        connector_id=connector_id).order_by(WindowsEnrollmentProfile.name)]


def test_a_connector_a_profile_uses_cannot_be_deleted(auth_client, app, monkeypatch):
    monkeypatch.setattr(lookup, '_connect', lambda config: (_ for _ in ()).throw(OSError('down')))
    used = _post(auth_client).get_json()['data']
    free = _post(auth_client, name='forest-b', servers=['dc.b.example'], base_dn='DC=b,DC=example').get_json()['data']
    with app.app_context():
        # A default profile another file left without a connector took this one when it was created
        already = _using(used['id'])
        profile = WindowsEnrollmentProfile(name='c02a-profile', realm='C02A.EXAMPLE', connector_id=used['id'])
        db.session.add(profile)
        db.session.commit()
        profile_id = profile.id
    try:
        refused = auth_client.delete(f"{URL}/{used['id']}")
        assert refused.status_code == 409
        # The refusal names the profiles that use the connector
        assert refused.get_json()['details']['profiles'] == sorted(
            already + [{'id': profile_id, 'name': 'c02a-profile'}], key=lambda p: p['name'])
        assert auth_client.delete(f"{URL}/{free['id']}").status_code == 204
        assert auth_client.get(f"{URL}/{free['id']}").status_code == 404
    finally:
        with app.app_context():
            WindowsEnrollmentProfile.query.filter_by(id=profile_id).delete()
            db.session.commit()
    with app.app_context():
        assert db.session.get(ADConnectorConfig, used['id']) is not None
        assert AuditLog.query.filter_by(action='ad_connector_delete', resource_id=str(free['id'])).count() == 1


def test_a_viewer_cannot_read_or_write_connectors(viewer_client):
    assert viewer_client.get(URL).status_code == 403
    assert _post(viewer_client).status_code == 403


def test_the_default_profile_names_the_connector_the_protocols_search_with(app):
    from services import windows_profiles
    a, b = _pair(app)
    with app.app_context():
        existing = windows_profiles.default_profile()
        if existing is not None:
            existing.is_default = False
            db.session.commit()
        try:
            assert windows_profiles.default_connector().id == a  # no default profile: the lowest row
        finally:
            if existing is not None:
                existing.is_default = True
                db.session.commit()
        profile = windows_profiles.default_profile()
        created = profile is None
        if created:
            profile = WindowsEnrollmentProfile(name='default', is_default=True, enabled=True)
            db.session.add(profile)
        saved = profile.connector_id
        try:
            profile.connector_id = b
            db.session.commit()
            assert windows_profiles.default_connector().id == b
            profile.connector_id = None
            db.session.commit()
            assert windows_profiles.default_connector() is None
        finally:
            if created:
                db.session.delete(profile)
            else:
                profile.connector_id = saved
            db.session.commit()


def test_a_save_reads_the_domain_sid_and_reads_it_again_for_a_new_dc_list(auth_client, app, monkeypatch):
    sids = [DOMAIN_SID]
    monkeypatch.setattr(lookup, '_connect', lambda config: _Conn([_Entry(objectSid=_sid_bytes(sids[0]))]))

    def put(**values):
        body = {'servers': ['dc1.a.example'], 'base_dn': 'DC=a,DC=example', 'bind_dn': 'svc',
                'bind_password': 'sekret-pw', 'enabled': True}
        body.update(values)
        response = save_connector(auth_client, body)
        assert response.status_code in (200, 201), response.data
        with app.app_context():
            return ADConnectorConfig.query.one().domain_sid

    assert put() == DOMAIN_SID
    sids[0] = 'S-1-5-21-1-2-3'
    assert put(servers=['dc1.a.example', 'dc2.a.example']) == 'S-1-5-21-1-2-3'


def test_a_new_connector_is_served_by_a_default_profile_that_names_none(auth_client, app, monkeypatch):
    """A default profile naming no connector takes the first one a save creates."""
    from services import windows_profiles
    from tests.windows_profile_support import default_profile
    monkeypatch.setattr(lookup, '_connect', lambda config: (_ for _ in ()).throw(OSError('down')))
    with app.app_context():
        made = default_profile() is None
        profile = default_profile(create=True)
        saved, profile.connector_id = profile.connector_id, None
        db.session.commit()
        profile_id = profile.id
        existing = add_connector('default', server='dc.a.example', base_dn='DC=a,DC=example',
                                 bind_dn='svc', enabled=True).id
    try:
        body = {'name': 'second', 'servers': ['dc.b.example'], 'base_dn': 'DC=b,DC=example',
                'bind_dn': 'svc', 'bind_password': 'sekret-pw', 'enabled': True}
        response = auth_client.post(URL, data=json.dumps(body), content_type='application/json')
        assert response.status_code == 201, response.data
        created = response.get_json()['data']['id']
        with app.app_context():
            assert created != existing and windows_profiles.default_connector().id == created
    finally:
        with app.app_context():
            if made:
                WindowsEnrollmentProfile.query.filter_by(id=profile_id).delete()
            else:
                db.session.get(WindowsEnrollmentProfile, profile_id).connector_id = saved
            db.session.commit()


@pytest.mark.parametrize('route', ['create', 'rename'])
def test_a_name_taken_by_a_concurrent_save_answers_409(auth_client, app, monkeypatch, route):
    """The name check passed before the other writer committed: the unique key decides."""
    from api.v2 import ad_connectors
    from services import windows_profiles
    monkeypatch.setattr(lookup, '_connect', lambda config: (_ for _ in ()).throw(OSError('down')))
    with app.app_context():
        parked = windows_profiles.default_profile()
        if parked is not None:
            parked.is_default = False
        db.session.commit()
        parked_id = parked.id if parked is not None else None
    try:
        mine = _post(auth_client, name='race-mine').get_json()['data'] if route == 'rename' else None
        with app.app_context():
            add_connector('race-taken', server='dc.r.example', base_dn='DC=r,DC=example')
        monkeypatch.setattr(ad_connectors, '_name_error', lambda data, current=None: (data['name'], None))
        if route == 'create':
            response = _post(auth_client, name='race-taken')
        else:
            response = auth_client.put(f"{URL}/{mine['id']}", data=json.dumps({'name': 'race-taken'}),
                                       content_type='application/json')
        assert response.status_code == 409, response.data
    finally:
        if parked_id is not None:
            with app.app_context():
                db.session.get(WindowsEnrollmentProfile, parked_id).is_default = True
                db.session.commit()


@pytest.mark.parametrize('connector_id', [True, False])
def test_a_boolean_id_names_no_connector(auth_client, monkeypatch, connector_id):
    """``True`` is an int to isinstance: it would lend connector 1's saved password."""
    real_get, looked_up = db.session.get, []

    def get(model, ident, *args, **kwargs):
        if model is ADConnectorConfig:
            looked_up.append(ident)
        return real_get(model, ident, *args, **kwargs)

    monkeypatch.setattr(db.session, 'get', get)
    body = {'servers': ['dc1.a.example'], 'bind_dn': 'svc', 'base_dn': 'DC=a,DC=example', 'id': connector_id}
    response = auth_client.post(f'{URL}/test', data=json.dumps(body), content_type='application/json')
    assert response.status_code == 404, response.data
    assert looked_up == []


def test_a_save_reads_the_domain_sid_within_one_connect_timeout(auth_client, monkeypatch):
    """Every DC black-holed: the save waits the connection test's per-DC connect timeout once, not once per DC."""
    directory = _Directory(monkeypatch, [], down={'dc1.a.example', 'dc2.a.example', 'dc3.a.example'})
    now, bind = [0.0], directory._bind

    def slow_bind(config, host, tls):
        now[0] += lookup._LDAP_CONNECT_TIMEOUT_SECONDS
        return bind(config, host, tls)

    monkeypatch.setattr(lookup, '_connect_to', slow_bind)
    monkeypatch.setattr(lookup, '_clock', lambda: now[0])
    servers = ['dc1.a.example', 'dc2.a.example', 'dc3.a.example']
    response = _post(auth_client, servers=servers)
    assert response.status_code in (200, 201), response.data
    assert response.get_json()['data']['domain_sid'] is None
    assert [host for _name, host in directory.binds] == ['dc1.a.example']


def test_a_refused_deletion_counts_every_profile_but_lists_the_first_fifty(auth_client, app):
    used = _post(auth_client, name='forest-many', servers=['dc.m.example'], base_dn='DC=m,DC=example').get_json()['data']
    with app.app_context():
        already = len(_using(used['id']))
        db.session.add_all([WindowsEnrollmentProfile(name=f'c07-many-{i:03d}', connector_id=used['id'])
                            for i in range(51)])
        db.session.commit()
    try:
        refused = auth_client.delete(f"{URL}/{used['id']}")
        assert refused.status_code == 409
        details = refused.get_json()['details']
        assert details['total'] == 51 + already and len(details['profiles']) == 50
    finally:
        with app.app_context():
            WindowsEnrollmentProfile.query.filter(WindowsEnrollmentProfile.name.like('c07-many-%')).delete(
                synchronize_session=False)
            db.session.commit()
        auth_client.delete(f"{URL}/{used['id']}")
