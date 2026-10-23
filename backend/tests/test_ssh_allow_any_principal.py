"""An SSH CA signs for any principal only when told to.

An empty allowed-principals list used to sign for anything, root included.
"""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, text

from tests.test_ssh import _generate_test_ssh_key, post_json

PG_URL = os.getenv('UCM_TEST_PG_URL')


def _ca(auth_client, **extra):
    r = post_json(auth_client, '/api/v2/ssh/cas', {'descr': 'Principal policy CA', 'ca_type': 'user',
                                                  'key_type': 'ed25519', **extra})
    assert r.status_code == 201, r.data
    return r.get_json()['data']


def _sign(auth_client, ca_id, principals):
    return post_json(auth_client, '/api/v2/ssh/certificates', {
        'ca_id': ca_id, 'public_key': _generate_test_ssh_key(),
        'cert_type': 'user', 'principals': principals})


def test_an_empty_list_signs_nothing_by_default(auth_client):
    ca = _ca(auth_client)
    assert ca['allow_any_principal'] is False
    r = _sign(auth_client, ca['id'], ['root'])
    assert r.status_code == 400
    assert 'allowed principals' in r.get_json()['message']


def test_the_explicit_setting_signs_any_principal(auth_client):
    ca = _ca(auth_client, allow_any_principal=True)
    assert _sign(auth_client, ca['id'], ['root']).status_code == 201


def test_a_list_holds_whatever_the_setting(auth_client):
    ca = _ca(auth_client, allowed_principals=['deploy'], allow_any_principal=True)
    assert _sign(auth_client, ca['id'], ['deploy']).status_code == 201
    assert _sign(auth_client, ca['id'], ['root']).status_code == 400


def test_the_setting_can_be_changed_and_must_be_a_boolean(auth_client):
    ca = _ca(auth_client)
    r = auth_client.put(f"/api/v2/ssh/cas/{ca['id']}", json={'allow_any_principal': 'yes'})
    assert r.status_code == 400
    r = auth_client.put(f"/api/v2/ssh/cas/{ca['id']}", json={'allow_any_principal': True})
    assert r.status_code == 200 and r.get_json()['data']['allow_any_principal'] is True
    assert _sign(auth_client, ca['id'], ['root']).status_code == 201


def _migration():
    return importlib.import_module('migrations.110_ssh_ca_allow_any_principal')


# Every form get_allowed_principals reads as empty keeps signing after the upgrade
_ROWS = [('none', None, 1), ('blank', '', 1), ('empty', '[]', 1), ('spaced', '[ ]', 1),
         ('null', 'null', 1), ('false', 'false', 1), ('text', 'deploy', 1), ('listed', '["deploy"]', 0)]


def test_sqlite_keeps_existing_cas_as_they_were_and_runs_twice():
    connection = sqlite3.connect(':memory:')
    connection.execute("CREATE TABLE ssh_cas (id INTEGER PRIMARY KEY, descr TEXT, allowed_principals TEXT)")
    connection.executemany("INSERT INTO ssh_cas (descr, allowed_principals) VALUES (?, ?)",
                           [(d, p) for d, p, _ in _ROWS])
    _migration().upgrade(connection)
    # An operator's later choice survives a second run
    connection.execute("UPDATE ssh_cas SET allow_any_principal = 0 WHERE descr = 'none'")
    _migration().upgrade(connection)
    got = dict(connection.execute("SELECT descr, allow_any_principal FROM ssh_cas"))
    assert got == {d: (0 if d == 'none' else want) for d, _, want in _ROWS}


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgresql_keeps_existing_cas_as_they_were_and_runs_twice():
    from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own
    with _a_schema_of_our_own('migration_110') as url:
        engine = create_engine(url)
        try:
            with engine.begin() as connection:
                connection.execute(text("CREATE TABLE ssh_cas (id SERIAL PRIMARY KEY, descr VARCHAR(80), "
                                        "allowed_principals TEXT)"))
                for descr, principals, _ in _ROWS:
                    connection.execute(text("INSERT INTO ssh_cas (descr, allowed_principals) VALUES (:d, :p)"),
                                       {'d': descr, 'p': principals})
                _migration().upgrade(connection)
                connection.execute(text("UPDATE ssh_cas SET allow_any_principal = FALSE WHERE descr = 'none'"))
                _migration().upgrade(connection)
                got = dict(connection.execute(text("SELECT descr, allow_any_principal FROM ssh_cas")).all())
                assert got == {d: (False if d == 'none' else bool(want)) for d, _, want in _ROWS}
        finally:
            engine.dispose()


@pytest.mark.parametrize('principals', ['deploy', True, 7, ['deploy', ''], [3]])
def test_a_principal_list_that_is_not_one_is_refused(auth_client, principals):
    r = post_json(auth_client, '/api/v2/ssh/cas', {'descr': 'Bad list CA', 'ca_type': 'user',
                                                  'key_type': 'ed25519', 'allowed_principals': principals})
    assert r.status_code == 400, r.data


def test_the_migration_reads_a_list_as_the_model_does():
    from models.ssh import SSHCertificateAuthority
    for _, stored, want in _ROWS:
        ca = SSHCertificateAuthority(allowed_principals=stored)
        assert (not ca.get_allowed_principals()) is bool(want)
        assert _migration()._lists_nothing(stored) is bool(want)
