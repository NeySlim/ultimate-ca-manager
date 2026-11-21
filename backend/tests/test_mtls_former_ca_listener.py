"""The 8443 listener trusts, beside its mTLS anchor, the former CAs a Windows enrollment profile
lists for renewal, and no other: a delisted or revoked former CA fails the handshake again at the
next start, and each worker arms the application's guard from the bundle its TLS context loaded,
whatever rewrites it later. Driven through gunicorn_config in a child process, as
test_mtls_trust_anchor does."""
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

# After the handshakes: another node rewrites the bundle (anchor alone); this worker keeps what it loaded
PINNED = CHILD + r'''
import os
from utils import client_cert
pinned = [sorted(client_cert.listener_former_refids()), client_cert.listener_guard_armed()]
with open(gunicorn_config.ca_certs, 'w') as handle:
    handle.write(client_cert.former_cas_header([]))
print(json.dumps({'pinned': pinned, 'after_rewrite': [sorted(client_cert.listener_former_refids()),
                                                       client_cert.listener_guard_armed()]}))
'''


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
    run = subprocess.run([sys.executable, '-c', PINNED, payload], cwd=BACKEND, env=env,
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    lines = run.stdout.strip().splitlines()
    outcomes = {name: result.split(':')[0] for name, result in json.loads(lines[-2]).items()}
    state = json.loads(lines[-1])
    assert state['after_rewrite'] == state['pinned']
    return outcomes, state['pinned'][0]


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


def test_the_worker_pins_the_former_cas_of_the_bundle_it_loaded(tmp_path, bench):
    """Armed while the bundle trusts a former CA, and still after the bundle is rewritten."""
    data_dir = tmp_path / 'data'
    _install(data_dir, bench, ['ca-F'])
    env = {k: v for k, v in os.environ.items() if k not in ('DATABASE_URL', 'DATABASE_PATH')}
    env.update(DATA_DIR=str(data_dir), UCM_BASE_PATH=str(tmp_path), PYTHONPATH=BACKEND)
    payload = json.dumps({'clients': bench['clients'], 'server': bench['server'], 'pre_313_defaults': False})
    run = subprocess.run([sys.executable, '-c', PINNED, payload], cwd=BACKEND, env=env,
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout.strip().splitlines()[-1]) == {
        'pinned': [['ca-F'], True], 'after_rewrite': [['ca-F'], True]}


def test_a_bundle_rewritten_while_loading_or_without_names_arms_the_guard(tmp_path):
    """In doubt the guard is armed: a bundle read twice differently, or trusting more than its anchor
    without naming its former CAs (unreadable header, written before the names were recorded)."""
    from utils import client_cert
    anchor = '-----BEGIN CERTIFICATE-----\nA\n-----END CERTIFICATE-----\n'
    path = tmp_path / 'bundle.pem'
    try:
        path.write_text(client_cert.former_cas_header([]) + anchor)
        client_cert.pin_listener_trust_file(str(path), lambda: None)
        assert (client_cert.listener_guard_armed(), client_cert.listener_former_refids()) == (False, frozenset())

        # Loaded while trusting F, then rewritten (anchor alone) at every attempt: never settled
        path.write_text(client_cert.former_cas_header(['ca-F']) + anchor * 2)
        loads = []

        def rewritten_during_load():
            loads.append(1)
            path.write_text(client_cert.former_cas_header([]) + anchor + f'rewrite {len(loads)}\n')
        client_cert.pin_listener_trust_file(str(path), rewritten_during_load)
        assert len(loads) == 3 and client_cert.listener_guard_armed()

        client_cert.pin_listener_trust([anchor * 2])
        assert (client_cert.listener_guard_armed(), client_cert.listener_former_refids()) == (True, frozenset())
        client_cert.pin_listener_trust(['UCM-Former-CAs: [unreadable\n' + anchor])
        assert client_cert.listener_guard_armed()
        client_cert.pin_listener_trust([None])
        assert client_cert.listener_guard_armed()
    finally:
        client_cert.pin_listener_trust(())


def test_the_fallback_keeps_the_bundle_and_the_former_cas_it_names(tmp_path, bench):
    """Settings unreadable at the next start: the last bundle is served, and its former CAs with it."""
    _install(tmp_path / 'data', bench, ['ca-F'])
    env = {k: v for k, v in os.environ.items() if k not in ('DATABASE_URL', 'DATABASE_PATH')}
    env.update(DATA_DIR=str(tmp_path / 'data'), UCM_BASE_PATH=str(tmp_path), PYTHONPATH=BACKEND)
    payload = json.dumps({'clients': bench['clients'], 'server': bench['server'], 'pre_313_defaults': False})
    first = subprocess.run([sys.executable, '-c', CHILD, payload], cwd=BACKEND, env=env,
                           capture_output=True, text=True, timeout=60)
    assert first.returncode == 0, first.stderr
    (tmp_path / 'data' / 'ucm.db').unlink()
    run = subprocess.run([sys.executable, '-c', PINNED, payload], cwd=BACKEND, env=env,
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    assert 'keeping the last known configuration' in run.stderr
    lines = run.stdout.strip().splitlines()
    assert {k: v.split(':')[0] for k, v in json.loads(lines[-2]).items()} == {
        'N': 'accepted', 'F': 'accepted', 'X': 'refused'}
    assert json.loads(lines[-1])['pinned'] == [['ca-F'], True]
