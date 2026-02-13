"""
Remote Syslog Forwarder for Audit Logs
Forwards audit events to a remote syslog server via UDP, TCP, or TCP+TLS.
"""

import socket
import ssl
import logging
import logging.handlers
import json
from datetime import datetime

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


class SyslogForwarder:
    """Forwards audit log entries to a remote syslog server."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    # All available event categories (resource_type values)
    ALL_CATEGORIES = ['certificate', 'ca', 'csr', 'user', 'acme', 'scep', 'system']

    def _initialize(self):
        self._enabled = False
        self._host = ''
        self._port = 514
        self._protocol = 'udp'
        self._tls = False
        self._categories = list(self.ALL_CATEGORIES)  # all enabled by default
        self._socket = None
        self._initialized = True

    def configure(self, enabled=False, host='', port=514, protocol='udp',
                  tls=False, categories=None):
        """Configure the syslog forwarder."""
        if not self._initialized:
            self._initialize()

        self._close()

        self._enabled = enabled
        self._host = host
        self._port = int(port) if port else 514
        self._protocol = protocol.lower() if protocol else 'udp'
        self._tls = tls and self._protocol == 'tcp'
        self._categories = categories if categories is not None else list(self.ALL_CATEGORIES)

        if self._enabled and self._host:
            logger.info(f"📡 Syslog forwarder configured: {self._protocol.upper()}://{self._host}:{self._port} "
                        f"(tls={self._tls}, categories={self._categories})")
        else:
            logger.info("📡 Syslog forwarder disabled")

    def _close(self):
        """Close existing socket."""
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

    def _get_socket(self):
        """Get or create socket connection."""
        if self._socket:
            return self._socket

        try:
            if self._protocol == 'tcp':
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                if self._tls:
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    sock = ctx.wrap_socket(sock, server_hostname=self._host)
                sock.connect((self._host, self._port))
                self._socket = sock
            else:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(5)
                self._socket = sock
            return self._socket
        except Exception as e:
            logger.error(f"Syslog connection failed: {e}")
            self._socket = None
            return None

    def _build_message(self, audit_log) -> bytes:
        """Build RFC 5424 syslog message from audit log entry."""
        facility_code = FACILITY_MAP['local0']
        severity_code = SEVERITY_MAP['info'] if audit_log.success else SEVERITY_MAP['warning']
        pri = (facility_code * 8) + severity_code

        timestamp = audit_log.timestamp.strftime('%Y-%m-%dT%H:%M:%S.%fZ') if audit_log.timestamp else datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        hostname = '-'

        # Structured data
        sd_parts = []
        if audit_log.action:
            sd_parts.append(f'action="{audit_log.action}"')
        if audit_log.username:
            sd_parts.append(f'user="{audit_log.username}"')
        if audit_log.ip_address:
            sd_parts.append(f'ip="{audit_log.ip_address}"')
        if audit_log.resource_type:
            sd_parts.append(f'resource_type="{audit_log.resource_type}"')
        if audit_log.resource_id:
            sd_parts.append(f'resource_id="{audit_log.resource_id}"')
        if audit_log.resource_name:
            sd_parts.append(f'resource_name="{audit_log.resource_name}"')
        sd_parts.append(f'success="{audit_log.success}"')

        sd = f'[ucm@0 {" ".join(sd_parts)}]' if sd_parts else '-'

        msg_text = audit_log.details or f'{audit_log.action}'
        message = f'<{pri}>1 {timestamp} {hostname} UCM - - {sd} {msg_text}'

        if self._protocol == 'tcp':
            return (message + '\n').encode('utf-8')
        return message.encode('utf-8')

    def send(self, audit_log):
        """Send an audit log entry to the remote syslog server. Non-blocking on failure."""
        if not self._enabled or not self._host:
            return False

        # Filter by event category
        resource_type = getattr(audit_log, 'resource_type', None) or ''
        if self._categories and resource_type and resource_type not in self._categories:
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
            except Exception:
                pass
            return False
        except Exception as e:
            logger.debug(f"Syslog send failed: {e}")
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
            timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            message = f'<{pri}>1 {timestamp} - UCM - - [ucm@0 action="test"] UCM syslog test message'

            if self._protocol == 'tcp':
                sock.sendall((message + '\n').encode('utf-8'))
            else:
                sock.sendto(message.encode('utf-8'), (self._host, self._port))

            return {'success': True, 'message': f'Test message sent via {self._protocol.upper()} to {self._host}:{self._port}'}
        except Exception as e:
            self._close()
            return {'success': False, 'error': str(e)}

    def load_from_db(self):
        """Load syslog config from database."""
        if not self._initialized:
            self._initialize()
        try:
            from models import SystemConfig
            def _get(key, default=None):
                c = SystemConfig.query.filter_by(key=key).first()
                return c.value if c else default

            categories_raw = _get('syslog_categories', '')
            categories = [c.strip() for c in categories_raw.split(',') if c.strip()] if categories_raw else list(self.ALL_CATEGORIES)

            self.configure(
                enabled=_get('syslog_enabled', 'false').lower() == 'true',
                host=_get('syslog_host', ''),
                port=int(_get('syslog_port', '514')),
                protocol=_get('syslog_protocol', 'udp'),
                tls=_get('syslog_tls', 'false').lower() == 'true',
                categories=categories,
            )
        except Exception as e:
            logger.debug(f"Syslog config load skipped: {e}")
            self._initialize()

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
            'categories': self._categories,
        }


# Singleton instance
syslog_forwarder = SyslogForwarder()
