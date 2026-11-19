"""HA on PostgreSQL: a sign-in test started on one node returns to the other.

Two applications on one schema with the SQL session store, as two nodes behind a load
balancer: the transaction and the report live in the database, never in a worker.
"""
import os
import uuid
from urllib.parse import parse_qs, urlsplit

import pytest

from tests.header_guard import guarded

from api.v2.sso import saml_sp, sign_in_tests
from models import db
from models.sso import SSOProvider
from tests.test_saml_strict_validation import ACS, IDP_ENTITY, SP_BASE, idp_signer  # noqa: F401
from tests.test_sso_sign_in_test import (
    HOST, OIDC_CALLBACK, Case, OIDCIdP, _install_idp, _oidc_userinfo, _request_id, _saml_answer,
)

PG_URL = os.getenv('UCM_TEST_APP_PG_URL') or os.getenv('UCM_TEST_PG_URL')
pytestmark = [pytest.mark.postgres,
              pytest.mark.skipif(not PG_URL, reason='no PostgreSQL URL for the two-node test')]


@pytest.fixture(autouse=True)
def _drop_session_table_from_metadata():
    """The SQL store registers flask_sessions on the shared metadata; never leak it."""
    yield
    t = db.metadata.tables.get('flask_sessions')
    if t is not None:
        db.metadata.remove(t)


@pytest.fixture
def nodes(monkeypatch):
    import psycopg

    from config.settings import TestingConfig
    from tests import pg_app_harness
    from utils.db_url import sqlalchemy_url

    schema = f'ucm_sit_{uuid.uuid4().hex[:8]}'
    admin = psycopg.connect(PG_URL, autocommit=True)
    admin.execute(f'CREATE SCHEMA "{schema}"')
    sep = '&' if '?' in PG_URL else '?'
    url = f'{PG_URL}{sep}options=-csearch_path%3D{schema}'
    monkeypatch.setenv('DATABASE_URL', url)
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', sqlalchemy_url(url))
    monkeypatch.setattr(TestingConfig, 'DATABASE_TYPE', 'postgresql')
    monkeypatch.setattr(TestingConfig, 'SESSION_TYPE', 'sqlalchemy')
    monkeypatch.setattr(TestingConfig, 'SESSION_SQLALCHEMY_TABLE', 'flask_sessions', raising=False)
    monkeypatch.setattr(saml_sp, 'get_admin_base_url', lambda: None)
    monkeypatch.setattr(saml_sp, 'get_admin_canonical_origin', lambda: None)
    pg_app_harness._creating_session_app.append(True)
    created = []
    try:
        from app import create_app
        created.append(guarded(create_app('testing')))
        created.append(guarded(create_app('testing')))
        yield created[0], created[1]
    finally:
        pg_app_harness._creating_session_app.pop()
        for application in created:
            with application.app_context():
                db.session.remove()
                db.engine.dispose()
        admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        admin.close()


def _login(node):
    from tests.conftest import clear_admin_password_flag
    clear_admin_password_flag(node)
    client = node.test_client()
    r = client.post('/api/v2/auth/login', base_url=SP_BASE,
                    json={'username': 'admin', 'password': 'changeme123'})
    assert r.status_code == 200, r.data
    return client


def _provider(node, **fields):
    with node.app_context():
        row = SSOProvider(name=f'sit-ha-{uuid.uuid4().hex[:6]}', enabled=False,
                          auto_create_users=True, default_role='viewer', **fields)
        db.session.add(row)
        db.session.commit()
        return row.id


def _carry(source, target, path):
    """The browser's cookies, presented to the other node."""
    for name, cookie_path in (('session', '/'), (sign_in_tests.BROWSER_COOKIE, path)):
        cookie = source.get_cookie(name, domain=HOST, path=cookie_path)
        assert cookie is not None, name
        target.set_cookie(name, cookie.value, domain=HOST, path=cookie_path)


def test_an_oidc_test_started_on_one_node_returns_and_reads_on_the_other(nodes, monkeypatch):
    node_a, node_b = nodes
    assert node_a.config['SESSION_TYPE'] == 'sqlalchemy'
    pid = _provider(node_a, provider_type='oauth2', oauth2_client_id='ucm-client',
                    oauth2_client_secret='secret', oauth2_auth_url='https://idp.example/authorize',
                    oauth2_token_url='https://idp.example/token',
                    oauth2_userinfo_url='https://idp.example/userinfo',
                    oauth2_issuer='https://idp.example', id_token_verify=True)
    case = Case(node_a, pid, 'oauth2')
    _install_idp(monkeypatch, OIDCIdP(case.external_id, _oidc_userinfo(case)))
    on_a = _login(node_a)
    r = on_a.post(f'/api/v2/sso/providers/{pid}/test-sign-in', base_url=SP_BASE)
    assert r.status_code == 200, r.data
    started = r.get_json()['data']
    state = parse_qs(urlsplit(started['url']).query)['state'][0]
    on_b = node_b.test_client()
    _carry(on_a, on_b, OIDC_CALLBACK)
    r = on_b.get(OIDC_CALLBACK, base_url=SP_BASE, query_string={'state': state, 'code': 'c'})
    assert r.headers['Location'] == '/sso-test-complete?result=done'
    for client in (on_a, on_b):
        r = client.get(f"/api/v2/sso/sign-in-tests/{started['id']}", base_url=SP_BASE)
        assert r.status_code == 200, r.data
        report = r.get_json()['data']['report']
        assert (report['verdict'], report['account']['outcome']) == ('accepted', 'create')


def test_a_saml_test_started_on_one_node_returns_to_the_other(nodes, idp_signer):
    node_a, node_b = nodes
    pid = _provider(node_a, provider_type='saml', saml_entity_id=IDP_ENTITY,
                    saml_sso_url='https://idp.example.test/sso', saml_certificate=idp_signer[1])
    case = Case(node_a, pid, 'saml')
    on_a = _login(node_a)
    r = on_a.post(f'/api/v2/sso/providers/{pid}/test-sign-in', base_url=SP_BASE)
    assert r.status_code == 200, r.data
    started = r.get_json()['data']
    on_b = node_b.test_client()
    _carry(on_a, on_b, ACS)
    answer = _saml_answer(case, idp_signer)(_request_id(started['url']))
    r = on_b.post(ACS, base_url=SP_BASE, data={'SAMLResponse': answer})
    assert r.headers['Location'] == '/sso-test-complete?result=done'
    r = on_a.get(f"/api/v2/sso/sign-in-tests/{started['id']}", base_url=SP_BASE)
    assert r.get_json()['data']['report']['verdict'] == 'accepted'
