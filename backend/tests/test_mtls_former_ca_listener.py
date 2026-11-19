"""The 8443 listener trusts, beside its mTLS anchor, the former CAs a Windows enrollment profile
lists for renewal, and no other: a delisted or revoked former CA fails the handshake again at the
next start, and the application is told which former CAs the running listener trusts. Driven
through gunicorn_config in a child process, as test_mtls_trust_anchor does."""
import base64
import json
import os
import sqlite3
import subprocess
import sys

import pytest
from cryptography.x509.oid import ExtendedKeyUsageOID

from tests.test_mtls_trust_anchor import BACKEND, CHILD, _issue, _key_pem, _pem

pytest.importorskip('gunicorn')


@pytest.fixture(scope='module')
def bench(tmp_path_factory):
    """Anchor N (the profile's CA now), former CA F, CA X never listed; one client leaf under each."""
    root = tmp_path_factory.mktemp('mtls_former')
    cas = {name: _issue(f'Bench {name}', ca=True) for name in ('N', 'F', 'X')}
    server = _issue('server.test', eku=ExtendedKeyUsageOID.SERVER_AUTH)
    (root / 'server.pem').write_text(_pem(server[0]))
    (root / 'server.key').write_text(_key_pem(server[1]))
    clients = {}
    for name, ca in cas.items():
        leaf, key = _issue(f'host-{name}', issuer=ca, eku=ExtendedKeyUsageOID.CLIENT_AUTH)
        (root / f'{name}.pem').write_text(_pem(leaf))
        (root / f'{name}.key').write_text(_key_pem(key))
        clients[name] = (str(root / f'{name}.pem'), str(root / f'{name}.key'))
    return {'cas': {k: v[0] for k, v in cas.items()}, 'clients': clients,
            'server': (str(root / 'server.pem'), str(root / 'server.key'))}


def _install(data_dir, bench, listed, revoked=()):
    data_dir.mkdir()
    db = sqlite3.connect(str(data_dir / 'ucm.db'))
    db.execute("CREATE TABLE system_config (key VARCHAR(255) PRIMARY KEY, value TEXT)")
    db.execute("CREATE TABLE certificate_authorities (refid VARCHAR(64) PRIMARY KEY, crt TEXT, descr TEXT, "
               "caref VARCHAR(64), revoked BOOLEAN)")
    db.execute("CREATE TABLE windows_enrollment_profiles (id INTEGER PRIMARY KEY, renewal_ca_refids TEXT)")
    for key, value in (('mtls_enabled', 'true'), ('mtls_required', 'false'), ('mtls_trusted_ca_id', 'ca-N')):
        db.execute("INSERT INTO system_config VALUES (?, ?)", (key, value))
    for name, cert in bench['cas'].items():
        db.execute("INSERT INTO certificate_authorities VALUES (?, ?, ?, NULL, ?)",
                   (f'ca-{name}', base64.b64encode(_pem(cert).encode()).decode(), f'Bench {name}',
                    name in revoked))
    db.execute("INSERT INTO windows_enrollment_profiles VALUES (1, ?)", (json.dumps(listed),))
    db.execute("INSERT INTO windows_enrollment_profiles VALUES (2, NULL)")
    db.commit()
    db.close()


def _start(tmp_path, bench, listed, revoked=()):
    data_dir = tmp_path / 'data'
    _install(data_dir, bench, listed, revoked)
    env = {k: v for k, v in os.environ.items() if k not in ('DATABASE_URL', 'DATABASE_PATH')}
    env.update(DATA_DIR=str(data_dir), UCM_BASE_PATH=str(tmp_path), PYTHONPATH=BACKEND)
    payload = json.dumps({'clients': bench['clients'], 'server': bench['server'], 'pre_313_defaults': False})
    run = subprocess.run([sys.executable, '-c', CHILD, payload], cwd=BACKEND, env=env,
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    outcomes = {name: result.split(':')[0]
                for name, result in json.loads(run.stdout.strip().splitlines()[-1]).items()}
    return outcomes, json.loads((data_dir / 'mtls_former_cas.json').read_text())


def test_a_listed_former_ca_is_trusted_beside_the_anchor_and_named_to_the_application(tmp_path, bench):
    assert _start(tmp_path, bench, ['ca-F']) == (
        {'N': 'accepted', 'F': 'accepted', 'X': 'refused'}, ['ca-F'])


def test_a_former_ca_off_the_list_is_refused_again(tmp_path, bench):
    assert _start(tmp_path, bench, []) == ({'N': 'accepted', 'F': 'refused', 'X': 'refused'}, [])


def test_a_revoked_former_ca_is_not_trusted_even_listed(tmp_path, bench):
    assert _start(tmp_path, bench, ['ca-F'], revoked=('F',)) == (
        {'N': 'accepted', 'F': 'refused', 'X': 'refused'}, [])


def test_a_listed_ca_unknown_here_is_ignored(tmp_path, bench):
    assert _start(tmp_path, bench, ['ca-gone']) == ({'N': 'accepted', 'F': 'refused', 'X': 'refused'}, [])
