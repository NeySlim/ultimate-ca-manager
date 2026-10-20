"""Domain restrictions on EAB credentials.

An account registered through an EAB credential may only order the names
the credential allows: NULL or '*' = everything, [] = nothing.
"""
import importlib
import json
import os
import sqlite3
import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text

from models import db
from models.acme_models import AcmeDomain, AcmeEabCredential, DnsProvider
from models.audit_log import AuditLog
from services.acme.acme_service import AcmeService
from tests.test_acme_security_paths import _build_jws, _nonce, acme_account  # noqa: F401
from utils.datetime_utils import utc_now

API = '/api/v2/acme/eab-credentials'
PG_URL = os.getenv('UCM_TEST_PG_URL')
REJECTED = 'urn:ietf:params:acme:error:rejectedIdentifier'
COMPOUND = 'urn:ietf:params:acme:error:compound'


def _cred(patterns):
    return AcmeEabCredential(kid='k', hmac_key_b64='x', allowed_domains=patterns)


def _dns(value):
    return {'type': 'dns', 'value': value}


def _ip(value):
    return {'type': 'ip', 'value': value}


# --- Matcher -----------------------------------------------------------------

@pytest.mark.parametrize('patterns, identifier, allowed', [
    (['*'], _dns('anything.example.org'), True),
    (None, _dns('anything.example.org'), True),
    (None, _ip('10.0.0.1'), True),
    ([], _dns('anything.example.org'), False),
    ([], _ip('10.0.0.1'), False),
    (['host.example.com'], _dns('host.example.com'), True),
    (['host.example.com'], _dns('HOST.example.com.'), True),
    (['Host.Example.COM.'], _dns('host.example.com'), True),
    (['host.example.com'], _dns('other.example.com'), False),
    (['*.example.com'], _dns('a.example.com'), True),
    (['*.example.com'], _dns('a.b.example.com'), True),
    (['*.example.com'], _dns('example.com'), False),
    (['*.example.com'], _dns('badexample.com'), False),
    (['*.example.com'], _dns('*.example.com'), True),
    (['*.example.com'], _dns('*.b.example.com'), True),
    (['*.b.example.com'], _dns('*.example.com'), False),
    (['host.example.com'], _dns('*.example.com'), False),
    (['example.com'], _dns('*.example.com'), False),
    (['*'], _ip('10.0.0.1'), True),
    (['10.0.0.1'], _ip('10.0.0.1'), True),
    (['10.0.0.1'], _ip('10.0.0.2'), False),
    (['*.example.com'], _ip('10.0.0.1'), False),
    (['*.0.0.1'], _ip('10.0.0.1'), False),
    (['xn--bcher-kva.example'], _dns('xn--bcher-kva.example'), True),
])
def test_allows_identifier(patterns, identifier, allowed):
    assert _cred(patterns).allows_identifier(identifier) is allowed


@pytest.mark.parametrize('raw', ['not json', '{"a": 1}', '"example.com"', '42', 'null'])
def test_corrupt_storage_reads_as_blocked(raw):
    cred = _cred(None)
    cred._allowed_domains = raw
    assert cred.allowed_domains == []
    assert cred.allows_identifier(_dns('example.com')) is False


def test_a_stored_star_dot_does_not_widen_to_everything():
    cred = _cred(None)
    cred._allowed_domains = json.dumps(['*.', 'host.example.com'])
    assert cred.allows_identifier(_dns('other.example.org')) is False
    assert cred.allows_identifier(_dns('host.example.com')) is True


def test_to_dict_exposes_parsed_normalized_list_or_null():
    cred = _cred(None)
    cred._allowed_domains = json.dumps([' Host.Example.com. ', '*'])
    assert cred.to_dict()['allowed_domains'] == ['host.example.com', '*']
    assert _cred(None).to_dict()['allowed_domains'] is None


# --- Bound credential lookup ---------------------------------------------------

@pytest.fixture
def make_cred(app):
    created = []

    def _make(patterns=None, account_id=None, used_at=None, raw=None):
        with app.app_context():
            cred = AcmeEabCredential(
                kid=f'eab-{uuid.uuid4().hex}', hmac_key_b64='c2VjcmV0',
                status='used' if account_id else 'active',
                used_by_account_id=account_id,
                used_at=used_at or (utc_now() if account_id else None),
            )
            cred.allowed_domains = patterns
            if raw is not None:
                cred._allowed_domains = raw
            db.session.add(cred)
            db.session.commit()
            created.append(cred.id)
            return cred.id, cred.kid

    yield _make
    with app.app_context():
        AcmeEabCredential.query.filter(AcmeEabCredential.id.in_(created)).delete(
            synchronize_session=False)
        db.session.commit()


def test_bound_credential_is_the_latest_used(app, make_cred, acme_account):
    from datetime import timedelta
    acct = acme_account['account_id']
    old_id, _ = make_cred(['old.example.com'], acct, utc_now() - timedelta(days=2))
    new_id, _ = make_cred(['new.example.com'], acct, utc_now())
    with app.app_context():
        svc = AcmeService(base_url='http://localhost')
        assert svc.get_bound_eab_credential(acct).id == new_id
        assert svc.get_bound_eab_credential('') is None
        assert svc.get_bound_eab_credential(None) is None
        assert svc.get_bound_eab_credential('no-such-account') is None


def test_allows_identifier_writes_nothing(app, make_cred, acme_account):
    cred_id, _ = make_cred(['host.example.com'], acme_account['account_id'])
    with app.app_context():
        cred = db.session.get(AcmeEabCredential, cred_id)
        cred.allows_identifier(_dns('other.example.com'))
        assert not db.session.dirty and not db.session.new


# --- REST API --------------------------------------------------------------------

def _create(auth_client, **body):
    body.setdefault('label', f'test-{uuid.uuid4().hex[:8]}')
    return auth_client.post(API, data=json.dumps(body), content_type='application/json')


def _patch(auth_client, cred_id, body):
    return auth_client.patch(f'{API}/{cred_id}', data=json.dumps(body),
                             content_type='application/json')


def _stored(app, cred_id):
    with app.app_context():
        cred = db.session.get(AcmeEabCredential, cred_id)
        return cred._allowed_domains, cred.notes


@pytest.fixture
def created_ids(app):
    ids = []
    yield ids
    with app.app_context():
        AcmeEabCredential.query.filter(AcmeEabCredential.id.in_(ids)).delete(
            synchronize_session=False)
        db.session.commit()


def _created(auth_client, created_ids, **body):
    r = _create(auth_client, **body)
    assert r.status_code == 201, r.data
    data = r.get_json()['data']
    created_ids.append(data['id'])
    return data


class TestCreate:
    def test_absent_means_unrestricted(self, auth_client, created_ids):
        assert _created(auth_client, created_ids)['allowed_domains'] == ['*']

    def test_null_means_unrestricted(self, auth_client, created_ids):
        assert _created(auth_client, created_ids, allowed_domains=None)['allowed_domains'] == ['*']

    def test_patterns_are_normalized(self, app, auth_client, created_ids):
        data = _created(auth_client, created_ids,
                        allowed_domains=['*.Corp.Example.NET.', 'api.corp.example.net'])
        assert data['allowed_domains'] == ['*.corp.example.net', 'api.corp.example.net']
        r = auth_client.get(f"{API}/{data['id']}")
        assert r.get_json()['data']['allowed_domains'] == ['*.corp.example.net', 'api.corp.example.net']

    def test_duplicates_collapse_in_first_seen_order(self, app, auth_client, created_ids):
        data = _created(auth_client, created_ids,
                        allowed_domains=['b.example.com', 'Example.com', 'example.com.', 'B.example.com'])
        assert data['allowed_domains'] == ['b.example.com', 'example.com']
        assert json.loads(_stored(app, data['id'])[0]) == ['b.example.com', 'example.com']

    def test_empty_list_blocks_everything(self, auth_client, created_ids):
        assert _created(auth_client, created_ids, allowed_domains=[])['allowed_domains'] == []

    def test_only_blank_entries_store_an_empty_list(self, auth_client, created_ids):
        data = _created(auth_client, created_ids, allowed_domains=['', '   ', '.'])
        assert data['allowed_domains'] == []

    @pytest.mark.parametrize('patterns', [
        ['*'], ['localhost'], ['a'], ['_dmarc.example.com'], ['host-1.example.com'],
        ['10.0.0.1'], ['2001:db8::1'], ['10.0.0.256'], ['example.123'],
        [f'h{i}.example.com' for i in range(100)],
    ])
    def test_valid_patterns_are_accepted(self, auth_client, created_ids, patterns):
        _created(auth_client, created_ids, allowed_domains=patterns)

    @pytest.mark.parametrize('patterns', [
        '*.example.com', {'a': 1}, 42,
        [1], ['ok.example.com', None],
        [f'h{i}.example.com' for i in range(101)],
        ['*.'], ['*..'], ['example.com..'], ['..'],
        ['*.10.0.0.1'], ['*.2001:db8::1'],
        ['-example.com'], ['example.com-'], ['example..com'], ['bad name?'],
        ['example.com_'], ['a.*.example.com'], ['*.*.example.com'],
        ['a' * 64 + '.example.com'],
        ['.'.join(['a' * 63] * 4) + '.ab'],
    ])
    def test_invalid_input_is_refused_and_nothing_created(self, app, auth_client, patterns):
        with app.app_context():
            before = AcmeEabCredential.query.count()
        r = _create(auth_client, allowed_domains=patterns)
        assert r.status_code == 400, r.data
        with app.app_context():
            assert AcmeEabCredential.query.count() == before


class TestPatch:
    @pytest.fixture
    def cred(self, auth_client, created_ids):
        return _created(auth_client, created_ids, allowed_domains=['host.example.com'],
                        )['id']

    def test_empty_list_blocks_and_is_returned(self, app, auth_client, cred):
        r = _patch(auth_client, cred, {'allowed_domains': []})
        assert r.status_code == 200, r.data
        assert r.get_json()['data']['allowed_domains'] == []
        with app.app_context():
            assert not db.session.get(AcmeEabCredential, cred).allows_identifier(_dns('host.example.com'))

    def test_null_is_refused_and_nothing_changes(self, app, auth_client, cred):
        r = _patch(auth_client, cred, {'allowed_domains': None, 'notes': 'should not stick'})
        assert r.status_code == 400, r.data
        assert _stored(app, cred) == ('["host.example.com"]', None)

    def test_absent_key_leaves_the_column(self, app, auth_client, cred):
        r = _patch(auth_client, cred, {'notes': 'hello'})
        assert r.status_code == 200, r.data
        assert _stored(app, cred) == ('["host.example.com"]', 'hello')

    def test_star_is_accepted(self, auth_client, cred):
        r = _patch(auth_client, cred, {'allowed_domains': ['*']})
        assert r.status_code == 200 and r.get_json()['data']['allowed_domains'] == ['*']

    def test_localhost_is_accepted(self, auth_client, cred):
        r = _patch(auth_client, cred, {'allowed_domains': ['localhost']})
        assert r.status_code == 200 and r.get_json()['data']['allowed_domains'] == ['localhost']

    @pytest.mark.parametrize('patterns', [
        ['*.'], ['*..'], ['example.com..'], ['bad name?'], ['-example.com'],
        ['example.com-'], ['example..com'], ['*.10.0.0.1'], 'example.com', [3],
        [f'h{i}.example.com' for i in range(101)],
    ])
    def test_invalid_input_is_refused_and_nothing_changes(self, app, auth_client, cred, patterns):
        r = _patch(auth_client, cred, {'allowed_domains': patterns, 'notes': 'should not stick'})
        assert r.status_code == 400, r.data
        assert _stored(app, cred) == ('["host.example.com"]', None)

    def test_legacy_null_credential_reads_as_null(self, auth_client, make_cred):
        cred_id, _ = make_cred(None)
        assert auth_client.get(f'{API}/{cred_id}').get_json()['data']['allowed_domains'] is None
        listed = {c['id']: c for c in auth_client.get(API).get_json()['data']}
        assert listed[cred_id]['allowed_domains'] is None


# --- ACME server -------------------------------------------------------------------

def _order(client, account, values):
    path = '/acme/new-order'
    payload = {'identifiers': [_dns(v) if not v[0].isdigit() else _ip(v) for v in values]}
    jws = _build_jws(f'http://localhost{path}', payload, account['key'],
                     kid=f'http://localhost/acme/acct/{account["account_id"]}',
                     nonce=_nonce(client))
    return client.post(path, data=json.dumps(jws), content_type='application/jose+json')


def _authz(client, account, value):
    path = '/acme/new-authz'
    jws = _build_jws(f'http://localhost{path}', {'identifier': _dns(value)}, account['key'],
                     kid=f'http://localhost/acme/acct/{account["account_id"]}',
                     nonce=_nonce(client))
    return client.post(path, data=json.dumps(jws), content_type='application/jose+json')


def _eab_audits(app, account_id):
    with app.app_context():
        return [(a.details, a.success, a.resource_type) for a in AuditLog.query.filter_by(
            action='acme.order.rejected_eab_domains', resource_id=account_id).all()]


class TestServerNewOrder:
    def test_allowed_names_are_ordered(self, client, make_cred, acme_account):
        make_cred(['*.example.com'], acme_account['account_id'])
        assert _order(client, acme_account, ['a.example.com', 'b.c.example.com']).status_code == 201

    def test_unbound_account_is_unrestricted(self, client, make_cred, acme_account):
        make_cred([])  # an unrelated, unbound credential
        assert _order(client, acme_account, ['anything.example.org']).status_code == 201

    def test_null_credential_is_unrestricted(self, client, make_cred, acme_account):
        make_cred(None, acme_account['account_id'])
        assert _order(client, acme_account, ['anything.example.org']).status_code == 201

    def test_empty_list_refuses(self, app, client, make_cred, acme_account):
        _, kid = make_cred([], acme_account['account_id'])
        r = _order(client, acme_account, ['host.example.com'])
        assert r.status_code == 400, r.data
        assert r.get_json()['type'] == REJECTED
        assert _eab_audits(app, acme_account['account_id']) == [
            (f'EAB kid={kid} rejected identifiers: host.example.com', False, 'acme_account')]

    def test_corrupt_credential_refuses(self, client, make_cred, acme_account):
        make_cred(None, acme_account['account_id'], raw='{not json')
        assert _order(client, acme_account, ['host.example.com']).get_json()['type'] == REJECTED

    def test_one_refused_identifier_is_a_rejected_identifier(self, client, make_cred, acme_account):
        make_cred(['host.example.com'], acme_account['account_id'])
        r = _order(client, acme_account, ['host.example.com', 'other.example.com'])
        assert r.status_code == 400
        body = r.get_json()
        assert body['type'] == REJECTED
        assert [s['identifier']['value'] for s in body['subproblems']] == ['other.example.com']

    def test_several_refused_identifiers_are_a_compound(self, app, client, make_cred, acme_account):
        _, kid = make_cred(['host.example.com'], acme_account['account_id'])
        r = _order(client, acme_account, ['a.example.org', 'host.example.com', 'b.example.org'])
        assert r.status_code == 400
        body = r.get_json()
        assert body['type'] == COMPOUND
        assert [(s['type'], s['identifier']) for s in body['subproblems']] == [
            (REJECTED, _dns('a.example.org')), (REJECTED, _dns('b.example.org'))]
        assert _eab_audits(app, acme_account['account_id']) == [
            (f'EAB kid={kid} rejected identifiers: a.example.org, b.example.org', False, 'acme_account')]

    def test_ip_identifiers_follow_ip_patterns(self, client, make_cred, acme_account):
        make_cred(['10.0.0.1', '*.example.com'], acme_account['account_id'])
        assert _order(client, acme_account, ['10.0.0.1']).status_code == 201
        assert _order(client, acme_account, ['10.0.0.2']).get_json()['type'] == REJECTED


class TestServerNewAuthz:
    def test_refused_name(self, app, client, make_cred, acme_account):
        make_cred(['host.example.com'], acme_account['account_id'])
        r = _authz(client, acme_account, 'other.example.com')
        assert r.status_code == 400, r.data
        body = r.get_json()
        assert body['type'] == REJECTED and 'subproblems' not in body
        assert _eab_audits(app, acme_account['account_id']) == []

    def test_allowed_name(self, client, make_cred, acme_account):
        make_cred(['host.example.com'], acme_account['account_id'])
        assert _authz(client, acme_account, 'HOST.example.com').status_code == 201


@pytest.fixture
def no_wildcard_domain(app):
    zone = f'eabwc{uuid.uuid4().hex[:8]}.example.com'
    with app.app_context():
        provider = DnsProvider(name=f'eab-{zone}', provider_type='manual', credentials='{}')
        db.session.add(provider)
        db.session.flush()
        entry = AcmeDomain(domain=zone, dns_provider_id=provider.id, is_wildcard_allowed=False)
        db.session.add(entry)
        db.session.commit()
        ids = (entry.id, provider.id)
    yield zone
    with app.app_context():
        db.session.delete(db.session.get(AcmeDomain, ids[0]))
        db.session.delete(db.session.get(DnsProvider, ids[1]))
        db.session.commit()


class TestWildcardRuleComesFirst:
    @pytest.mark.parametrize('patterns', [['*'], []])
    def test_server(self, app, client, make_cred, acme_account, no_wildcard_domain, patterns):
        make_cred(patterns, acme_account['account_id'])
        r = _order(client, acme_account, [f'*.{no_wildcard_domain}'])
        assert r.status_code == 400
        body = r.get_json()
        assert body['type'] == REJECTED
        assert 'Wildcard' in body['detail']
        assert _eab_audits(app, acme_account['account_id']) == []

    def test_proxy(self, app, client, monkeypatch, make_cred, acme_account, no_wildcard_domain):
        make_cred(['*'], acme_account['account_id'])
        r, service = _proxy_order(client, monkeypatch, acme_account['account_id'],
                                  [f'*.{no_wildcard_domain}'])
        assert r.status_code == 400
        assert r.get_json()['type'] == REJECTED
        service.new_order.assert_not_called()


# --- ACME proxy ----------------------------------------------------------------------

def _proxy_order(client, monkeypatch, account_id, values):
    from api.acme import acme_proxy_api

    payload = {'identifiers': [_dns(v) for v in values]}
    service = MagicMock()
    service.new_order.return_value = ({'status': 'pending'}, 'order-id')
    monkeypatch.setattr(acme_proxy_api, 'verify_proxy_jws', lambda: (True, payload, None, None))
    monkeypatch.setattr(acme_proxy_api, 'get_proxy_service', lambda slug=None: service)
    monkeypatch.setattr(acme_proxy_api, '_kid_account_thumbprint', lambda _p: None)
    monkeypatch.setattr(acme_proxy_api, '_request_protected_header',
                        lambda: {'kid': f'https://ucm.example/acme/proxy/acct/{account_id}'})
    r = client.post('/acme/proxy/new-order',
                    data=json.dumps({'protected': 's', 'payload': 's', 'signature': 's'}),
                    content_type='application/jose+json')
    return r, service


class TestProxyNewOrder:
    def test_refused_values_are_listed_in_one_rejected_identifier(
            self, app, client, monkeypatch, make_cred, acme_account):
        make_cred(['host.example.com'], acme_account['account_id'])
        r, service = _proxy_order(client, monkeypatch, acme_account['account_id'],
                                  ['a.example.org', 'host.example.com', 'b.example.org'])
        assert r.status_code == 400, r.data
        body = r.get_json()
        assert body['type'] == REJECTED
        assert 'a.example.org, b.example.org' in body['detail']
        assert 'host.example.com' not in body['detail']
        assert 'subproblems' not in body
        service.new_order.assert_not_called()
        assert _eab_audits(app, acme_account['account_id']) == []

    def test_allowed_values_reach_the_upstream(self, client, monkeypatch, make_cred, acme_account):
        make_cred(['*.example.com'], acme_account['account_id'])
        r, service = _proxy_order(client, monkeypatch, acme_account['account_id'], ['a.example.com'])
        assert r.status_code == 201, r.data
        service.new_order.assert_called_once()

    def test_unbound_account_reaches_the_upstream(self, client, monkeypatch, acme_account):
        r, service = _proxy_order(client, monkeypatch, acme_account['account_id'], ['a.example.org'])
        assert r.status_code == 201, r.data


# --- Migration 069 -----------------------------------------------------------------------

def _migration():
    return importlib.import_module('migrations.069_eab_allowed_domains')


_LEGACY_TABLE = ("CREATE TABLE acme_eab_credentials (id {pk}, kid VARCHAR(255) NOT NULL,"
                 " hmac_key_b64 TEXT NOT NULL, status VARCHAR(20) NOT NULL DEFAULT 'active')")


def test_migration_069_sqlite_backfills_existing_rows():
    conn = sqlite3.connect(':memory:')
    conn.execute(_LEGACY_TABLE.format(pk='INTEGER PRIMARY KEY'))
    conn.execute("INSERT INTO acme_eab_credentials (kid, hmac_key_b64) VALUES ('a', 'x'), ('b', 'y')")
    _migration().upgrade(conn)
    assert conn.execute("SELECT allowed_domains FROM acme_eab_credentials").fetchall() == [
        ('["*"]',), ('["*"]',)]
    # A later NULL (migration 101 import) survives a re-run.
    conn.execute("INSERT INTO acme_eab_credentials (kid, hmac_key_b64) VALUES ('c', 'z')")
    _migration().upgrade(conn)
    assert conn.execute("SELECT allowed_domains FROM acme_eab_credentials WHERE kid = 'c'").fetchone() == (None,)


def test_migration_069_sqlalchemy_path_backfills_existing_rows():
    # Same code path as PostgreSQL, through a SQLAlchemy connection.
    engine = create_engine('sqlite:///:memory:')
    with engine.begin() as conn:
        conn.execute(text(_LEGACY_TABLE.format(pk='INTEGER PRIMARY KEY')))
        conn.execute(text("INSERT INTO acme_eab_credentials (kid, hmac_key_b64) VALUES ('a', 'x')"))
        _migration().upgrade(conn)
        conn.execute(text("INSERT INTO acme_eab_credentials (kid, hmac_key_b64) VALUES ('c', 'z')"))
        _migration().upgrade(conn)
        rows = conn.execute(text("SELECT kid, allowed_domains FROM acme_eab_credentials ORDER BY id")).fetchall()
    assert [tuple(r) for r in rows] == [('a', '["*"]'), ('c', None)]


def test_migration_069_sqlite_without_table_is_a_noop():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_migration_069_postgres_backfills_existing_rows():
    schema = f"migtest_069_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        conn.execute(text(_LEGACY_TABLE.format(pk='SERIAL PRIMARY KEY')))
        conn.execute(text("INSERT INTO acme_eab_credentials (kid, hmac_key_b64) VALUES ('a', 'x'), ('b', 'y')"))
        _migration().upgrade(conn)
        rows = conn.execute(text("SELECT allowed_domains FROM acme_eab_credentials ORDER BY id")).fetchall()
        assert [r[0] for r in rows] == ['["*"]', '["*"]']
        conn.execute(text("INSERT INTO acme_eab_credentials (kid, hmac_key_b64) VALUES ('c', 'z')"))
        _migration().upgrade(conn)
        row = conn.execute(text("SELECT allowed_domains FROM acme_eab_credentials WHERE kid = 'c'")).fetchone()
        assert row[0] is None
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()
