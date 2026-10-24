# Gunicorn configuration file for UCM
# Single config for all deployments (DEB, RPM, Docker)

# Monkey-patch BEFORE any other imports to avoid gevent + Python 3.13
# SSLContext/SSLSocket recursion bugs (super() closure captures wrong class)
from gevent import monkey
monkey.patch_all()

import os
import ssl
import sys

# Detect environment
base_path = os.getenv('UCM_BASE_PATH', '/opt/ucm')
data_path = os.getenv('DATA_DIR', f'{base_path}/data')
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
timeout = 120
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
    ``WSTEP_TLS12_CAP_NEEDED`` (read once at worker startup, see
    ``_wstep_enabled`` below) means installs that never touch Windows
    autoenrollment keep TLS 1.3 for everything else, instead of every UCM
    instance silently losing it by default. ``api/v2/wstep.py`` restarts
    the service whenever ``wstep_enabled`` is toggled, so this stays in
    sync with the setting rather than only taking effect on the next
    unrelated restart.
    """
    ctx = default_ssl_context_factory()
    if WSTEP_TLS12_CAP_NEEDED:
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    if conf.ca_certs:
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


from boot_config import mtls_client_ca, wstep_enabled

# Drives the TLS 1.2 cap in ssl_context().
WSTEP_TLS12_CAP_NEEDED = wstep_enabled(data_path)


MTLS_MODE_FILE = 'mtls_mode'


def _remember_mtls_mode(required):
    """What the last successful read decided, for the next start."""
    try:
        with open(os.path.join(data_path, MTLS_MODE_FILE), 'w') as handle:
            handle.write('required' if required else 'optional')
    except OSError as e:
        print(f"mTLS: could not record the mode: {e}", file=sys.stderr)


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
    if not (os.path.exists(ca_file_path) and os.path.exists(mode_path)):
        print("mTLS: no previous configuration to fall back on; the socket "
              "will not ask for a client certificate", file=sys.stderr)
        return
    try:
        with open(mode_path) as handle:
            required = handle.read().strip() == 'required'
    except OSError:
        required = False
    ca_certs = ca_file_path
    cert_reqs = 2 if required else 1
    print(f"mTLS: settings unreadable, keeping the last known configuration "
          f"({'REQUIRED' if required else 'OPTIONAL'})", file=sys.stderr)


def _load_mtls_config():
    """Configure client certificate verification from the stored settings."""
    global cert_reqs, ca_certs

    try:
        found = mtls_client_ca(data_path)
        if not found:
            _remember_mtls_mode(False)
            return
        full_chain, ca_name, required = found

        # Write CA cert atomically (temp file + rename) with restricted permissions
        import tempfile
        import stat
        ca_file_path = os.path.join(data_path, 'mtls_ca.pem')
        fd, temp_path = tempfile.mkstemp(dir=data_path, prefix='.mtls_ca_', suffix='.tmp')
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(full_chain)
            os.chmod(temp_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)
            os.rename(temp_path, ca_file_path)
        except Exception as e:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise e

        ca_certs = ca_file_path
        cert_reqs = 2 if required else 1
        _remember_mtls_mode(required)

        mode = "REQUIRED" if cert_reqs == 2 else "OPTIONAL"
        print(f"mTLS: {mode}, trusted CA: {ca_name}", file=sys.stderr)

    except Exception as e:
        print(f"mTLS: config load failed: {e}", file=sys.stderr)
        _reuse_last_known_mtls()


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

def on_reload(server):
    server.log.info("Reloading UCM")

def worker_int(worker):
    worker.log.info("Worker received INT or QUIT signal")

def worker_abort(worker):
    worker.log.info("Worker received SIGABRT signal")

def post_worker_init(worker):
    """Post-worker initialization:
    1. Suppress noisy SSL/connection tracebacks from gevent
    2. Start HTTP protocol server for CDP/OCSP (if configured)
    """
    import ssl
    import gevent

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
