"""UDP and TCP server of the DNS UPDATE (RFC 2136) listener.

gevent ``DatagramServer`` and ``StreamServer`` with bounded pools (plan 2.4).
Every datagram and every TCP message passes a global and a per-IP token bucket
before any parsing. Traffic over a limit is dropped without a response.

Backpressure: a full ``Pool`` blocks the UDP read loop (the kernel buffer then
drops datagrams) and makes the TCP server stop accepting (the listen backlog
takes the rest). Memory and greenlet count stay bounded.

Logs never contain packet bytes, keys or MACs.
"""
import errno
import ipaddress
import logging
import socket
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

from services.acme.dns_update import status
from services.acme.dns_update.constants import MAX_MESSAGE_SIZE
from services.acme.dns_update.handler import LogSampler

logger = logging.getLogger(__name__)

# gevent reads datagrams with recvfrom(8192), above MAX_MESSAGE_SIZE + 1. An oversize
# datagram therefore reaches the handler, which drops it. It is never cut down to a
# valid-looking message.

_server = None  # module-level reference, keeps the servers alive
_retry = None   # greenlet of a pending bind retry, if any

# Bind retry after a reload: the old worker may still hold the port (seconds).
RETRY_FIRST_DELAY = 0.25
RETRY_MAX_DELAY = 4.0


def _sleep(seconds: float) -> None:
    import gevent
    gevent.sleep(seconds)


_clock = time.monotonic  # tests replace both _sleep and _clock


@dataclass(frozen=True)
class ServerLimits:
    udp_pool: int = 16
    tcp_pool: int = 128
    tcp_per_ip: int = 8
    global_rate: float = 200.0      # packets per second, all sources
    global_burst: int = 400
    per_ip_rate: float = 50.0       # packets per second per source IP
    per_ip_burst: int = 100
    per_ip_table: int = 4096        # bounded LRU of per-IP buckets
    tcp_idle_s: float = 10.0        # RFC 7766 §6.2.3, reset only on a FULL message
    tcp_write_s: float = 10.0
    tcp_lifetime_s: float = 120.0


def _limit_key(ip: str) -> str:
    """Key of the per-source limits: the address for IPv4, the /64 network for IPv6.
    One host with a /64 must not get a fresh bucket for every address."""
    try:
        if ipaddress.ip_address(ip).version == 4:
            return ip
        net = ipaddress.IPv6Network(f"{ip}/64", strict=False)
        return str(net.network_address) + "/64"
    except ValueError:
        return ip


class _Bucket:
    __slots__ = ('tokens', 'stamp')

    def __init__(self, tokens: float, stamp: float):
        self.tokens = tokens
        self.stamp = stamp


class RateLimiter:
    """Global token bucket plus a bounded LRU table of per-IP buckets."""

    def __init__(self, limits: ServerLimits, clock=time.monotonic):
        self._limits = limits
        self._clock = clock
        self._global = _Bucket(float(limits.global_burst), clock())
        self._per_ip = OrderedDict()

    def _take(self, bucket: _Bucket, rate: float, burst: int, now: float) -> bool:
        elapsed = max(0.0, now - bucket.stamp)
        bucket.stamp = now
        bucket.tokens = min(float(burst), bucket.tokens + elapsed * rate)
        if bucket.tokens >= 1.0:
            bucket.tokens -= 1.0
            return True
        return False

    def allow(self, ip: str) -> bool:
        lim = self._limits
        now = self._clock()
        ip = _limit_key(ip)
        bucket = self._per_ip.get(ip)
        if bucket is None:
            bucket = _Bucket(float(lim.per_ip_burst), now)
            self._per_ip[ip] = bucket
            while len(self._per_ip) > lim.per_ip_table:
                self._per_ip.popitem(last=False)
        else:
            self._per_ip.move_to_end(ip)
        # The per-IP check goes first: one noisy source must not drain the global bucket.
        if not self._take(bucket, lim.per_ip_rate, lim.per_ip_burst, now):
            return False
        return self._take(self._global, lim.global_rate, lim.global_burst, now)

    def table_size(self) -> int:
        return len(self._per_ip)


def _peer_ip(address) -> str:
    from listen_address import normalize_peer_address
    try:
        return normalize_peer_address(address[0])
    except Exception:
        return ''


def _udp_server_class():
    from gevent.server import DatagramServer

    class _UdpServer(DatagramServer):
        # No SO_REUSEADDR: another socket must not share the port with us.
        reuse_addr = 0

    return _UdpServer


class DnsUpdateServer:
    def __init__(self, app, host: str, port: int, handler=None, limits=ServerLimits(),
                 clock=time.monotonic):
        self._app = app
        self._host = host
        self._port = port
        self._handler = handler
        self._limits = limits
        self._clock = clock
        self._limiter = RateLimiter(limits, clock)
        self._sampler = LogSampler(10.0, clock, logger)
        self._tcp = None
        self._udp = None
        self._tcp_counts = {}
        self._tcp_lock = threading.Lock()
        self._hub = None
        self._stopped = None
        self.bind_errno = None  # errno of the last bind OSError, None otherwise

    @property
    def port(self) -> int:
        return self._port

    @property
    def limiter(self) -> RateLimiter:
        return self._limiter

    # -- lifecycle -----------------------------------------------------------------

    def start(self, quiet: bool = False) -> bool:
        """Bind UDP and TCP on the same port. Call it in the thread that runs the
        gevent hub. Returns False (never raises) when a bind fails. ``quiet`` logs
        a bind error at debug level (for the bind retry)."""
        import gevent
        from gevent.event import Event
        from gevent.pool import Pool
        from gevent.server import StreamServer

        if self._handler is None:
            from services.acme.dns_update.handler import DnsUpdateHandler
            self._handler = DnsUpdateHandler()
        self.bind_errno = None
        try:
            tcp = StreamServer((self._host, self._port), self._handle_tcp,
                               spawn=Pool(self._limits.tcp_pool))
            tcp.start()
            self._tcp = tcp
            port = tcp.address[1]
            udp = _udp_server_class()((self._host, port), self._handle_udp,
                                      spawn=Pool(self._limits.udp_pool))
            udp.start()
            self._udp = udp
        except OSError as exc:
            self.bind_errno = exc.errno
            logger.log(logging.DEBUG if quiet else logging.ERROR,
                       "Cannot start DNS UPDATE listener on %s port %d: %s",
                       self._host, self._port, exc)
            self._close_servers()
            return False
        except Exception as exc:
            logger.warning("DNS UPDATE listener startup failed: %s", type(exc).__name__)
            self._close_servers()
            return False
        self._port = port
        self._hub = gevent.get_hub()
        self._stopped = Event()
        status.set_listening(True, self._port)
        logger.info("DNS UPDATE listener started on %s port %d (UDP and TCP)", self._host, port)
        return True

    def serve_forever(self) -> None:
        """Block (cooperatively) until stop(). For threads that own the hub."""
        if self._stopped is not None:
            self._stopped.wait()

    def _close_servers(self) -> None:
        for srv in (self._udp, self._tcp):
            if srv is not None:
                try:
                    srv.close()
                except Exception:
                    pass
        self._udp = None
        self._tcp = None

    def _stop_now(self) -> None:
        self._close_servers()
        status.set_listening(False)
        if self._stopped is not None:
            self._stopped.set()

    def stop(self) -> None:
        """Stop both servers. Safe to call from another thread."""
        hub = self._hub
        if hub is None:
            self._stop_now()
            return
        import gevent
        if gevent.get_hub() is hub:
            self._stop_now()
            return
        done = threading.Event()

        def run():
            try:
                self._stop_now()
            finally:
                done.set()

        hub.loop.run_callback_threadsafe(run)
        done.wait(5)
        status.set_listening(False)

    # -- UDP -----------------------------------------------------------------------

    def _handle_udp(self, data, address) -> None:
        try:
            ip = _peer_ip(address)
            if not self._limiter.allow(ip):
                self._sampler.note('rate_limited_udp', logging.WARNING, ip)
                return
            with self._app.app_context():
                out = self._handler.handle(data, ip, 'udp')
            if out is not None:
                self._udp.sendto(out, address)
        except Exception as exc:
            self._note_error('udp_error', address, exc)

    def _note_error(self, reason, address, exc) -> None:
        try:
            self._sampler.note(reason, logging.ERROR, _peer_ip(address), type(exc).__name__)
        except Exception:
            pass

    # -- TCP -----------------------------------------------------------------------

    def _acquire_slot(self, ip: str) -> bool:
        ip = _limit_key(ip)
        with self._tcp_lock:
            n = self._tcp_counts.get(ip, 0)
            if n >= self._limits.tcp_per_ip:
                return False
            self._tcp_counts[ip] = n + 1
            return True

    def _release_slot(self, ip: str) -> None:
        ip = _limit_key(ip)
        with self._tcp_lock:
            n = self._tcp_counts.get(ip, 0) - 1
            if n > 0:
                self._tcp_counts[ip] = n
            else:
                self._tcp_counts.pop(ip, None)

    def _recv_exact(self, sock, n: int, deadline: float) -> Optional[bytes]:
        """Read exactly n bytes, in as many segments as needed (RFC 7766 §8).
        None when the peer closed or the deadline passed."""
        buf = bytearray()
        while len(buf) < n:
            remaining = deadline - self._clock()
            if remaining <= 0:
                return None
            sock.settimeout(remaining)
            try:
                chunk = sock.recv(n - len(buf))
            except socket.timeout:
                return None
            if not chunk:
                return None
            buf += chunk
        return bytes(buf)

    def _handle_tcp(self, sock, address) -> None:
        ip = _peer_ip(address)
        if not self._acquire_slot(ip):
            self._sampler.note('tcp_per_ip_cap', logging.WARNING, ip)
            self._close(sock)
            return
        try:
            self._serve_connection(sock, address, ip)
        except (OSError, socket.timeout):
            pass  # the peer closing or resetting is normal
        except Exception as exc:
            self._note_error('tcp_error', address, exc)
        finally:
            self._close(sock)
            self._release_slot(ip)

    @staticmethod
    def _close(sock) -> None:
        try:
            sock.close()
        except Exception:
            pass

    def _serve_connection(self, sock, address, ip: str) -> None:
        lim = self._limits
        started = self._clock()
        lifetime_end = started + lim.tcp_lifetime_s
        last_full = started
        while True:
            now = self._clock()
            if now >= lifetime_end:
                return
            # The idle time runs from the last COMPLETE message, not from the last byte.
            deadline = min(last_full + lim.tcp_idle_s, lifetime_end)
            head = self._recv_exact(sock, 2, deadline)
            if head is None:
                return
            length = int.from_bytes(head, 'big')
            if length == 0 or length > MAX_MESSAGE_SIZE:
                self._sampler.note('tcp_bad_length', logging.INFO, ip)
                return
            data = self._recv_exact(sock, length, deadline)
            if data is None:
                return
            if not self._limiter.allow(ip):
                # Close instead of reading on: a flood on one connection costs nothing more.
                self._sampler.note('rate_limited_tcp', logging.WARNING, ip)
                return
            with self._app.app_context():
                out = self._handler.handle(data, ip, 'tcp')
            if out is None:
                return
            sock.settimeout(lim.tcp_write_s)
            sock.sendall(len(out).to_bytes(2, 'big') + out)
            last_full = self._clock()


def _retry_bind(server: DnsUpdateServer, retry_for: float) -> None:
    """Greenlet body: call start() again with a growing delay until it works, fails
    for another reason than a busy port, or the deadline passes. Never raises."""
    global _server
    try:
        deadline = _clock() + retry_for
        delay = RETRY_FIRST_DELAY
        attempts = 1  # the first start() was attempt 1
        while True:
            _sleep(delay)
            delay = min(delay * 2, RETRY_MAX_DELAY)
            attempts += 1
            if server.start(quiet=True):
                _server = server
                logger.info("DNS UPDATE listener started after %d attempts", attempts)
                return
            if server.bind_errno != errno.EADDRINUSE:
                logger.error("DNS UPDATE listener bind retry stopped: errno %s",
                             server.bind_errno)
                return
            if _clock() >= deadline:
                logger.error("DNS UPDATE port %d still in use after %.0f s, "
                             "the listener is not running", server.port, retry_for)
                return
    except Exception as exc:
        logger.error("DNS UPDATE listener bind retry failed: %s", type(exc).__name__)


def start_dns_update_server(app, retry_for: float = 0.0) -> Optional[DnsUpdateServer]:
    """Start the listener when a port is configured. Never raises.

    When the port is busy and ``retry_for`` > 0, the bind is retried in a background
    greenlet (a reload starts the new worker before the old one lets go of the port).
    The call then returns None at once; the listener is in ``_server`` after a success.
    """
    global _server, _retry
    try:
        with app.app_context():
            port = status.get_dns_update_port()
            host = status.get_dns_update_host()
        if port <= 0:
            return None
        from services.acme.dns_update.handler import DnsUpdateHandler
        with app.app_context():
            handler = DnsUpdateHandler()
        server = DnsUpdateServer(app, host, port, handler)
        # With a retry, a busy port is expected after a reload: one warning, no error.
        if not server.start(quiet=retry_for > 0):
            if server.bind_errno == errno.EADDRINUSE and retry_for > 0:
                import gevent
                logger.warning("DNS UPDATE port %d is in use, a previous worker may still "
                               "hold it; retrying for up to %.0f s", port, retry_for)
                _retry = gevent.spawn(_retry_bind, server, retry_for)
            elif retry_for > 0 and server.bind_errno is not None:
                logger.error("Cannot start DNS UPDATE listener on %s port %d: errno %s",
                             host, port, server.bind_errno)
            return None
        _server = server
        return server
    except Exception as exc:
        logger.warning("DNS UPDATE listener startup failed: %s", type(exc).__name__)
        return None
