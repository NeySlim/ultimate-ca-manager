# Gunicorn configuration file for UCM
# Single config for all deployments (DEB, RPM, Docker)

# Monkey-patch BEFORE any other imports to avoid gevent + Python 3.13
# SSLContext/SSLSocket recursion bugs (super() closure captures wrong class)
from gevent import monkey
monkey.patch_all()

import os
import ssl
import sys

# Before the preloaded app: the master and its workers only register the scheduled
# tasks, which run in the scheduler process started below (when_ready)
os.environ['UCM_SCHEDULER_SUPERVISED'] = '1'

# Stamps the process start (HA cluster commands) before the mTLS and WSTEP settings are read
import services.cluster_commands  # noqa: E402

# Detect environment
base_path = os.getenv('UCM_BASE_PATH', '/opt/ucm')
data_path = os.getenv('DATA_DIR', f'{base_path}/data')
# HA: the restarts committed before the settings below are read; a later one restarts this node
services.cluster_commands.snapshot_committed_restarts(data_path)
is_docker = os.path.exists('/.dockerenv') or os.getenv('UCM_DOCKER') == '1'

# Server socket — HOST selects the listen address (0.0.0.0 by default,
# :: for IPv6 + IPv4 dual-stack), see listen_address.py
from listen_address import format_bind, get_bind_host
bind = format_bind(get_bind_host(), os.getenv('HTTPS_PORT', '8443'))
backlog = 2048

# Worker processes — single worker required for WebSocket broadcast across tabs
# gevent handles concurrency via greenlets (1000+ concurrent connections)
workers = 1
worker_class = 'workers.MTLSGeventWebSocketWorker'
worker_connections = 1000
# UCM_WORKER_TIMEOUT, 120 s by default; out of bounds the start is refused
from worker_timeout import worker_timeout  # noqa: E402
timeout = worker_timeout()
keepalive = 5

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# SSL/TLS
certfile = os.getenv('HTTPS_CERT_PATH', f'{data_path}/https_cert.pem')
keyfile = os.getenv('HTTPS_KEY_PATH', f'{data_path}/https_key.pem')
cert_reqs = 0
ca_certs = None
do_handshake_on_connect = True


def ssl_context(conf, default_ssl_context_factory):
    """Custom SSL context that ensures CA names are sent in CertificateRequest.

    Python's ssl.SSLContext.load_verify_locations() populates the trust store
    but on OpenSSL 3.x it does NOT set the client CA list sent in the TLS
    CertificateRequest message. Without that list, browsers cannot determine
    which client certificate to offer. We call SSL_CTX_set_client_CA_list()
    via ctypes to fix this.

    Also caps the negotiated protocol at TLS 1.2, but *only* when WSTEP is
    administratively enabled. When this context offers TLS 1.3 but a
    client's ClientHello only proposes TLS 1.2 (no supported_versions
    extension — true of some Windows schannel clients, observed here with
    MS-WSTEP/CEP enrollment traffic), OpenSSL 3.x sets the RFC 8446 §4.1.3
    downgrade-protection sentinel in ServerHello.random. That's
    spec-compliant, but at least some real-world TLS-1.2-only clients abort
    the connection on seeing it rather than ignoring it (they never asked
    for 1.3, so per spec they have no reason to be checking for the
    sentinel at all, but empirically some do anyway). The sentinel is only
    ever emitted when the server itself could have negotiated 1.3; capping
    this context to a max of 1.2 removes the trigger entirely.

    This same listening socket also serves everything else UCM does
    (browsers, ACME, SCEP, EST, the admin API) — TLS version negotiation
    happens before the HTTP path is known, so there's no way to cap only
    WSTEP traffic without a separate port. Scoping the cap to
    ``WSTEP_TLS12_CAP_NEEDED`` (read as the master loads this file, see
    ``_wstep_enabled`` below) means installs that never touch Windows
    autoenrollment keep TLS 1.3 for everything else, instead of every UCM
    instance silently losing it by default. The Windows settings route reloads
    the listener whenever ``wstep_enabled`` is toggled (SIGHUP to the master,
    which re-runs this file and replaces the workers, #452), so this stays in
    sync with the setting rather than only taking effect on the next
    unrelated restart; a new certificate or mTLS trust is applied the same way.
    """
    from utils.client_cert import pin_listener_trust, pin_listener_trust_file
    from utils.listener_tls import pin_served_certificate

    def build():
        if conf.ca_certs:
            # The guard of the application follows the bundle this context loaded, read once here
            return pin_listener_trust_file(conf.ca_certs, default_ssl_context_factory)
        built = default_ssl_context_factory()
        pin_listener_trust(())
        return built
    # The HTTPS state compares the leaf this worker serves with the file on disk
    ctx = pin_served_certificate(conf.certfile, build)
    if WSTEP_TLS12_CAP_NEEDED:
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    if conf.ca_certs:
        anchor_client_verification(ctx)
        try:
            import ctypes
            libssl = ctypes.CDLL('libssl.so.3')

            _load_file = libssl.SSL_load_client_CA_file
            _load_file.argtypes = [ctypes.c_char_p]
            _load_file.restype = ctypes.c_void_p

            _set_list = libssl.SSL_CTX_set_client_CA_list
            _set_list.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            _set_list.restype = None

            _get_verify = libssl.SSL_CTX_get_verify_mode
            _get_verify.argtypes = [ctypes.c_void_p]
            _get_verify.restype = ctypes.c_int

            # Extract SSL_CTX* from CPython SSLContext (PyObject_HEAD + first field)
            ssl_ctx_ptr = ctypes.c_void_p.from_address(id(ctx) + 16).value
            if ssl_ctx_ptr and _get_verify(ssl_ctx_ptr) == ctx.verify_mode:
                ca_stack = _load_file(conf.ca_certs.encode())
                if ca_stack:
                    _set_list(ssl_ctx_ptr, ca_stack)
                    print("mTLS: client CA names will be sent in CertificateRequest",
                          file=sys.stderr)
        except Exception as e:
            print(f"mTLS: could not set client CA list (non-fatal): {e}",
                  file=sys.stderr)
    return ctx


from boot_config import (MTLS_UNDECIDED, HttpsMaterialError, anchor_client_verification,
                         materialize_https, mtls_client_ca, mtls_former_cas, wstep_enabled)

# Drives the TLS 1.2 cap in ssl_context().
WSTEP_TLS12_CAP_NEEDED = wstep_enabled(data_path)


MTLS_MODE_FILE = 'mtls_mode'


def _remember_mtls_mode(mode):
    """What the last successful read decided (required, optional or off), for the next start."""
    try:
        with open(os.path.join(data_path, MTLS_MODE_FILE), 'w') as handle:
            handle.write(mode)
    except OSError as e:
        print(f"mTLS: could not record the mode: {e}", file=sys.stderr)


def _write_private(name, content):
    """Write *name* in the data directory atomically (temp file + rename), owner and group only."""
    import tempfile
    import stat
    path = os.path.join(data_path, name)
    fd, temp_path = tempfile.mkstemp(dir=data_path, prefix=f'.{name}_', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(content)
        os.chmod(temp_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)
        os.rename(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
    return path


def _reuse_last_known_mtls():
    """Keep the previous start's client-certificate setting.

    The settings live in the database, and a database that is briefly out of
    reach used to mean a socket that asks for no client certificate at all.
    Serving the last configuration that worked is closer to the operator's
    intent than silently turning mTLS off.
    """
    global cert_reqs, ca_certs

    ca_file_path = os.path.join(data_path, 'mtls_ca.pem')
    mode_path = os.path.join(data_path, MTLS_MODE_FILE)
    try:
        with open(mode_path) as handle:
            mode = handle.read().strip()
    except OSError:
        mode = None
    if mode == 'off':  # off at the last start: a CA file an earlier setting left is not asked for
        return
    if mode is None or not os.path.exists(ca_file_path):
        print("mTLS: no previous configuration to fall back on; the socket "
              "will not ask for a client certificate", file=sys.stderr)
        return
    required = mode == 'required'
    ca_certs = ca_file_path
    cert_reqs = 2 if required else 1
    print(f"mTLS: settings unreadable, keeping the last known configuration "
          f"({'REQUIRED' if required else 'OPTIONAL'})", file=sys.stderr)


def _load_mtls_config():
    """Configure client certificate verification from the stored settings."""
    global cert_reqs, ca_certs

    try:
        found = mtls_client_ca(data_path)
        if found is MTLS_UNDECIDED:
            # No settings to read: a first start has no mode on record, a lost table keeps the last one
            if os.path.exists(os.path.join(data_path, MTLS_MODE_FILE)):
                _reuse_last_known_mtls()
            return
        if not found:
            _remember_mtls_mode('off')
            return
        ca_pem, ca_name, required = found
        # The former CAs a Windows profile lists renew over TLS: anchors beside the mTLS CA, whose
        # certificates the application keeps from every route but WSTEP renewal
        former = mtls_former_cas(data_path)
        # The bundle names its own former CAs: each worker arms its guard from the bundle it loads
        from utils.client_cert import former_cas_header
        ca_file_path = _write_private('mtls_ca.pem', former_cas_header(f[0] for f in former) + ''.join(
            pem if pem.endswith('\n') else pem + '\n' for pem in [ca_pem, *(f[1] for f in former)]))

        ca_certs = ca_file_path
        cert_reqs = 2 if required else 1
        _remember_mtls_mode('required' if required else 'optional')

        mode = "REQUIRED" if cert_reqs == 2 else "OPTIONAL"
        print(f"mTLS: {mode}, trusted CA: {ca_name}", file=sys.stderr)
        if former:
            print("mTLS: former CAs trusted for Windows renewal only: "
                  + ', '.join(name for _refid, _pem, name in former), file=sys.stderr)

    except Exception as e:
        print(f"mTLS: config load failed: {e}", file=sys.stderr)
        _reuse_last_known_mtls()


def _materialize_https():
    """Before the TLS socket opens: the HTTPS pair the database names, on every node."""
    try:
        done = materialize_https(data_path, certfile, keyfile)
    except HttpsMaterialError as e:
        print(f"HTTPS: {e}; the certificate files on disk are left as they are", file=sys.stderr)
        return
    except Exception as e:
        print(f"HTTPS: certificate not read from the database ({type(e).__name__}: {e}); "
              "the certificate files on disk are left as they are", file=sys.stderr)
        return
    if done:
        print(f"HTTPS: {done}", file=sys.stderr)


_materialize_https()
_load_mtls_config()

# Logging: stdout in Docker, files in native installs
if is_docker:
    accesslog = '-'
    errorlog = '-'
else:
    accesslog = os.getenv('ACCESS_LOG', '/var/log/ucm/access.log')
    errorlog = os.getenv('ERROR_LOG', '/var/log/ucm/error.log')
loglevel = os.getenv('LOG_LEVEL', 'info')
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'
# Reset tokens and OAuth codes travel in URLs: kept out of the access log.
from utils.access_log import RedactingLogger  # noqa: E402
logger_class = RedactingLogger

# Process naming
proc_name = 'ucm'

# Preload app so DB init runs once in master process
preload_app = True

# Server mechanics
# Gunicorn 25 opens a control socket in the working directory by default. The
# service runs from /opt/ucm/backend, which ProtectSystem=strict keeps
# read-only, so the socket could never be created and an error was logged at
# every start (#349). UCM never uses the control interface, so it stays off.
# The key is control_socket_disable; the command-line flag is
# --no-control-socket and gunicorn ignores an unknown key here in silence.
control_socket_disable = True
daemon = False
pidfile = None
umask = 0o027
user = None
group = None
tmp_upload_dir = None

# Server hooks
def on_starting(server):
    server.log.info("Starting UCM with Gunicorn")

def _release_node():
    # After the scheduler process's last heartbeat: the node's next start takes its row at once
    from services.scheduler_leader import release_claimed_node
    release_claimed_node()

def when_ready(server):
    from scheduler_supervisor import supervisor
    # Run as soon as the master stops (beside the workers' drain), else by on_exit
    supervisor.start(server, on_stopped=_release_node)

def on_reload(server):
    server.log.info("Reloading UCM")
    from utils.listener_tls import take_reload_request
    if take_reload_request(data_path):
        # Asked for the TLS listener alone: the scheduler process serves no TLS, its tasks go on
        server.log.info("TLS listener reload: the scheduler process keeps running")
        return
    # The scheduler process takes the new code and configuration too
    from scheduler_supervisor import supervisor
    supervisor.restart()

def on_exit(server):
    from scheduler_supervisor import supervisor
    supervisor.stop(on_stopped=_release_node)
    # Only once Arbiter.stop() drained the workers: a full-stop migration must not run under them
    from migration_runner import mark_node_stopped
    mark_node_stopped()

def worker_int(worker):
    worker.log.info("Worker received INT or QUIT signal")

def worker_abort(worker):
    worker.log.info("Worker received SIGABRT signal")

def worker_exit(server, worker):
    # A worker leaving with a restart claim not given back would keep its successor from restarting
    from services.cluster_commands import stop_applier
    stop_applier()
    from services.ws_relay import stop_reader
    stop_reader()
    from services.backup.restore.invalidate import stop_epoch_watcher
    stop_epoch_watcher()

def post_worker_init(worker):
    """Post-worker initialization:
    0. Drop the database and syslog connections inherited from the master
    1. Suppress noisy SSL/connection tracebacks from gevent
    2. Start HTTP protocol server for CDP/OCSP (if configured)
    3. Start the DNS UPDATE listener (if configured)
    """
    import ssl
    import gevent

    # The master this worker may ask for a TLS listener reload (SIGHUP), checked again at that time
    from utils.listener_tls import note_master
    note_master(worker.ppid)

    # Before any query: the pool still holds the master's connections
    from models import db
    from utils.db_fork import forget_inherited_connections
    from wsgi import app as flask_app
    with flask_app.app_context():
        forget_inherited_connections(db.engines.values())
    # A restore holding SQLite never stops this worker's greenlets in sqlite3's busy wait
    from utils.sqlite_wait import serve_web_worker
    serve_web_worker(flask_app)
    from services.syslog_service import syslog_forwarder
    syslog_forwarder.forget_inherited_socket()

    hub = gevent.get_hub()
    _original_handle_error = hub.handle_error

    def _quiet_handle_error(context, type, value, tb):
        if type and issubclass(type, (ssl.SSLError, ConnectionResetError, BrokenPipeError, OSError)):
            worker.log.debug("Connection error suppressed: %s", value)
            return
        _original_handle_error(context, type, value, tb)

    hub.handle_error = _quiet_handle_error

    # Start HTTP protocol server for CDP/OCSP (no TLS)
    try:
        from protocol_http_server import start_http_protocol_server
        from wsgi import app as flask_app
        with flask_app.app_context():
            # After a reload the old worker holds the port for up to graceful_timeout
            error_after = float(getattr(worker.cfg, 'graceful_timeout', 30)) + 5
            start_http_protocol_server(flask_app, error_after=error_after)
    except Exception as e:
        import logging
        logging.getLogger('ucm.protocol').warning(
            "Could not initialize HTTP protocol server: %s", e
        )

    # Start the DNS UPDATE (RFC 2136) listener (UDP and TCP, if a port is configured)
    try:
        from services.acme.dns_update.server import start_dns_update_server
        from wsgi import app as flask_app
        with flask_app.app_context():
            # After a reload the old worker holds the port for up to graceful_timeout
            error_after = float(getattr(worker.cfg, 'graceful_timeout', 30)) + 5
            start_dns_update_server(flask_app, error_after=error_after)
    except Exception as e:
        import logging
        logging.getLogger('ucm.protocol').warning(
            "Could not initialize DNS UPDATE listener: %s", e
        )

    # HA: this worker applies the cluster commands and owns this node's restart turn
    try:
        from services.cluster_commands import start_applier
        from wsgi import app as flask_app
        start_applier(flask_app, record=True, master_pid=worker.ppid)
    except Exception as e:
        import logging
        logging.getLogger('ucm.cluster').error("Cluster command applier not started: %s", e)

    # A restore run by another process advanced the session epoch: this worker drops its
    # caches within EPOCH_CHECK_SECONDS, on its own timer rather than on a request
    try:
        from services.backup.restore.invalidate import start_epoch_watcher
        from wsgi import app as flask_app
        start_epoch_watcher(flask_app)
    except Exception as e:
        import logging
        logging.getLogger('ucm.backup').error("Session epoch cache watcher not started: %s", e)

    # Without Redis: this worker emits to its clients the events of the scheduler process,
    # and in HA those of the other workers and nodes, to which it also publishes its own
    try:
        from services.ws_relay import start_reader
        from wsgi import app as flask_app
        start_reader(flask_app)
    except Exception as e:
        import logging
        logging.getLogger('ucm.websocket').error("WebSocket relay reader not started: %s", e)
