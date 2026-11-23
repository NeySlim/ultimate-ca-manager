"""A new TLS listener configuration (HTTPS pair, mTLS trust, WSTEP cap) is served by a SIGHUP to
the gunicorn master that started this process, outside HA, in a container or not (#452).

Only the verified parent is signalled, never a guessed pid; HA keeps its rolling restart; the
restarts a container still refuses (service restart, database switch, restore) stay refused.
The state of the HTTPS listener compares the certificate it serves with the one on disk.
"""
import logging
import os
import signal
import time

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from config.settings import Config
from utils import listener_tls

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


def _pair(cn):
    """(certificate PEM, key PEM, SHA-256 hex) of a fresh self-signed certificate."""
    from datetime import datetime, timedelta, timezone
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=30))
            .sign(key, hashes.SHA256()))
    key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()
    return (cert.public_bytes(serialization.Encoding.PEM).decode(), key_pem,
            cert.fingerprint(hashes.SHA256()).hex())


@pytest.fixture
def signals(monkeypatch, tmp_path):
    """Every signal the code sends, recorded and never delivered; the marker in a tmp data dir."""
    sent = []
    monkeypatch.setattr(listener_tls.os, 'kill', lambda pid, sig: sent.append((pid, sig)))
    monkeypatch.setattr('config.settings.DATA_DIR', tmp_path)
    monkeypatch.setitem(listener_tls._state, 'master', None)
    monkeypatch.delenv('UCM_SCHEDULER_MASTER_PID', raising=False)
    return sent


@pytest.fixture
def restarts(monkeypatch):
    """The watcher's restarts asked for; never a real one."""
    asked = []
    monkeypatch.setattr('config.settings.restart_ucm_service',
                        lambda: asked.append(1) or (True, 'Service restart initiated'))
    return asked


def _mode(monkeypatch, docker, ha=False):
    monkeypatch.setattr(Config, 'HA_MODE', ha)
    monkeypatch.setattr('config.settings.is_docker', lambda: docker)


@pytest.mark.parametrize('docker', [True, False], ids=['container', 'native'])
def test_outside_ha_the_master_that_started_this_worker_gets_sighup(monkeypatch, signals, restarts,
                                                                    tmp_path, docker):
    _mode(monkeypatch, docker)
    listener_tls.note_master(os.getppid())
    outcome, _message = listener_tls.serve_listener_change()
    assert outcome == listener_tls.RELOADING
    assert signals == [(os.getppid(), signal.SIGHUP)]
    assert restarts == []
    assert (tmp_path / listener_tls.RELOAD_MARKER).exists()


def test_a_pid_that_is_not_the_parent_is_never_signalled(monkeypatch, signals, restarts, caplog):
    _mode(monkeypatch, docker=True)
    listener_tls.note_master(os.getppid() + 7919)  # a worker whose master died: reparented
    with caplog.at_level(logging.ERROR, logger='utils.listener_tls'):
        outcome, message = listener_tls.serve_listener_change()
    assert outcome == listener_tls.FAILED and message
    assert signals == [] and restarts == []
    assert any(r.levelno == logging.ERROR and 'not reloaded' in r.getMessage() for r in caplog.records)


def test_without_a_gunicorn_master_a_container_reports_the_failure(monkeypatch, signals, restarts,
                                                                   caplog):
    _mode(monkeypatch, docker=True)
    with caplog.at_level(logging.ERROR, logger='utils.listener_tls'):
        outcome, _message = listener_tls.serve_listener_change()
    assert outcome == listener_tls.FAILED
    assert signals == [] and restarts == []
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_without_a_gunicorn_master_a_native_install_restarts_through_the_watcher(monkeypatch, signals,
                                                                                 restarts):
    _mode(monkeypatch, docker=False)
    outcome, _message = listener_tls.serve_listener_change()
    assert outcome == listener_tls.RESTARTING
    assert signals == [] and restarts == [1]


def test_ha_keeps_the_rolling_restart(monkeypatch, signals):
    _mode(monkeypatch, docker=True, ha=True)
    listener_tls.note_master(os.getppid())
    asked = []
    monkeypatch.setattr('services.cluster_commands.request_restart',
                        lambda: asked.append(1) or (True, 'rolling'))
    outcome, _message = listener_tls.serve_listener_change()
    assert outcome == listener_tls.ROLLING
    assert asked == [1] and signals == []


def test_the_scheduler_process_signals_the_master_its_supervisor_named(monkeypatch, signals, restarts):
    _mode(monkeypatch, docker=True)
    monkeypatch.setenv('UCM_SCHEDULER_MASTER_PID', str(os.getppid()))
    assert listener_tls.serve_listener_change()[0] == listener_tls.RELOADING
    assert signals == [(os.getppid(), signal.SIGHUP)]


def test_the_scheduler_process_never_signals_a_master_that_is_not_its_parent(monkeypatch, signals,
                                                                             restarts):
    _mode(monkeypatch, docker=True)
    monkeypatch.setenv('UCM_SCHEDULER_MASTER_PID', str(os.getppid() + 7919))
    assert listener_tls.serve_listener_change()[0] == listener_tls.FAILED
    assert signals == []


def test_a_signal_that_cannot_be_sent_fails_and_leaves_no_marker(monkeypatch, signals, restarts,
                                                                 tmp_path):
    _mode(monkeypatch, docker=True)
    listener_tls.note_master(os.getppid())

    def gone(pid, sig):
        raise ProcessLookupError(3, 'No such process')
    monkeypatch.setattr(listener_tls.os, 'kill', gone)
    outcome, message = listener_tls.serve_listener_change()
    assert outcome == listener_tls.FAILED and 'No such process' in message
    assert not (tmp_path / listener_tls.RELOAD_MARKER).exists()


def test_the_master_takes_a_fresh_reload_request_once(tmp_path):
    marker = tmp_path / listener_tls.RELOAD_MARKER
    assert listener_tls.take_reload_request(tmp_path) is False
    marker.write_text('1')
    assert listener_tls.take_reload_request(tmp_path) is True
    assert not marker.exists()
    assert listener_tls.take_reload_request(tmp_path) is False
    marker.write_text('1')
    old = time.time() - listener_tls.MARKER_FRESH_SECONDS - 5
    os.utime(marker, (old, old))
    assert listener_tls.take_reload_request(tmp_path) is False  # a leftover: a full reload
    assert not marker.exists()


def test_the_served_certificate_is_the_leaf_the_context_loaded(monkeypatch, tmp_path):
    monkeypatch.setitem(listener_tls._state, 'served', None)
    cert_pem, _key, fingerprint = _pair('served.test')
    other_pem, _key2, _other = _pair('chain.test')
    path = tmp_path / 'https_cert.pem'
    path.write_text(cert_pem + other_pem)
    built = []
    ctx = listener_tls.pin_served_certificate(str(path), lambda: built.append(1) or 'ctx')
    assert ctx == 'ctx' and built == [1]
    assert listener_tls.served_fingerprint() == fingerprint


def test_a_file_replaced_while_the_context_loads_is_not_pinned(monkeypatch, tmp_path):
    monkeypatch.setitem(listener_tls._state, 'served', 'stale')
    path = tmp_path / 'https_cert.pem'
    path.write_text(_pair('first.test')[0])

    def build():
        path.write_text(_pair('moving.test')[0])
        return 'ctx'
    assert listener_tls.pin_served_certificate(str(path), build) == 'ctx'
    assert listener_tls.served_fingerprint() is None


# --- the restarts a container still refuses -------------------------------------------------

def test_the_service_restart_route_still_refuses_in_a_container(app, auth_client, monkeypatch, signals):
    monkeypatch.setattr(Config, 'HA_MODE', False)
    monkeypatch.setattr('api.v2.system.service.is_docker', lambda: True)
    listener_tls.note_master(os.getppid())
    r = auth_client.post('/api/v2/system/service/restart', json={})
    assert r.status_code == 400
    assert signals == []


def test_restore_and_database_switch_restarts_still_refuse_in_a_container(app, monkeypatch, signals):
    import config.settings as settings
    from services.jobs import restore
    _mode(monkeypatch, docker=True)
    listener_tls.note_master(os.getppid())
    assert settings.restart_ucm_service()[0] is False
    assert restore.predicted_restart()[0] is False
    assert signals == []


# --- the HTTPS state and routes ---------------------------------------------------------------

@pytest.fixture
def https_files(monkeypatch, tmp_path):
    cert_pem, key_pem, fingerprint = _pair('recorded.test')
    (tmp_path / 'https_cert.pem').write_text(cert_pem)
    (tmp_path / 'https_key.pem').write_text(key_pem)
    monkeypatch.setenv('HTTPS_CERT_PATH', str(tmp_path / 'https_cert.pem'))
    monkeypatch.setenv('HTTPS_KEY_PATH', str(tmp_path / 'https_key.pem'))
    return fingerprint


def _colons(hexdigest):
    return ':'.join(hexdigest[i:i + 2].upper() for i in range(0, len(hexdigest), 2))


def test_the_https_state_says_the_recorded_certificate_is_served(auth_client, monkeypatch, https_files):
    monkeypatch.setitem(listener_tls._state, 'served', https_files)
    data = auth_client.get('/api/v2/system/https/cert-info').get_json()['data']
    assert data['served'] == {'fingerprint': _colons(https_files), 'matches': True}


def test_the_https_state_says_a_renewed_certificate_is_not_served_yet(auth_client, monkeypatch,
                                                                    https_files):
    previous = _pair('previous.test')[2]
    monkeypatch.setitem(listener_tls._state, 'served', previous)
    data = auth_client.get('/api/v2/system/https/cert-info').get_json()['data']
    assert data['served'] == {'fingerprint': _colons(previous), 'matches': False}
    assert data['fingerprint'] == _colons(https_files)


def test_the_https_state_without_a_listener_here_says_unknown(auth_client, monkeypatch, https_files):
    monkeypatch.setitem(listener_tls._state, 'served', None)
    data = auth_client.get('/api/v2/system/https/cert-info').get_json()['data']
    assert data['served'] == {'fingerprint': None, 'matches': None}


@pytest.fixture
def unbound(app):
    from services.https_binding import set_bound_refid
    with app.app_context():
        set_bound_refid('')
    yield
    with app.app_context():
        set_bound_refid('')


def test_regenerate_in_a_container_reloads_the_listener(auth_client, monkeypatch, signals, restarts,
                                                        https_files, unbound):
    _mode(monkeypatch, docker=True)
    listener_tls.note_master(os.getppid())
    r = auth_client.post('/api/v2/system/https/regenerate', json={'common_name': 'reload.test'})
    assert r.status_code == 200, r.data
    data = r.get_json()['data']
    assert data == {'listener_reload': listener_tls.RELOADING}
    assert signals == [(os.getppid(), signal.SIGHUP)] and restarts == []


def test_apply_in_a_container_reloads_the_listener(auth_client, monkeypatch, signals, restarts,
                                                   https_files, unbound, create_cert):
    _mode(monkeypatch, docker=True)
    listener_tls.note_master(os.getppid())
    cert = create_cert(cn='apply-reload.example.test')
    r = auth_client.post('/api/v2/system/https/apply', json={'cert_id': cert['id']})
    assert r.status_code == 200, r.data
    assert r.get_json()['data'] == {'listener_reload': listener_tls.RELOADING}
    assert signals == [(os.getppid(), signal.SIGHUP)]


def test_an_apply_whose_reload_fails_says_so(auth_client, monkeypatch, signals, restarts, https_files,
                                             unbound, create_cert):
    _mode(monkeypatch, docker=True)
    cert = create_cert(cn='apply-noreload.example.test')
    r = auth_client.post('/api/v2/system/https/apply', json={'cert_id': cert['id']})
    assert r.status_code == 200, r.data
    body = r.get_json()
    assert body['data']['listener_reload'] == listener_tls.FAILED and body['data']['error']
    assert 'not reloaded' in body['message']


def test_a_renewal_of_the_bound_certificate_reloads_the_listener(app, monkeypatch, signals, restarts,
                                                                 https_files, unbound, create_cert):
    from services import https_binding
    _mode(monkeypatch, docker=True)
    listener_tls.note_master(os.getppid())
    cert = create_cert(cn='renew-reload.example.test')
    with app.app_context():
        https_binding.set_bound_refid(cert['refid'])
        outcome = https_binding.apply_bound_now(cert['refid'])
    assert outcome[0] == listener_tls.RELOADING
    assert signals == [(os.getppid(), signal.SIGHUP)]


def test_a_renewal_whose_reload_fails_is_an_error_and_a_failed_audit(app, monkeypatch, signals,
                                                                      restarts, https_files, unbound,
                                                                      create_cert, caplog):
    from models import AuditLog
    from services import https_binding
    _mode(monkeypatch, docker=True)
    cert = create_cert(cn='renew-noreload.example.test')
    with app.app_context():
        https_binding.set_bound_refid(cert['refid'])
        floor = AuditLog.query.order_by(AuditLog.id.desc()).first().id
        with caplog.at_level(logging.ERROR):
            outcome = https_binding.apply_bound_now(cert['refid'])
        entry = (AuditLog.query.filter(AuditLog.id > floor, AuditLog.action == 'https_apply')
                 .order_by(AuditLog.id.desc()).first())
    assert outcome[0] == listener_tls.FAILED
    assert any(r.levelno == logging.ERROR and 'not served' in r.getMessage() for r in caplog.records)
    assert entry is not None and entry.success is False
    assert 'not reloaded' in entry.details


# --- mTLS, Windows former CAs and WSTEP: the same reload ----------------------------------------

def test_an_mtls_change_in_a_container_reloads_the_listener(auth_client, monkeypatch, signals, restarts):
    _mode(monkeypatch, docker=True)
    listener_tls.note_master(os.getppid())
    current = auth_client.get('/api/v2/mtls/settings').get_json()['data'].get('required', False)
    r = auth_client.put('/api/v2/mtls/settings', json={'required': current})
    assert r.status_code == 200, r.data
    data = r.get_json()['data']
    assert data['needs_restart'] is True and data['listener_reload'] == listener_tls.RELOADING
    assert signals == [(os.getppid(), signal.SIGHUP)] and restarts == []


def test_former_cas_changed_in_a_container_reload_the_listener(app, monkeypatch, signals, restarts):
    from api.v2.windows_profiles import _listener_restart
    _mode(monkeypatch, docker=True)
    listener_tls.note_master(os.getppid())
    with app.app_context():
        needs, message = _listener_restart(False)
    assert needs is True and 'reload' in message
    assert signals == [(os.getppid(), signal.SIGHUP)]


def test_a_wstep_toggle_in_a_container_reloads_the_listener(app, auth_client, monkeypatch, signals,
                                                           restarts):
    from tests.windows_profile_support import restore, snapshot
    _mode(monkeypatch, docker=True)
    listener_tls.note_master(os.getppid())
    with app.app_context():
        saved = snapshot(('wstep_enabled',))
    try:
        current = auth_client.get('/api/v2/windows-profiles/settings').get_json()['data']
        r = auth_client.patch('/api/v2/windows-profiles/settings',
                              json={'wstep_enabled': not current.get('wstep_enabled')})
        assert r.status_code == 200, r.data
        assert (r.get_json().get('data') or {}).get('listener_reload') == listener_tls.RELOADING
        assert signals == [(os.getppid(), signal.SIGHUP)] and restarts == []
    finally:
        with app.app_context():
            restore(saved)


# --- the master's side ------------------------------------------------------------------------

def _worker(ppid):
    import types
    return types.SimpleNamespace(cfg=types.SimpleNamespace(graceful_timeout=30), ppid=ppid,
                                 log=logging.getLogger('test.worker'))


def test_a_worker_notes_the_master_that_started_it(app, monkeypatch):
    from tests.test_db_fork import _load_gunicorn_config
    monkeypatch.setitem(listener_tls._state, 'master', None)
    module = _load_gunicorn_config(monkeypatch, app)
    # The in-memory test database dies with its pool: nothing the worker drops is dropped here
    for target in ('utils.db_fork.forget_inherited_connections',
                   'services.syslog_service.syslog_forwarder.forget_inherited_socket',
                   'protocol_http_server.start_http_protocol_server',
                   'services.acme.dns_update.server.start_dns_update_server',
                   'services.cluster_commands.start_applier', 'services.ws_relay.start_reader',
                   'utils.sqlite_wait.serve_web_worker'):
        monkeypatch.setattr(target, lambda *a, **k: None)
    module.post_worker_init(_worker(os.getppid()))
    assert listener_tls.gunicorn_master() == os.getppid()


@pytest.mark.parametrize('asked', [True, False], ids=['tls-reload', 'operator-hup'])
def test_a_tls_reload_keeps_the_scheduler_process(app, monkeypatch, tmp_path, asked):
    import types
    from tests.test_db_fork import _load_gunicorn_config
    module = _load_gunicorn_config(monkeypatch, app)
    monkeypatch.setattr(module, 'data_path', str(tmp_path))
    if asked:
        (tmp_path / listener_tls.RELOAD_MARKER).write_text('1')
    restarted = []
    monkeypatch.setattr('scheduler_supervisor.supervisor.restart', lambda: restarted.append(1))
    module.on_reload(types.SimpleNamespace(log=logging.getLogger('test.master')))
    assert restarted == ([] if asked else [1])
