"""
Remote Syslog Forwarder for Audit Logs
Forwards audit events to a remote syslog server via UDP, TCP, or TCP+TLS.
"""

import os
import re
import socket
import ssl
import time
import logging
import logging.handlers
import json
from datetime import datetime
from utils.datetime_utils import utc_now
from utils.request_helpers import safe_call

logger = logging.getLogger(__name__)

# Syslog facility mapping
FACILITY_MAP = {
    'kern': 0, 'user': 1, 'mail': 2, 'daemon': 3,
    'auth': 4, 'syslog': 5, 'lpr': 6, 'news': 7,
    'local0': 16, 'local1': 17, 'local2': 18, 'local3': 19,
    'local4': 20, 'local5': 21, 'local6': 22, 'local7': 23,
}

# Syslog severity mapping
SEVERITY_MAP = {
    'emerg': 0, 'alert': 1, 'crit': 2, 'err': 3,
    'warning': 4, 'notice': 5, 'info': 6, 'debug': 7,
}

# How long the resolved HOSTNAME is cached before re-reading system_name
_HOSTNAME_CACHE_TTL = 300
# Another process (the scheduler, another node) may have saved the settings: re-read this often
REFRESH_SECONDS = 5.0


def _sd_escape(value) -> str:
    """Escape a STRUCTURED-DATA PARAM-VALUE (RFC 5424 §6.3.3: \\, \" and ])."""
    return str(value).replace('\\', '\\\\').replace('"', '\\"').replace(']', '\\]')


def _sanitize_hostname(name) -> str:
    """Coerce a value into a valid RFC 5424 HOSTNAME (printable US-ASCII, no spaces, ≤255)."""
    if not name:
        return ''
    name = re.sub(r'[^\x21-\x7e]+', '-', str(name).strip()).strip('-')
    return name[:255]


class SyslogForwarder:
    """Forwards audit log entries to a remote syslog server."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    # The categories an operator can deselect; a resource type in none of them is always sent
    ALL_CATEGORIES = ['certificate', 'ca', 'csr', 'user', 'acme', 'scep', 'system']
    SETTING_KEYS = ('syslog_enabled', 'syslog_host', 'syslog_port', 'syslog_protocol', 'syslog_tls',
                    'syslog_tls_verify', 'syslog_framing', 'syslog_categories')
    _PREFIXES = (('acme_', 'acme'), ('scep_', 'scep'))
    _ALIASES = {'sso': 'user', 'user_certificate': 'certificate',
                'ssh_certificate': 'certificate', 'ssh_ca': 'ca'}

    # Under Users only sign-in activity can be muted: account changes (role, password, MFA) always leave
    _USER_ACTIVITY = ('login', 'logout')
    # Under System, key, encryption, restore, database and settings changes always leave too
    _SYSTEM_ALWAYS = frozenset({
        'master_key_downloaded', 'encryption_enabled', 'encryption_disabled', 'system_encrypt',
        'system_restore', 'database_reset', 'database.switch', 'settings_update',
        'private_key_files_purged', 'backup_delete', 'log_bundle_downloaded'})

    @classmethod
    def category_of(cls, resource_type, action=None):
        """The deselectable category an event belongs to, or None."""
        category = cls._category_of_type(resource_type)
        if category == 'user' and not str(action or '').startswith(cls._USER_ACTIVITY):
            return None
        if category == 'system' and action in cls._SYSTEM_ALWAYS:
            return None
        return category

    @classmethod
    def _category_of_type(cls, resource_type):
        if not resource_type:
            return None
        if resource_type in cls.ALL_CATEGORIES:
            return resource_type
        for prefix, category in cls._PREFIXES:
            if resource_type.startswith(prefix):
                return category
        return cls._ALIASES.get(resource_type)

    def _wanted(self, resource_type, action=None) -> bool:
        # No box checked is read back from the database as all of them: same here
        category = self.category_of(resource_type, action)
        return not self._categories or category is None or category in self._categories

    def _initialize(self):
        self._enabled = False
        self._host = ''
        self._port = 514
        self._protocol = 'udp'
        self._tls = False
        self._tls_verify = True
        self._framing = 'line'
        self._categories = list(self.ALL_CATEGORIES)  # all enabled by default
        self._socket = None
        self._socket_pid = None
        self._hostname = ''
        self._hostname_resolved_at = 0.0
        self._stored = None  # the rows last applied: a refresh applies only a change to them
        self._checked_at = float('-inf')
        self._initialized = True

    def _resolve_hostname(self) -> str:
        """Resolve the syslog HOSTNAME field: system_name setting → machine hostname → NILVALUE.

        Cached for a few minutes so each audit event doesn't re-query the config.
        """
        now = time.time()
        if self._hostname and now - self._hostname_resolved_at < _HOSTNAME_CACHE_TTL:
            return self._hostname

        name = ''
        read = True
        try:
            from models import SystemConfig
            cfg = SystemConfig.query.filter_by(key='system_name').first()
            name = _sanitize_hostname(cfg.value if cfg else '')
        except Exception:
            read = False
        if not name:
            name = _sanitize_hostname(safe_call(socket.gethostname))
        if not read:
            # A fallback taken because SQL was refused must not hide system_name for minutes
            return name or '-'

        self._hostname = name or '-'
        self._hostname_resolved_at = now
        return self._hostname

    def configure(self, enabled=False, host='', port=514, protocol='udp',
                  tls=False, tls_verify=True, categories=None, framing=None):
        """Configure the syslog forwarder."""
        if not self._initialized:
            self._initialize()

        self._close()

        self._enabled = enabled
        self._host = host
        self._port = int(port) if port else 514
        self._protocol = protocol.lower() if protocol else 'udp'
        self._tls = tls and self._protocol == 'tcp'
        self._tls_verify = tls_verify
        default_framing = 'octet' if self._tls else 'line'
        self._framing = framing.lower() if framing else default_framing
        if self._framing not in ('octet', 'line'):
            raise ValueError("Syslog framing must be 'octet' or 'line'")
        self._categories = list(categories) if categories else list(self.ALL_CATEGORIES)
        # Force re-resolution of the HOSTNAME field on next send
        self._hostname = ''
        self._hostname_resolved_at = 0.0

        if self._enabled and self._host:
            logger.info(f"📡 Syslog forwarder configured: {self._protocol.upper()}://{self._host}:{self._port} "
                        f"(tls={self._tls}, framing={self._framing}, categories={self._categories})")
        else:
            logger.info("📡 Syslog forwarder disabled")

    def _close(self):
        """Close existing socket."""
        self.forget_inherited_socket()
        if self._socket:
            safe_call(self._socket.close)
            self._socket = None

    def forget_inherited_socket(self):
        """Drop a connection opened by the process this one was forked from.

        Frames from both would interleave on it. Only this copy of the descriptor
        is closed: no FIN, no TLS close_notify, the parent's stream is untouched.
        """
        sock = getattr(self, '_socket', None)
        if sock is None or self._socket_pid == os.getpid():
            return
        self._socket = None
        try:
            os.close(sock.detach())
        except OSError:
            pass

    def _get_socket(self):
        """Get or create socket connection."""
        self.forget_inherited_socket()
        if self._socket:
            return self._socket

        try:
            if self._protocol == 'tcp':
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                if self._tls:
                    ctx = ssl.create_default_context()
                    if not self._tls_verify:
                        ctx.check_hostname = False
                        ctx.verify_mode = ssl.CERT_NONE
                    sock = ctx.wrap_socket(sock, server_hostname=self._host)
                sock.connect((self._host, self._port))
                self._socket = sock
            else:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(5)
                self._socket = sock
            self._socket_pid = os.getpid()
            return self._socket
        except Exception as e:
            logger.error(f"Syslog connection failed: {e}")
            self._socket = None
            return None

    def _frame_message(self, message: str) -> bytes:
        """Apply RFC 6587 framing to a TCP syslog message."""
        encoded = message.encode('utf-8')
        if self._protocol != 'tcp':
            return encoded
        if self._framing == 'octet':
            return str(len(encoded)).encode('ascii') + b' ' + encoded
        return encoded + b'\n'

    def _build_message(self, audit_log) -> bytes:
        """Build and frame an RFC 5424 syslog message."""
        facility_code = FACILITY_MAP['local0']
        severity_code = SEVERITY_MAP['info'] if audit_log.success else SEVERITY_MAP['warning']
        pri = (facility_code * 8) + severity_code

        timestamp = audit_log.timestamp.strftime('%Y-%m-%dT%H:%M:%S.%fZ') if audit_log.timestamp else utc_now().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        # A staged entry carries the name resolved while SQL was still allowed
        hostname = getattr(audit_log, 'syslog_hostname', None)
        if not isinstance(hostname, str) or not hostname:
            hostname = self._resolve_hostname()

        # Structured data
        sd_parts = []
        if audit_log.action:
            sd_parts.append(f'action="{_sd_escape(audit_log.action)}"')
        if audit_log.username:
            sd_parts.append(f'user="{_sd_escape(audit_log.username)}"')
        if audit_log.ip_address:
            sd_parts.append(f'ip="{_sd_escape(audit_log.ip_address)}"')
        if audit_log.resource_type:
            sd_parts.append(f'resource_type="{_sd_escape(audit_log.resource_type)}"')
        if audit_log.resource_id:
            sd_parts.append(f'resource_id="{_sd_escape(audit_log.resource_id)}"')
        if audit_log.resource_name:
            sd_parts.append(f'resource_name="{_sd_escape(audit_log.resource_name)}"')
        sd_parts.append(f'success="{audit_log.success}"')

        sd = f'[ucm@0 {" ".join(sd_parts)}]'

        msg_text = audit_log.details or f'{audit_log.action}'
        # Newlines would break RFC 6587 non-transparent TCP framing
        msg_text = ' '.join(str(msg_text).splitlines())
        message = f'<{pri}>1 {timestamp} {hostname} UCM - - {sd} {msg_text}'

        return self._frame_message(message)

    def send(self, audit_log):
        """Send an audit log entry to the remote syslog server. Non-blocking on failure."""
        if not self._enabled or not self._host:
            return False

        if not self._wanted(getattr(audit_log, 'resource_type', None),
                            getattr(audit_log, 'action', None)):
            return False

        try:
            sock = self._get_socket()
            if not sock:
                return False

            message = self._build_message(audit_log)

            if self._protocol == 'tcp':
                sock.sendall(message)
            else:
                sock.sendto(message, (self._host, self._port))

            return True
        except (BrokenPipeError, ConnectionResetError, OSError):
            self._close()
            try:
                sock = self._get_socket()
                if sock:
                    message = self._build_message(audit_log)
                    if self._protocol == 'tcp':
                        sock.sendall(message)
                    else:
                        sock.sendto(message, (self._host, self._port))
                    return True
            except Exception as e:
                logger.debug(f"Syslog retry send failed (after socket reset): {e}", exc_info=True)
            return False
        except Exception as e:
            logger.debug(f"Syslog send failed: {e}", exc_info=True)
            return False

    def test_connection(self) -> dict:
        """Test syslog connection by sending a test message."""
        if not self._host:
            return {'success': False, 'error': 'No host configured'}

        self._close()

        try:
            sock = self._get_socket()
            if not sock:
                return {'success': False, 'error': 'Failed to connect'}

            facility_code = FACILITY_MAP['local0']
            pri = (facility_code * 8) + SEVERITY_MAP['info']
            timestamp = utc_now().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            hostname = self._resolve_hostname()
            message = f'<{pri}>1 {timestamp} {hostname} UCM - - [ucm@0 action="test"] UCM syslog test message'

            framed_message = self._frame_message(message)
            if self._protocol == 'tcp':
                sock.sendall(framed_message)
            else:
                sock.sendto(framed_message, (self._host, self._port))

            return {'success': True, 'message': f'Test message sent via {self._protocol.upper()} to {self._host}:{self._port}'}
        except Exception as e:
            self._close()
            return {'success': False, 'error': str(e)}

    def _read_stored(self) -> dict:
        """The stored settings, read without flushing what the caller has pending.

        Not from an after_commit hook: the session refuses SQL there.
        """
        from models import db, SystemConfig
        with db.session.no_autoflush:
            rows = db.session.query(SystemConfig.key, SystemConfig.value) \
                .filter(SystemConfig.key.in_(self.SETTING_KEYS)).all()
        return {key: value for key, value in rows}

    def _apply_stored(self, stored):
        categories_raw = stored.get('syslog_categories', '')
        categories = [c.strip() for c in categories_raw.split(',') if c.strip()] if categories_raw else list(self.ALL_CATEGORIES)
        try:
            self.configure(
                enabled=stored.get('syslog_enabled', 'false').lower() == 'true',
                host=stored.get('syslog_host', ''),
                port=int(stored.get('syslog_port', '514')),
                protocol=stored.get('syslog_protocol', 'udp'),
                tls=stored.get('syslog_tls', 'false').lower() == 'true',
                tls_verify=stored.get('syslog_tls_verify', 'true').lower() == 'true',
                framing=stored.get('syslog_framing'),
                categories=categories,
            )
        except Exception as e:
            logger.warning(f"Stored syslog settings not applied, forwarding disabled: {e}")
            checked_at = self._checked_at
            self._close()
            self._initialize()
            self._checked_at = checked_at
        self._stored = stored

    def load_from_db(self):
        """Apply the stored settings unless they are the ones this process last applied."""
        if not self._initialized:
            self._initialize()
        try:
            stored = self._read_stored()
        except Exception as e:
            logger.debug(f"Syslog config load skipped: {e}")
            self._initialize()
            self._checked_at = time.monotonic()  # retried by reload_if_changed(), not on every line
            return
        self._checked_at = time.monotonic()
        if stored != self._stored:
            self._apply_stored(stored)

    def postpone_reload(self):
        """The next REFRESH_SECONDS keep the current target (an entry meant for it is on its way)."""
        self._checked_at = time.monotonic()

    def reload_if_changed(self):
        """Apply a change another process saved; the rows are read at most every REFRESH_SECONDS."""
        now = time.monotonic()
        if now - getattr(self, '_checked_at', float('-inf')) < REFRESH_SECONDS:
            return
        self._checked_at = now
        try:
            stored = self._read_stored()
        except Exception as e:
            logger.debug(f"Syslog settings not re-read, the current target stays: {e}")
            return
        if stored != getattr(self, '_stored', None):
            self._apply_stored(stored)

    @property
    def is_enabled(self):
        return self._enabled and bool(self._host)

    @property
    def config(self):
        return {
            'enabled': self._enabled,
            'host': self._host,
            'port': self._port,
            'protocol': self._protocol,
            'tls': self._tls,
            'tls_verify': self._tls_verify,
            'framing': self._framing,
            'categories': self._categories,
        }


# Singleton instance
syslog_forwarder = SyslogForwarder()
