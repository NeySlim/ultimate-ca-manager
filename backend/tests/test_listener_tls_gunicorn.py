"""A real node in container mode outside HA (gunicorn with the product's configuration, SQLite): a
regenerated, an applied, then a renewed HTTPS certificate is served after the product's SIGHUP to
its master, whose pid stays, while the scheduler process keeps running (#452). openssl s_client
reads what the listener presents. An external SIGHUP restarts the scheduler process, silently.
"""
import os
import re
import shutil
import signal
import ssl
import subprocess
import time
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes

from tests.ha.cluster import Client, Node, create_ca, issue, wait_until
from tests.test_listener_tls import _colons, _pair

pytest.importorskip('gunicorn')
pytestmark = pytest.mark.slow

READY_TIMEOUT = 240
PEM = re.compile(r'-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----', re.S)


def _served(port):
    """SHA-256 hex of the leaf the listener presents, or None while it does not answer."""
    if shutil.which('openssl'):
        run = subprocess.run(['openssl', 's_client', '-connect', f'127.0.0.1:{port}',
                              '-servername', 'localhost'],
                             input='', capture_output=True, text=True, timeout=30)
        found = PEM.search(run.stdout)
        pem = found.group(0) if found else None
    else:
        try:
            pem = ssl.get_server_certificate(('127.0.0.1', port), timeout=10)
        except OSError:
            pem = None
    if not pem:
        return None
    return x509.load_pem_x509_certificate(pem.encode()).fingerprint(hashes.SHA256()).hex()


def _on_disk(path):
    return x509.load_pem_x509_certificate(Path(path).read_bytes()).fingerprint(hashes.SHA256()).hex()


def _children(master):
    """{pid: command line} of the master's live children."""
    found = {}
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / 'stat').read_text().rsplit(')', 1)[1].split()
            cmdline = (entry / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
        except OSError:
            continue
        if int(fields[1]) == master and fields[0] != 'Z':
            found[int(entry.name)] = cmdline
    return found


def _worker_and_scheduler(master):
    children = _children(master)
    schedulers = [pid for pid, cmd in children.items() if 'scheduler_main' in cmd]
    workers = [pid for pid, cmd in children.items() if 'scheduler_main' not in cmd]
    return workers, schedulers


@pytest.fixture
def node(tmp_path):
    from cryptography.fernet import Fernet
    import secrets
    root = tmp_path / 'node'
    data = root / 'data'
    data.mkdir(parents=True)
    cert_pem, key_pem, _fingerprint = _pair('before-reload.test')
    (data / 'https_cert.pem').write_text(cert_pem)
    (data / 'https_key.pem').write_text(key_pem)
    password = f'Reload-{secrets.token_hex(8)}-9z'
    shared = {
        'SECRET_KEY': secrets.token_hex(32),
        'KEY_ENCRYPTION_KEY': Fernet.generate_key().decode(),
        'UCM_DB_ENCRYPTION_KEY': Fernet.generate_key().decode(),
        'INITIAL_ADMIN_PASSWORD': password,
        'FQDN': 'ucm-reload.test',
        'UCM_FQDN': 'ucm-reload.test',
        'UCM_DOCKER': '1',
        'DATABASE_PATH': str(data / 'ucm.db'),
    }
    bench = Node('node-reload', root, shared)
    bench.password = password
    bench.start()
    try:
        wait_until(bench.ready, READY_TIMEOUT, 'node ready')
    except BaseException:
        print(bench.log_text()[-30000:])
        bench.stop()
        raise
    try:
        yield bench
        assert not bench.guard_hits(), bench.guard_hits()
    finally:
        bench.stop()


def test_a_regenerated_certificate_is_served_after_the_products_sighup(node):
    try:
        _regenerate_and_serve(node)
    except BaseException:
        print(node.log_text()[-30000:])
        raise


def _regenerate_and_serve(node):
    cert_path = node.data_dir / 'https_cert.pem'
    master = node.proc.pid
    before = _on_disk(cert_path)
    assert _served(node.port) == before

    admin = Client.login(node, node.password)
    info = admin.get('/api/v2/system/https/cert-info').json()['data']
    assert info['served'] == {'fingerprint': _colons(before), 'matches': True}

    workers, schedulers = _worker_and_scheduler(master)
    assert len(workers) == 1 and len(schedulers) == 1, _children(master)

    console_from = len(node.console.read_text(errors='replace'))
    r = admin.post('/api/v2/system/https/regenerate', {'common_name': 'after-reload.test'})
    assert r.status_code == 200, r.text
    assert r.json()['data'] == {'listener_reload': 'reloading'}, r.text
    after = _on_disk(cert_path)
    assert after != before

    wait_until(lambda: _served(node.port) == after, 90, 'the regenerated certificate served')
    assert node.alive() and node.proc.pid == master
    wait_until(lambda: len(_worker_and_scheduler(master)[0]) == 1, 60, 'the old worker gone')
    new_workers, new_schedulers = _worker_and_scheduler(master)
    assert new_workers != workers  # a new worker, forked by the same master
    assert new_schedulers == schedulers  # a TLS reload leaves the scheduled tasks running

    again = Client.login(node, node.password)
    info = again.get('/api/v2/system/https/cert-info').json()['data']
    assert info['served'] == {'fingerprint': _colons(after), 'matches': True}

    # A managed certificate applied, then renewed in place (the binding follows it): each served
    ca = create_ca(again, 'Reload bench CA')
    cert = issue(again, ca['id'], 'ucm-reload.test')
    r = again.post('/api/v2/system/https/apply', {'cert_id': cert['id']})
    assert r.status_code == 200, r.text
    assert r.json()['data'] == {'listener_reload': 'reloading'}, r.text
    applied = _on_disk(cert_path)
    wait_until(lambda: _served(node.port) == applied, 90, 'the applied certificate served')

    renewer = Client.login(node, node.password)
    r = renewer.post(f"/api/v2/certificates/{cert['id']}/renew", {})
    assert r.status_code == 200, r.text
    renewed = _on_disk(cert_path)
    assert renewed != applied
    wait_until(lambda: _served(node.port) == renewed, 90, 'the renewed certificate served')

    assert node.alive() and node.proc.pid == master
    wait_until(lambda: len(_worker_and_scheduler(master)[0]) == 1, 60, 'the old workers gone')
    assert _worker_and_scheduler(master)[1] == schedulers
    console = node.console.read_text(errors='replace')[console_from:]
    assert console.count('Hang up') == 3
    # The configuration re-read at each SIGHUP finds the bound pair the worker wrote
    assert 'already in place' in console
    assert 'Failed to read config file' not in console and 'Traceback' not in console


def test_an_external_sighup_restarts_the_scheduler_without_a_traceback(node):
    try:
        _external_sighup(node)
    except BaseException:
        print(node.log_text()[-30000:])
        raise


def _external_sighup(node):
    master = node.proc.pid
    workers, schedulers = _worker_and_scheduler(master)
    assert len(workers) == 1 and len(schedulers) == 1, _children(master)
    console_from = len(node.console.read_text(errors='replace'))
    os.kill(master, signal.SIGHUP)  # systemctl reload, docker kill --signal=HUP: no reload asked by UCM

    def renewed():
        new_workers, new_schedulers = _worker_and_scheduler(master)
        return (len(new_workers) == 1 and new_workers != workers
                and len(new_schedulers) == 1 and new_schedulers != schedulers)
    wait_until(renewed, 150, 'a new worker and a new scheduler process')
    wait_until(node.ready, 60, 'the node ready after the reload')
    # What the new worker inherited from the master's reload ends within seconds of the old scheduler
    time.sleep(5)
    assert node.alive() and node.proc.pid == master
    console = node.console.read_text(errors='replace')[console_from:]
    assert 'Hang up' in console
    assert 'Traceback' not in console and 'KeyError' not in console, console
