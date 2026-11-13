"""C-08: 150 profiles and 150 connectors cost what two do (SQLite, and PostgreSQL with UCM_TEST_APP_PG_URL).

Bounds are numbers (statements, binds, entries), never wall-clock time."""
import threading

import pytest
from sqlalchemy import event

from models import ADConnectorConfig, WindowsEnrollmentProfile, db
from services import windows_profiles
from services.wstep import CES_KERBEROS_PATH
from services.ad_connector import lookup
from services.ad_connector.lookup import lookup_object_sid as real_lookup_object_sid
from tests.ad_connector_support import add_connector
from tests.test_ad_connectors_collection import DOMAIN_SID, _Directory, _Entry, _sid_bytes
from tests.test_windows_profile_routing import (CEP_KERBEROS, _issue, _policy, _policy_of,  # noqa: F401
                                                world)
from tests.test_keytab_composed import profiles  # noqa: F401
from tests.windows_profile_support import connectors_kept
from tests.windows_profile_support import windows_profiles_restored  # noqa: F401

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')
TOTAL = 150


def _statements(app, call):
    """(statements run on this thread by call(), its result)."""
    seen, mine = [], threading.get_ident()

    def hook(conn, cursor, statement, parameters, *rest):
        if threading.get_ident() == mine:
            seen.append((statement, parameters))

    from utils.admin_allowlist import invalidate_cache
    with app.app_context():
        # The allowlist cache expires after seconds: read on every counted call, never on one of two
        invalidate_cache()
        event.listen(db.engine, 'before_cursor_execute', hook)
        try:
            result = call()
        finally:
            event.remove(db.engine, 'before_cursor_execute', hook)
    return seen, result


def _fill_profiles(app):
    """Profiles up to TOTAL in all, named c04-fill-N so the routing world's teardown removes them."""
    with app.app_context():
        missing = TOTAL - WindowsEnrollmentProfile.query.count()
        db.session.add_all(WindowsEnrollmentProfile(name=f'c04-fill-{i:03d}', realm=f'FILL{i:03d}.TEST',
                                                    enabled=True) for i in range(missing))
        db.session.commit()
        assert WindowsEnrollmentProfile.query.count() == TOTAL


def _fill_connectors(app):
    with app.app_context():
        for i in range(TOTAL - ADConnectorConfig.query.count()):
            add_connector(f'fill-{i:03d}', server=f'dc.fill{i}.test', base_dn=f'DC=fill{i},DC=test',
                          bind_dn='svc', enabled=True)
        assert ADConnectorConfig.query.count() >= TOTAL


# Criterion 1
def test_the_realm_of_a_principal_is_resolved_by_one_indexed_query(app, world):
    _fill_profiles(app)
    seen, profile = _statements(app, lambda: windows_profiles.profile_for_realm('FILL077.TEST'))
    with app.app_context():
        assert profile.name == 'c04-fill-077'
        assert len(seen) == 1
        statement, parameters = seen[0]
        connection = db.session.connection()
        if db.engine.dialect.name == 'postgresql':
            # The planner prefers a scan of 150 rows: forbid it, the unique index must remain usable
            connection.exec_driver_sql('SET LOCAL enable_seqscan = off')
            plan = '\n'.join(r[0] for r in connection.exec_driver_sql('EXPLAIN ' + statement, parameters))
            assert 'Index' in plan and 'realm' in plan, plan
            db.session.rollback()
        else:
            plan = ' '.join(r[3] for r in connection.exec_driver_sql('EXPLAIN QUERY PLAN ' + statement, parameters))
            assert 'USING' in plan and 'INDEX' in plan and 'SCAN' not in plan, plan


# Criterion 2
def test_get_policies_costs_the_same_statements_with_150_profiles(app, client, world):
    _policy_of(client, world, 'hostA$@C04A.TEST')  # warm-up: first-use reads are not the cost
    with app.app_context():
        few = WindowsEnrollmentProfile.query.count()
    base, response = _statements(app, lambda: _policy_of(client, world, 'hostA$@C04A.TEST'))
    expected = _policy(response)
    _fill_profiles(app)
    many, response = _statements(app, lambda: _policy_of(client, world, 'hostA$@C04A.TEST'))
    assert few < TOTAL and _policy(response) == expected
    assert [s for s, _p in many] == [s for s, _p in base]


# Criterion 3
def test_a_kerberos_issuance_binds_as_often_with_150_connectors_as_with_one(app, client, world, monkeypatch):
    monkeypatch.setattr(lookup, 'lookup_object_sid', real_lookup_object_sid)
    directory = _Directory(monkeypatch, [_Entry(objectSid=_sid_bytes(DOMAIN_SID + '-1105'))])
    assert _issue(client, world, 'userA@C04A.TEST').status_code == 200
    one = list(directory.binds)
    assert one == [('c04-a', 'dc.c04a.test')]
    directory.binds.clear()
    _fill_connectors(app)
    assert _issue(client, world, 'userA@C04A.TEST', cn='c04-host-2').status_code == 200
    assert directory.binds == one


# Criterion 6
def _list_statements(app, auth_client, url):
    seen, response = _statements(app, lambda: auth_client.get(url))
    assert response.status_code == 200, response.data
    return len(seen), response.get_json()['data']


def test_the_profile_list_costs_the_same_statements_on_every_page(app, auth_client, world):
    from models import CA
    with app.app_context():
        refids = [c.refid for c in CA.query.limit(2).all()]
    _fill_profiles(app)
    with app.app_context():
        # Every row names CAs and a connector, so a per-row lookup of either would show
        connector_id = ADConnectorConfig.query.order_by(ADConnectorConfig.id).first().id
        for i, profile in enumerate(WindowsEnrollmentProfile.query.filter(
                WindowsEnrollmentProfile.name.like('c04-fill-%'))):
            profile.issuing_ca_refid, profile.policy_ca_refid = refids[i % 2], refids[(i + 1) % 2]
            profile.connector_id = connector_id
        db.session.commit()
    _list_statements(app, auth_client, '/api/v2/windows-profiles')  # warm-up
    costs = {}
    for url in ('/api/v2/windows-profiles?per_page=5', '/api/v2/windows-profiles?per_page=100',
                '/api/v2/windows-profiles?per_page=100&page=2', '/api/v2/windows-profiles?q=c04-fill&per_page=50'):
        costs[url], rows = _list_statements(app, auth_client, url)
        assert rows
    assert len(set(costs.values())) == 1, costs


def test_the_connector_list_costs_the_same_statements_with_150_connectors_as_with_two(app, auth_client, world):
    few, rows = _list_statements(app, auth_client, '/api/v2/ad-connectors')
    _fill_connectors(app)
    many, rows = _list_statements(app, auth_client, '/api/v2/ad-connectors')
    assert len(rows) >= TOTAL and many == few


# Criterion 7
@pytest.mark.parametrize('path', [CEP_KERBEROS, CES_KERBEROS_PATH], ids=['xcep', 'wstep'])
@pytest.mark.parametrize('trusted', [True, False], ids=['trusted-proxy', 'untrusted-peer'])
def test_the_pending_spnego_context_is_keyed_by_the_client_address(app, client, world, monkeypatch, path, trusted):
    from services.kerberos import negotiate_auth
    from utils.trusted_proxy import _compile_trusted_proxies
    proxy, real_client = '10.8.0.5', '192.0.2.77'
    monkeypatch.setenv('UCM_TRUSTED_PROXIES', proxy if trusted else '10.99.0.1')
    _compile_trusted_proxies.cache_clear()
    keys = []
    monkeypatch.setattr(negotiate_auth, 'is_library_available', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'is_configured', lambda: True)
    monkeypatch.setattr(negotiate_auth, 'authenticate_negotiate', lambda header, key: keys.append(key)
                        or negotiate_auth.NegotiateResult(status='challenge'))
    client.post(path, data=b'',
                headers={'Authorization': 'Negotiate dG9rZW4=', 'X-Forwarded-For': real_client},
                environ_overrides={'REMOTE_ADDR': proxy})
    _compile_trusted_proxies.cache_clear()
    assert keys == [real_client if trusted else proxy]


# Criterion 4
def test_three_probe_passes_over_150_connectors_keep_the_budget_and_reach_every_one(app, monkeypatch):
    import types
    from datetime import timedelta

    from services.ad_connector import health, lookup
    from utils.datetime_utils import utc_now
    reachable_cost, budget = 0.25, health.PROBE_BUDGET_SECONDS
    started = utc_now()
    now, probed = [0.0], []
    monkeypatch.setattr(health, 'utc_now', lambda: started + timedelta(seconds=now[0]))
    with connectors_kept(app):
        with app.app_context():
            ids = [add_connector(f'probe-{i:03d}', server=f'dc.p{i}.test', base_dn=f'DC=p{i},DC=test',
                                 bind_dn='svc', enabled=True, health_probe_interval=30).id
                   for i in range(TOTAL)]
        down = set(ids[3::10])
        assert len(down) == 15

        by_host = {f'dc.p{i}.test': cid for i, cid in enumerate(ids)}

        def fake_connect(config, host, tls, connect_timeout=None):
            # A silent DC costs the connect timeout the caller asked for, as ldap3 would
            is_down = by_host[host] in down
            now[0] += (connect_timeout or lookup._LDAP_CONNECT_TIMEOUT_SECONDS) if is_down else reachable_cost
            probed.append(by_host[host])
            if is_down:
                raise OSError('timed out')
            return types.SimpleNamespace(unbind=lambda: None)

        monkeypatch.setattr(lookup, '_connect_to', fake_connect)
        monkeypatch.setattr(lookup, '_build_tls', lambda config: (None, lambda: None))
        unreachable_cost = lookup._LDAP_CONNECT_TIMEOUT_SECONDS
        for _ in range(3):
            before = now[0]
            with app.app_context():
                health.run_health_probe(budget=budget, clock=lambda: now[0])
            # The budget is checked before each connector: a pass overruns by one probe at most
            assert now[0] - before < budget + unreachable_cost
        assert set(probed) == set(ids)


# Criterion 5
def test_a_keytab_of_450_entries_is_composed_inspected_and_refused_above_its_limit(app, profiles, monkeypatch):
    from services.kerberos import keytab_format, negotiate_auth
    from tests.keytab_support import AES128, AES256, keytab
    from tests.test_keytab_composed import HOST
    types_ = (AES128, AES256, 23)
    with app.app_context():
        for i in range(TOTAL):
            profile = WindowsEnrollmentProfile(name=f'c03-scale-{i:03d}', realm=f'SC{i:03d}.TEST', enabled=True)
            profile.set_keytab(keytab(*[(f'HTTP/{HOST}@SC{i:03d}.TEST', 2, t) for t in types_]))
            db.session.add(profile)
        db.session.commit()
        data = windows_profiles.publish_keytab()
        db.session.commit()
        negotiate_auth.write_stored_keytab()
        entries = keytab_format.read_entries(data)
        assert sorted((e.realm, e.enctype) for e in entries) == sorted(
            (f'SC{i:03d}.TEST', t) for i in range(TOTAL) for t in types_)
        assert len(data) < windows_profiles.MAX_COMPOSED_KEYTAB_SIZE // 10
        listed = negotiate_auth.inspect_keytab()
        assert listed['error'] is None and listed['valid']
        assert len(listed['entries']) == TOTAL * len(types_)

        monkeypatch.setattr(windows_profiles, 'MAX_COMPOSED_KEYTAB_SIZE', len(data) - 1)
        with pytest.raises(ValueError, match=f'above the {len(data) - 1} bytes a node serves'):
            windows_profiles.composed_keytab()


def test_one_keytab_above_the_limit_is_refused_as_a_composition_is(app, profiles, monkeypatch):
    """A single keytab is served as stored: the size a node serves bounds it too."""
    from tests.keytab_support import keytab
    from tests.test_keytab_composed import HOST
    with app.app_context():
        default = db.session.get(WindowsEnrollmentProfile, profiles.default)
        default.set_keytab(keytab(f'HTTP/{HOST}@ONE.TEST'))
        db.session.commit()
        size = len(windows_profiles.composed_keytab())
        monkeypatch.setattr(windows_profiles, 'MAX_COMPOSED_KEYTAB_SIZE', size - 1)
        with pytest.raises(ValueError, match=f'above the {size - 1} bytes a node serves'):
            windows_profiles.composed_keytab()


def test_the_probe_connects_with_its_own_timeout_and_a_lookup_with_the_usual_one(app, monkeypatch):
    """What reaches ldap3: 3 s for a probe, 10 s for a lookup."""
    import types
    import ldap3
    from services.ad_connector import health
    asked = []

    def server(host, **kwargs):
        asked.append(kwargs['connect_timeout'])
        return object()
    monkeypatch.setattr(ldap3, 'Server', server)
    monkeypatch.setattr(ldap3, 'Connection', lambda *a, **k: types.SimpleNamespace(unbind=lambda: None))
    monkeypatch.setattr(lookup, '_build_tls', lambda config: (None, lambda: None))
    with connectors_kept(app), app.app_context():
        config = add_connector('scale-timeout', server='dc.timeout.test', base_dn='DC=timeout,DC=test',
                               bind_dn='svc', enabled=True)
        health.probe(config)
        lookup._connect(config)
    assert asked == [health.PROBE_CONNECT_TIMEOUT_SECONDS, lookup._LDAP_CONNECT_TIMEOUT_SECONDS] == [3, 10]
