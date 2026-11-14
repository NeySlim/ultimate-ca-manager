"""Migration 155: a 2.x base of either backend gets a default Windows enrollment profile carrying
exactly its XCEP/WSTEP configuration, the settings it replaces are gone, the WSTEP certificates
are attached to it, and the realm follows A1 (connector, SPN, keytab; none: Kerberos refused)."""
import base64
import importlib
import os
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from models import ADConnectorConfig, Certificate, SystemConfig, WindowsEnrollmentProfile
from services.windows_profiles.legacy import MIGRATED_KEYS, profile_from_2x

PG_URL = os.getenv('UCM_TEST_PG_URL')
FIXTURES = Path(__file__).parent / 'fixtures'
PROFILES, CONNECTORS = WindowsEnrollmentProfile.__tablename__, ADConnectorConfig.__tablename__
CERTS, SETTINGS = Certificate.__tablename__, SystemConfig.__tablename__
# Real MIT keytabs (ktutil): HTTP/ucm.example in ONE.EXAMPLE and TWO.EXAMPLE; one in EXAMPLE.TEST
TWO_REALMS = base64.b64decode(
    'BQIAAABTAAIAC09ORS5FWEFNUExFAARIVFRQAAt1Y20uZXhhbXBsZQAAAAFq9jRZAwASACCkscNWEQA3t9IRlwlWm4s+'
    'Jd/2w4uIRuPYHUWQ6+MoNwAAAAMAAABDAAIAC1RXTy5FWEFNUExFAARIVFRQAAt1Y20uZXhhbXBsZQAAAAFq9jRZAQAR'
    'ABBkB8g0vovY6bCxhOLdesjNAAAAAQ==')
ONE_REALM = base64.b64decode(
    'BQIAAABeAAIADEVYQU1QTEUuVEVTVAAESFRUUAAVdGVzdGhvc3QuZXhhbXBsZS50ZXN0AAAA'
    'AWd0hYABABIAIAABAgMEBQYHCAkKCwwNDg8QERITFBUWFxgZGhscHR4fAAAAAQ==')

SETTINGS_2X = {
    'xcep_enabled': 'true', 'xcep_ca_refid': 'ca-policy', 'xcep_username': 'cep-user',
    'xcep_password': 'pbkdf2:sha256:600000$salt$cep', 'wstep_enabled': 'true',
    'wstep_ca_refid': 'ca-issue', 'wstep_username': 'ces-user',
    'wstep_password': 'pbkdf2:sha256:600000$salt$ces', 'wstep_validity_days': '30',
    'kerberos_enabled': 'true', 'kerberos_spn': 'HTTP/ucm.corp.example',
}
CONNECTOR_2X = {'id': 1, 'enabled': True, 'base_dn': 'DC=corp,DC=example'}
PROFILE_COLUMNS = ('name', 'realm', 'is_default', 'enabled', 'connector_id', 'issuing_ca_refid',
                   'policy_ca_refid', 'validity_days', 'xcep_username', 'xcep_password',
                   'wstep_username', 'wstep_password')


def _migration():
    return importlib.import_module('migrations._from_2_254.155_windows_enrollment_profiles')


def _schema_2x(dialect):
    return (FIXTURES / f'schema_v2254_{dialect}.sql').read_text()


class _Base:
    """A 2.x base on one backend: ``run`` executes SQL, ``migrate`` runs 155 alone."""

    def __init__(self, run, migrate, upgrade_all):
        self.run, self.migrate, self.upgrade_all = run, migrate, upgrade_all

    def seed(self, settings=SETTINGS_2X, connector=CONNECTOR_2X):
        for refid in ('ca-issue', 'ca-policy'):
            self.run(f"INSERT INTO certificate_authorities (refid, descr, crt, signature_scheme, "
                     f"issuance_hidden) VALUES ('{refid}', '{refid}', 'x', 'pkcs1v15', FALSE)")
        for refid, source in (('c-wstep', 'wstep'), ('c-est', 'est'), ('c-wstep-2', 'wstep')):
            self.run(f"INSERT INTO {CERTS} (refid, descr, source, renewed_times) "
                     f"VALUES ('{refid}', '{refid}', '{source}', 0)")
        if connector:
            self.run(f"INSERT INTO {CONNECTORS} (id, server, base_dn, enabled) VALUES "
                     f"({connector['id']}, 'dc1', '{connector['base_dn']}', "
                     f"{'TRUE' if connector['enabled'] else 'FALSE'})")
        for key, value in settings.items():
            self.run(f"INSERT INTO {SETTINGS} (key, value) VALUES ('{key}', '{value}')")

    def rows(self, sql):
        return [tuple(r) for r in self.run(sql)]

    def profiles(self):
        return [dict(zip(PROFILE_COLUMNS, row, strict=True)) for row in self.rows(
            f"SELECT {', '.join(PROFILE_COLUMNS)} FROM {PROFILES} ORDER BY id")]


@pytest.fixture
def sqlite_base(tmp_path):
    path = tmp_path / 'ucm2x.db'
    conn = sqlite3.connect(path)
    conn.executescript(_schema_2x('sqlite'))
    conn.commit()

    def run(sql):
        rows = conn.execute(sql.replace('TRUE', '1').replace('FALSE', '0')).fetchall()
        conn.commit()
        return rows

    def upgrade_all():
        import migration_runner
        applied = {n for (n,) in conn.execute("SELECT name FROM _migrations")}
        pending = [n for n in migration_runner._list_migration_names() if n not in applied]
        assert migration_runner._run_pending_sqlite(pending, False, db_path=str(path))

    yield _Base(run, lambda keytab=b'': _migration().upgrade_sqlite(conn, keytab=keytab), upgrade_all)
    conn.close()


@pytest.fixture
def pg_base():
    if not PG_URL:
        pytest.skip('UCM_TEST_PG_URL not set')
    schema = f"migtest_155_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    admin = create_engine(PG_URL)
    with admin.begin() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(PG_URL, connect_args={'options': f'-csearch_path={schema}'})
    with engine.begin() as conn:
        conn.exec_driver_sql(_schema_2x('postgresql'))

    def run(sql):
        with engine.begin() as conn:
            result = conn.execute(text(sql))
            return result.fetchall() if result.returns_rows else []

    def migrate(keytab=b''):
        with engine.begin() as conn:
            _migration().upgrade_pg(conn, keytab=keytab)

    def upgrade_all():
        import migration_runner
        with engine.connect() as conn:
            applied = {n for (n,) in conn.execute(text("SELECT name FROM _migrations"))}
        pending = [n for n in migration_runner._list_migration_names() if n not in applied]
        assert migration_runner._run_pending_pg(engine, pending, False)

    try:
        yield _Base(run, migrate, upgrade_all)
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        admin.dispose()


BACKENDS = [pytest.param('sqlite_base', id='sqlite'),
            pytest.param('pg_base', id='postgresql', marks=pytest.mark.postgres)]


@pytest.fixture(params=BACKENDS)
def base(request):
    return request.getfixturevalue(request.param)


EXPECTED = {'name': 'default', 'realm': 'CORP.EXAMPLE', 'is_default': True, 'enabled': True,
            'connector_id': 1, 'issuing_ca_refid': 'ca-issue', 'policy_ca_refid': 'ca-policy',
            'validity_days': 30, 'xcep_username': 'cep-user',
            'xcep_password': SETTINGS_2X['xcep_password'], 'wstep_username': 'ces-user',
            'wstep_password': SETTINGS_2X['wstep_password']}


def _normalised(profiles):
    return [{k: bool(v) if k in ('is_default', 'enabled') else v for k, v in p.items()} for p in profiles]


def test_the_2x_configuration_becomes_the_default_profile(base):
    base.seed()
    base.migrate()
    assert _normalised(base.profiles()) == [EXPECTED]
    left = {k for (k,) in base.rows(f"SELECT key FROM {SETTINGS}")}
    assert not left & set(MIGRATED_KEYS)
    assert {'xcep_enabled', 'wstep_enabled', 'kerberos_enabled', 'kerberos_spn'} <= left
    assert base.rows(f"SELECT name FROM {CONNECTORS}") == [('default',)]


def test_wstep_certificates_are_attached_to_the_default_profile(base):
    base.seed()
    base.migrate()
    (profile_id,), = base.rows(f"SELECT id FROM {PROFILES}")
    assert dict(base.rows(f"SELECT refid, windows_profile_id FROM {CERTS}")) == {
        'c-wstep': profile_id, 'c-wstep-2': profile_id, 'c-est': None}


def test_a_replayed_migration_adds_nothing(base):
    base.seed()
    base.migrate()
    base.migrate()
    assert _normalised(base.profiles()) == [EXPECTED]


def test_a_base_without_windows_configuration_gets_no_profile(base):
    base.seed(settings={'xcep_enabled': 'false', 'scep_enabled': 'true'}, connector=None)
    base.migrate()
    assert base.profiles() == []
    assert base.rows(f"SELECT windows_profile_id FROM {CERTS} WHERE windows_profile_id IS NOT NULL") == []


@pytest.mark.parametrize('connector, spn, keytab, realm', [
    (CONNECTOR_2X, 'HTTP/ucm@SPN.EXAMPLE', ONE_REALM, 'CORP.EXAMPLE'),
    ({**CONNECTOR_2X, 'enabled': False}, 'HTTP/ucm@SPN.EXAMPLE', ONE_REALM, 'SPN.EXAMPLE'),
    (None, 'HTTP/ucm', ONE_REALM, 'EXAMPLE.TEST'),
], ids=['connector', 'spn', 'keytab'])
def test_the_realm_comes_from_the_connector_then_the_spn_then_the_keytab(base, connector, spn, keytab, realm):
    base.seed(settings={**SETTINGS_2X, 'kerberos_spn': spn}, connector=connector)
    base.migrate(keytab=keytab)
    profile, = base.profiles()
    assert profile['realm'] == realm and bool(profile['enabled'])


DISABLED = {**CONNECTOR_2X, 'enabled': False}


@pytest.mark.parametrize('connector, spn, keytab, realm, warned', [
    (DISABLED, 'HTTP/ucm@SPN.EXAMPLE', TWO_REALMS, 'SPN.EXAMPLE', True),
    (DISABLED, 'HTTP/ucm', ONE_REALM, 'EXAMPLE.TEST', True),
    ({**DISABLED, 'base_dn': 'DC=one,DC=example'}, 'HTTP/ucm', TWO_REALMS, 'ONE.EXAMPLE', False),
    (DISABLED, 'HTTP/ucm', TWO_REALMS, None, True),
    (DISABLED, 'HTTP/ucm', b'', None, False),
], ids=['spn', 'one-realm-keytab', 'dn-in-keytab', 'dn-not-in-keytab', 'dn-keytab-not-read'])
def test_a_disabled_connector_names_the_realm_last(base, connector, spn, keytab, realm, warned, caplog):
    """2.x served the SPN's realm, else the keytab's, while the connector was disabled: kept;
    its base DN is the last resort, only for a realm the keytab holds or once none exists (start)."""
    base.seed(settings={**SETTINGS_2X, 'kerberos_spn': spn}, connector=connector)
    with caplog.at_level('WARNING', logger='services.windows_profiles.legacy'):
        base.migrate(keytab=keytab)
    profile, = base.profiles()
    assert profile['realm'] == realm and bool(profile['enabled'])
    assert ('differs from the realm of the connector' in caplog.text) == warned


NO_DC = {**CONNECTOR_2X, 'base_dn': 'OU=Servers,O=corp'}
SPN_NO_REALM = {**SETTINGS_2X, 'kerberos_spn': 'HTTP/ucm.example'}
UNDETERMINABLE = [
    pytest.param(SPN_NO_REALM, None, TWO_REALMS, id='two-realm-keytab-no-connector'),
    pytest.param(SPN_NO_REALM, {**CONNECTOR_2X, 'enabled': False, 'base_dn': 'DC=other,DC=example'},
                 TWO_REALMS, id='two-realm-keytab-connector-disabled'),
    pytest.param(SPN_NO_REALM, NO_DC, TWO_REALMS, id='two-realm-keytab-connector-without-dc'),
    pytest.param({**SETTINGS_2X, 'kerberos_spn': ''}, None, TWO_REALMS, id='kerberos-enabled-empty-spn'),
]


@pytest.mark.parametrize('settings, connector, keytab', UNDETERMINABLE)
def test_an_undeterminable_realm_leaves_the_profile_enabled_without_realm(base, settings, connector,
                                                                          keytab, caplog):
    """A1 refuses Kerberos only: the profile stays enabled, so the other bindings serve as in 2.x."""
    base.seed(settings=settings, connector=connector)
    with caplog.at_level('WARNING', logger='services.windows_profiles.legacy'):
        base.migrate(keytab=keytab)
    profile, = base.profiles()
    assert profile['realm'] is None and bool(profile['enabled'])
    warned = 'default profile has no realm: Kerberos refused until one is set' in caplog.text
    # Only where 2.x served Kerberos (enabled, SPN, keytab) does the refusal change anything
    assert warned == bool(settings['kerberos_spn'])


def test_without_kerberos_in_use_an_unknown_realm_does_not_disable(base, caplog):
    base.seed(settings={**SETTINGS_2X, 'kerberos_enabled': 'false', 'kerberos_spn': 'HTTP/ucm'},
              connector=None)
    with caplog.at_level('WARNING', logger='services.windows_profiles.legacy'):
        base.migrate(keytab=TWO_REALMS)
    profile, = base.profiles()
    assert profile['realm'] is None and profile['enabled']
    assert 'no realm' not in caplog.text


@pytest.mark.parametrize('changes, switch', [
    ({'xcep_ca_refid': ''}, 'false'),
    ({'xcep_ca_refid': None}, 'false'),
    ({}, 'true'),
    ({'xcep_ca_refid': None, 'wstep_ca_refid': None}, 'true'),
    ({'xcep_ca_refid': None, 'xcep_enabled': 'false'}, 'false'),
], ids=['empty-xcep-ca', 'absent-xcep-ca', 'xcep-ca', 'no-ca-at-all', 'already-off'])
def test_xcep_without_its_own_ca_is_switched_off(base, changes, switch):
    """2.x served no policy without an XCEP CA; the profile would serve the issuing CA's (A4)."""
    settings = {k: v for k, v in {**SETTINGS_2X, **changes}.items() if v is not None}
    base.seed(settings=settings)
    base.migrate()
    base.migrate()
    assert base.rows(f"SELECT value FROM {SETTINGS} WHERE key = 'xcep_enabled'") == [(switch,)]


def test_upgrading_a_real_2x_base_gives_the_direct_conversion(base):
    """The upgrade from 2.254, on its schema: the profile is the conversion of the settings."""
    base.seed()
    base.upgrade_all()
    direct = profile_from_2x(SETTINGS_2X, CONNECTOR_2X, None)
    assert _normalised(base.profiles()) == [{k: direct[k] for k in PROFILE_COLUMNS}]
    assert base.rows("SELECT name FROM _migrations WHERE name = '300_upgrade_from_2_254'")


def test_the_app_schema_has_the_migrated_columns(app):
    from sqlalchemy import inspect
    from models import db
    with app.app_context():
        inspector = inspect(db.engine)
        assert {'name', 'domain_sid'} <= {c['name'] for c in inspector.get_columns(CONNECTORS)}
        assert 'windows_profile_id' in {c['name'] for c in inspector.get_columns(CERTS)}
        migrated = set(_migration()._INSERT_FIELDS) | {'keytab', 'allowed_ad_group', 'pinned_subject_fields'}
        assert migrated <= {c['name'] for c in inspector.get_columns(PROFILES)}
