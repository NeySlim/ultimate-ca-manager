"""UDP/TCP server of the DNS UPDATE (RFC 2136) listener.

The real gevent servers run on 127.0.0.1 port 0 in their own thread (own hub):
the test process is not monkey-patched, so blocking client calls in the main
thread would starve the hub otherwise. Most tests use a fake handler.
Test names start with an ID: the letter says what is tested (M message, E EDNS,
T transport, S TSIG, U UPDATE, Q query and SOA discovery, R expected values,
K keys, N server, logs and security, F regression of a fixed defect). The
scenarios are in docs/testing/ACME-PROXY-DNS-UPDATE.md.
Test names have the form test_<ID>_<what>_pos / _neg.
"""
import errno
import importlib.util
import logging
import pathlib
import socket
import sys
import threading
import time
import types

import dns.flags
import dns.message
import dns.rcode
import gevent
import pytest

from services.acme.dns_update import server as srv_mod
from services.acme.dns_update import status
from services.acme.dns_update.constants import MAX_MESSAGE_SIZE
from services.acme.dns_update.server import DnsUpdateServer, RateLimiter, ServerLimits

BACKEND = pathlib.Path(__file__).resolve().parent.parent
# Limits that never interfere, unless a test lowers them.
OPEN = dict(global_rate=100000.0, global_burst=100000, per_ip_rate=100000.0, per_ip_burst=100000)


class FakeHandler:
    def __init__(self, reply=lambda wire: b'R' + wire):
        self.calls = []
        self.reply = reply
        self.lock = threading.Lock()

    def handle(self, wire, peer_ip, transport):
        with self.lock:
            self.calls.append((wire, peer_ip, transport))
        return self.reply(wire)


class Running:
    def __init__(self, app, handler, limits, host='127.0.0.1', port=0):
        self.server = DnsUpdateServer(app, host, port, handler, limits)
        self.ok = None
        ready = threading.Event()

        def run():
            self.ok = self.server.start()
            ready.set()
            if self.ok:
                self.server.serve_forever()

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        assert ready.wait(10), 'server thread did not start'

    @property
    def port(self):
        return self.server.port

    def stop(self):
        self.server.stop()


@pytest.fixture
def run(app):
    started = []

    def factory(handler=None, **limits):
        r = Running(app, handler or FakeHandler(), ServerLimits(**{**OPEN, **limits}))
        assert r.ok
        started.append(r)
        return r

    yield factory
    for r in started:
        r.stop()


def tcp(r, timeout=3.0):
    s = socket.create_connection(('127.0.0.1', r.port), timeout=timeout)
    return s


def frame(b):
    return len(b).to_bytes(2, 'big') + b


def read_frame(s):
    """One framed response, or None on EOF/timeout."""
    try:
        head = b''
        while len(head) < 2:
            c = s.recv(2 - len(head))
            if not c:
                return None
            head += c
        n = int.from_bytes(head, 'big')
        body = b''
        while len(body) < n:
            c = s.recv(n - len(body))
            if not c:
                return None
            body += c
        return body
    except (socket.timeout, ConnectionError):
        return None


def closed_by_server(s, wait=3.0):
    s.settimeout(wait)
    try:
        return s.recv(1) == b''
    except socket.timeout:
        return False
    except ConnectionError:
        return True


def udp_ask(r, data, wait=1.0):
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    u.settimeout(wait)
    try:
        u.sendto(data, ('127.0.0.1', r.port))
        return u.recv(65535)
    except socket.timeout:
        return None
    finally:
        u.close()


# -- UDP ---------------------------------------------------------------------------

def test_udp_datagram_is_answered_pos(run):
    h = FakeHandler()
    r = run(h)
    assert udp_ask(r, b'hello') == b'Rhello'
    assert h.calls == [(b'hello', '127.0.0.1', 'udp')]


def test_udp_handler_none_sends_nothing_neg(run):
    h = FakeHandler(lambda w: None)
    r = run(h)
    assert udp_ask(r, b'hello', wait=0.5) is None
    assert len(h.calls) == 1


def test_udp_oversize_datagram_reaches_the_handler_in_full_neg(run):
    h = FakeHandler(lambda w: None)
    r = run(h)
    big = b'x' * (MAX_MESSAGE_SIZE + 1)
    assert udp_ask(r, big, wait=0.5) is None
    deadline = time.time() + 2
    while not h.calls and time.time() < deadline:
        time.sleep(0.02)
    assert h.calls and h.calls[0][0] == big


# -- T3 ----------------------------------------------------------------------------

def test_T3_two_pipelined_messages_two_responses_in_order_pos(run):
    r = run()
    s = tcp(r)
    s.sendall(frame(b'one') + frame(b'two'))
    assert read_frame(s) == b'Rone'
    assert read_frame(s) == b'Rtwo'
    s.close()


def test_T3_length_and_body_in_separate_segments_pos(run):
    r = run(tcp_idle_s=2.0)
    s = tcp(r)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    msg = frame(b'segmented')
    s.sendall(msg[:2])
    time.sleep(0.3)
    s.sendall(msg[2:5])
    time.sleep(0.3)
    s.sendall(msg[5:])
    assert read_frame(s) == b'Rsegmented'
    s.close()


def test_T3_length_zero_closes_without_response_neg(run):
    h = FakeHandler()
    r = run(h)
    s = tcp(r)
    s.sendall(b'\x00\x00')
    assert closed_by_server(s)
    assert h.calls == []
    s.close()


def test_T3_length_over_max_closes_without_reading_body_neg(run):
    h = FakeHandler()
    r = run(h)
    s = tcp(r)
    s.sendall((MAX_MESSAGE_SIZE + 1).to_bytes(2, 'big') + b'x' * 100)
    assert closed_by_server(s)
    assert h.calls == []
    s.close()


def test_T3_length_max_is_accepted_pos(run):
    h = FakeHandler()
    r = run(h)
    s = tcp(r)
    s.sendall(frame(b'y' * MAX_MESSAGE_SIZE))
    assert read_frame(s) == b'R' + b'y' * MAX_MESSAGE_SIZE
    s.close()


def test_T3_handler_none_closes_the_connection_neg(run):
    r = run(FakeHandler(lambda w: None))
    s = tcp(r)
    s.sendall(frame(b'q'))
    assert closed_by_server(s)
    s.close()


# -- T5 ----------------------------------------------------------------------------

def test_T5_messages_within_idle_keep_the_connection_pos(run):
    r = run(tcp_idle_s=0.5, tcp_lifetime_s=30.0)
    s = tcp(r)
    end = time.time() + 2.0
    n = 0
    while time.time() < end:
        s.sendall(frame(b'k%d' % n))
        assert read_frame(s) == b'Rk%d' % n
        n += 1
        time.sleep(0.2)
    assert n >= 8
    s.close()


def test_T5_half_message_then_silence_closes_neg(run):
    h = FakeHandler()
    r = run(h, tcp_idle_s=0.5)
    s = tcp(r)
    s.sendall(b'\x00\x0a' + b'half')
    t0 = time.time()
    assert closed_by_server(s, wait=3.0)
    assert time.time() - t0 < 2.0
    assert h.calls == []
    s.close()


def test_T5_slow_drip_does_not_reset_the_idle_timer_neg(run):
    r = run(tcp_idle_s=0.6)
    s = tcp(r)
    s.sendall(b'\x00\x32')
    t0 = time.time()
    try:
        for _ in range(20):
            s.sendall(b'a')
            time.sleep(0.2)
    except OSError:
        pass
    assert closed_by_server(s, wait=2.0)
    assert time.time() - t0 < 2.5
    s.close()


def test_T5_connection_closed_after_lifetime_even_if_active_neg(run):
    r = run(tcp_idle_s=0.5, tcp_lifetime_s=1.0)
    s = tcp(r)
    t0 = time.time()
    got_close = False
    while time.time() - t0 < 3.0:
        try:
            s.sendall(frame(b'a'))
        except OSError:
            got_close = True
            break
        if read_frame(s) is None:
            got_close = True
            break
        time.sleep(0.1)
    assert got_close
    assert 0.8 < time.time() - t0 < 2.5
    s.close()


# -- N3 ----------------------------------------------------------------------------

def test_N3_port_in_use_start_returns_false_neg(app):
    status.set_listening(False)
    blocker = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    blocker.bind(('127.0.0.1', 0))
    port = blocker.getsockname()[1]
    try:
        r = Running(app, FakeHandler(), ServerLimits(), port=port)
        assert r.ok is False
        assert status.is_listening() is False
    finally:
        blocker.close()


def test_N3_tcp_port_in_use_start_returns_false_neg(app):
    status.set_listening(False)
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(('127.0.0.1', 0))
    blocker.listen(1)
    try:
        r = Running(app, FakeHandler(), ServerLimits(), port=blocker.getsockname()[1])
        assert r.ok is False
        assert status.is_listening() is False
    finally:
        blocker.close()


def test_N3_free_port_listens_and_stop_clears_pos(app):
    r = Running(app, FakeHandler(), ServerLimits())
    assert r.ok is True
    assert status.is_listening() is True
    assert r.port > 0
    assert status.listening_port() == r.port  # D4a
    assert udp_ask(r, b'a') == b'Ra'
    r.stop()
    assert status.is_listening() is False
    assert status.listening_port() == 0
    with pytest.raises(OSError):
        socket.create_connection(('127.0.0.1', r.port), timeout=1)


# -- N1: start and bind host -----------------------------------------------------------------------

def test_N1_port_zero_disables_the_listener_neg(app, monkeypatch):
    monkeypatch.setenv('UCM_DNS_UPDATE_PORT', '0')
    monkeypatch.setattr(srv_mod, 'DnsUpdateServer',
                        lambda *a, **k: pytest.fail('server must not be created'))
    assert srv_mod.start_dns_update_server(app) is None


def _free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _start_via_env(app, port):
    holder, ready = {}, threading.Event()

    def go():
        holder['srv'] = srv_mod.start_dns_update_server(app)
        ready.set()
        if holder['srv']:
            holder['srv'].serve_forever()

    threading.Thread(target=go, daemon=True).start()
    assert ready.wait(10)
    return holder['srv']


def test_N1_env_port_starts_the_listener_pos(app, monkeypatch):
    port = _free_port()
    monkeypatch.setenv('UCM_DNS_UPDATE_PORT', str(port))
    monkeypatch.setenv('UCM_DNS_UPDATE_HOST', '127.0.0.1')
    server = _start_via_env(app, port)
    try:
        assert server is not None and server.port == port
        assert status.is_listening()
        s = tcp(server)
        s.close()
    finally:
        if server:
            server.stop()


def test_F8_listener_binds_the_configured_host_pos(app, monkeypatch):
    port = _free_port()
    monkeypatch.setenv('UCM_DNS_UPDATE_PORT', str(port))
    monkeypatch.setenv('UCM_DNS_UPDATE_HOST', '127.0.0.1')
    server = _start_via_env(app, port)
    try:
        assert server._host == '127.0.0.1'
        assert server._tcp.address[0] == '127.0.0.1'
        assert server._udp.address[0] == '127.0.0.1'
    finally:
        server.stop()


def test_F8_default_host_is_the_http_host_neg(app, monkeypatch):
    port = _free_port()
    monkeypatch.setenv('UCM_DNS_UPDATE_PORT', str(port))
    monkeypatch.delenv('UCM_DNS_UPDATE_HOST', raising=False)
    monkeypatch.setenv('HOST', '127.0.0.1')
    server = _start_via_env(app, port)
    try:
        assert server._host == '127.0.0.1'
    finally:
        server.stop()
    monkeypatch.delenv('HOST')
    assert status.get_dns_update_host() == '0.0.0.0'


# -- N4 ----------------------------------------------------------------------------

def test_N4_fast_udp_traffic_over_the_global_limit_is_dropped_neg(run):
    h = FakeHandler()
    r = run(h, global_rate=5.0, global_burst=5)
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    u.settimeout(0.5)
    for i in range(50):
        u.sendto(b'q%d' % i, ('127.0.0.1', r.port))
    answered = 0
    try:
        while True:
            u.recv(100)
            answered += 1
    except socket.timeout:
        pass
    u.close()
    assert 5 <= answered <= 10
    assert len(h.calls) == answered


def test_N4_slow_traffic_under_the_limit_is_answered_pos(run):
    r = run(global_rate=5.0, global_burst=5)
    for i in range(8):
        assert udp_ask(r, b'q%d' % i) == b'Rq%d' % i
        time.sleep(0.25)


def test_N4_per_ip_limit_drops_one_source_neg(run):
    h = FakeHandler()
    r = run(h, per_ip_rate=1.0, per_ip_burst=3)
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    u.settimeout(0.5)
    for i in range(20):
        u.sendto(b'q', ('127.0.0.1', r.port))
    n = 0
    try:
        while True:
            u.recv(100)
            n += 1
    except socket.timeout:
        pass
    u.close()
    assert 3 <= n <= 5


def test_N4_tcp_message_over_the_limit_gets_no_response_neg(run):
    h = FakeHandler()
    r = run(h, per_ip_rate=0.1, per_ip_burst=2)
    s = tcp(r)
    s.sendall(frame(b'a') + frame(b'b') + frame(b'c'))
    assert read_frame(s) == b'Ra'
    assert read_frame(s) == b'Rb'
    assert read_frame(s) is None
    assert len(h.calls) == 2
    s.close()


def test_N4_per_ip_table_is_bounded_neg():
    now = [0.0]
    limiter = RateLimiter(ServerLimits(per_ip_table=50, **{k: v for k, v in OPEN.items()}),
                          clock=lambda: now[0])
    for i in range(10000):
        limiter.allow('10.%d.%d.%d' % (i >> 16 & 255, i >> 8 & 255, i & 255))
        assert limiter.table_size() <= 50
    assert limiter.table_size() == 50


def test_N4_limiter_allows_in_limit_traffic_pos():
    now = [0.0]
    limiter = RateLimiter(ServerLimits(global_rate=10.0, global_burst=2,
                                       per_ip_rate=10.0, per_ip_burst=2),
                          clock=lambda: now[0])
    assert limiter.allow('a') and limiter.allow('a')
    assert not limiter.allow('a')
    now[0] += 0.1
    assert limiter.allow('a')


def _limiter(burst=2):
    now = [0.0]
    return RateLimiter(ServerLimits(global_rate=100000.0, global_burst=100000,
                                    per_ip_rate=0.001, per_ip_burst=burst),
                       clock=lambda: now[0])


def test_A5_limit_key_ipv6_is_the_64_network_pos():
    assert srv_mod._limit_key('2001:db8:1:2:aaaa::1') == '2001:db8:1:2::/64'
    assert srv_mod._limit_key('2001:db8:1:2:ffff:ffff:ffff:ffff') == '2001:db8:1:2::/64'
    assert srv_mod._limit_key('2001:db8:1:3::1') == '2001:db8:1:3::/64'


def test_A5_limit_key_ipv4_and_unparsable_are_unchanged_neg():
    assert srv_mod._limit_key('192.0.2.7') == '192.0.2.7'
    assert srv_mod._limit_key('') == ''
    assert srv_mod._limit_key('not-an-ip') == 'not-an-ip'


def test_A5_addresses_in_one_64_share_one_bucket_pos():
    limiter = _limiter(burst=2)
    assert limiter.allow('2001:db8:1:2::1') and limiter.allow('2001:db8:1:2::2')
    assert not limiter.allow('2001:db8:1:2::3')  # the burst of the /64 is used up
    assert limiter.table_size() == 1


def test_A5_addresses_in_different_64s_have_separate_buckets_neg():
    limiter = _limiter(burst=1)
    assert limiter.allow('2001:db8:1:2::1')
    assert not limiter.allow('2001:db8:1:2::1')
    assert limiter.allow('2001:db8:1:3::1')  # another /64
    assert limiter.allow('192.0.2.1') and limiter.allow('192.0.2.2')  # IPv4 per address
    assert not limiter.allow('192.0.2.1')


def test_A5_tcp_per_ip_cap_counts_one_64_together_pos():
    s = DnsUpdateServer(None, '127.0.0.1', 0, FakeHandler(), ServerLimits(tcp_per_ip=2))
    assert s._acquire_slot('2001:db8:1:2::1') and s._acquire_slot('2001:db8:1:2::2')
    assert not s._acquire_slot('2001:db8:1:2::3')
    s._release_slot('2001:db8:1:2::2')
    assert s._acquire_slot('2001:db8:1:2::9')  # a slot of the /64 was freed
    assert len(s._tcp_counts) == 1


def test_A5_tcp_per_ip_cap_is_per_64_and_per_ipv4_address_neg():
    s = DnsUpdateServer(None, '127.0.0.1', 0, FakeHandler(), ServerLimits(tcp_per_ip=1))
    assert s._acquire_slot('2001:db8:1:2::1')
    assert s._acquire_slot('2001:db8:1:3::1')  # another /64
    assert s._acquire_slot('192.0.2.1') and s._acquire_slot('192.0.2.2')
    assert not s._acquire_slot('192.0.2.1')
    for ip in ('2001:db8:1:2::1', '2001:db8:1:3::1', '192.0.2.1', '192.0.2.2'):
        s._release_slot(ip)
    assert s._tcp_counts == {}


def test_A5_default_tcp_pool_needs_16_sources_pos_and_neg():
    lim = ServerLimits()
    assert lim.tcp_pool == 128 and lim.tcp_per_ip == 8
    assert lim.tcp_pool // lim.tcp_per_ip == 16
    assert ServerLimits(tcp_pool=32).tcp_pool == 32  # an explicit value is kept


def test_N4_tcp_per_ip_cap_closes_the_extra_connection_neg(run):
    r = run(tcp_per_ip=3, tcp_idle_s=5.0)
    held = [tcp(r) for _ in range(3)]
    time.sleep(0.2)
    extra = tcp(r)
    assert closed_by_server(extra, wait=2.0)
    extra.close()
    for s in held:
        s.sendall(frame(b'x'))
        assert read_frame(s) == b'Rx'
        s.close()


def test_N4_tcp_up_to_the_cap_all_work_pos(run):
    r = run(tcp_per_ip=3, tcp_idle_s=5.0)
    conns = [tcp(r) for _ in range(3)]
    for s in conns:
        s.sendall(frame(b'x'))
    for s in conns:
        assert read_frame(s) == b'Rx'
        s.close()
    time.sleep(0.2)
    again = tcp(r)  # slots were released
    again.sendall(frame(b'y'))
    assert read_frame(again) == b'Ry'
    again.close()


def test_N4_pool_bounds_concurrent_handlers_pos(run):
    active = {'now': 0, 'max': 0}
    lock = threading.Lock()

    def slow(wire):
        # runs in a greenlet of the server thread: sleeping here yields to the hub
        import gevent
        with lock:
            active['now'] += 1
            active['max'] = max(active['max'], active['now'])
        gevent.sleep(0.1)
        with lock:
            active['now'] -= 1
        return b'ok'

    r = run(FakeHandler(slow), udp_pool=2)
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    u.settimeout(3)
    for i in range(6):
        u.sendto(b'q', ('127.0.0.1', r.port))
    got = 0
    try:
        while got < 6:
            u.recv(100)
            got += 1
    except socket.timeout:
        pass
    u.close()
    assert got == 6
    assert active['max'] <= 2


# -- N10 ---------------------------------------------------------------------------

def test_N10_handler_exception_keeps_serving_udp_neg(run, caplog):
    def boom(wire):
        if wire == b'boom':
            raise RuntimeError('secret-detail')
        return b'ok'

    r = run(FakeHandler(boom))
    with caplog.at_level(logging.DEBUG):
        assert udp_ask(r, b'boom', wait=0.5) is None
        assert udp_ask(r, b'fine') == b'ok'
    assert 'RuntimeError' in caplog.text
    assert 'secret-detail' not in caplog.text  # type only, never the message


def test_N10_handler_exception_keeps_serving_tcp_neg(run):
    def boom(wire):
        if wire == b'boom':
            raise RuntimeError('x')
        return b'ok'

    r = run(FakeHandler(boom))
    s = tcp(r)
    s.sendall(frame(b'boom'))
    assert closed_by_server(s)
    s.close()
    s2 = tcp(r)
    s2.sendall(frame(b'fine'))
    assert read_frame(s2) == b'ok'
    s2.close()


# -- real handler smoke ------------------------------------------------------------

def test_real_handler_refuses_unsigned_soa_over_udp_and_tcp_pos(app):
    from services.acme.dns_update.handler import DnsUpdateHandler
    with app.app_context():
        handler = DnsUpdateHandler()
    r = Running(app, handler, ServerLimits(**OPEN))
    assert r.ok
    try:
        q = dns.message.make_query('nothing.invalid.', 'SOA').to_wire()
        out = udp_ask(r, q, wait=3.0)
        assert out is not None
        assert dns.message.from_wire(out).rcode() == dns.rcode.REFUSED
        s = tcp(r, timeout=5)
        s.sendall(frame(q))
        body = read_frame(s)
        s.close()
        assert body is not None
        assert dns.message.from_wire(body).rcode() == dns.rcode.REFUSED
    finally:
        r.stop()


# -- TSIG on one TCP connection (RFC 8945 §4.3.1, §5.3.1; miekg/dns#1733) ----------------
#
# The prior MAC chain of §5.3.1 applies only to the messages of ONE multi-message
# response. Independent requests on the same TCP connection are each signed and
# verified as a first message: no state carries over from one request to the next.


def _tsig_handler():
    import dns.name
    import dns.tsig
    from services.acme.dns_update.handler import DnsUpdateHandler
    from services.acme.dns_update.keys import KeyScope
    from services.acme.dns_update.records import ActiveRecord, ActiveSnapshot, expected_value
    from services.acme.dns_update.tsig import TsigKeyMaterial

    key = dns.tsig.Key(dns.name.from_text('tcp-chain.example.'), bytes(range(7, 39)), dns.tsig.HMAC_SHA256)
    value = expected_value('tok', 'thumb')
    record = '_acme-challenge.app.example.com.'
    row = ActiveRecord(1, 1, record, value, 'example.com.', 1, 'acct-1')
    snap = ActiveSnapshot({record: (row,)}, frozenset({'example.com.'}), (row,))
    confirmed = []

    class Keys:
        def lookup(self, name):
            return TsigKeyMaterial(1, key.name, key.algorithm, key.secret) if name == key.name else None

        def scope(self, key_id):
            return KeyScope(1, False, None)

        def touch(self, key_id, now):
            pass

    class Zones:
        def is_authoritative(self, zname):
            return zname == dns.name.from_text('example.com.')

    class Audit:
        def audit_limited(self, **kw):
            return True

        def audit_authenticated(self, **kw):
            return True

    handler = DnsUpdateHandler(key_store=Keys(), zone_index=Zones(), audit=Audit(),
                               snapshot_fn=lambda *a: snap,
                               mark_confirmed_fn=lambda ids, now: confirmed.append(list(ids)))
    return handler, key, record, value, confirmed


def _update(key, record, value, request_mac=b''):
    import dns.update
    m = dns.update.UpdateMessage('example.com.')
    m.add(record, 60, 'TXT', f'"{value}"')
    m.use_tsig({key.name: key}, key.name, algorithm=key.algorithm)
    # A request has no request MAC (RFC 8945 §4.3.1). A non-empty value here
    # signs the request like a client that chains the previous response MAC.
    m.request_mac = request_mac
    wire = m.to_wire()
    return m, wire


def test_T3_independent_signed_updates_on_one_connection_pos(app):
    handler, key, record, value, confirmed = _tsig_handler()
    r = Running(app, handler, ServerLimits(**OPEN))
    assert r.ok
    try:
        s = tcp(r, timeout=5)
        for _ in range(3):
            req, wire = _update(key, record, value)
            s.sendall(frame(wire))
            body = read_frame(s)
            assert body is not None
            # dnspython as the client verifies the response MAC with this request's MAC.
            resp = dns.message.from_wire(body, keyring={key.name: key}, request_mac=req.mac)
            assert resp.had_tsig
            assert resp.rcode() == dns.rcode.NOERROR
        s.close()
        assert confirmed == [[1], [1], [1]]
    finally:
        r.stop()


def test_T3_request_signed_with_the_prior_response_mac_is_badsig_neg(app):
    handler, key, record, value, confirmed = _tsig_handler()
    r = Running(app, handler, ServerLimits(**OPEN))
    assert r.ok
    try:
        s = tcp(r, timeout=5)
        req1, wire1 = _update(key, record, value)
        s.sendall(frame(wire1))
        resp1 = dns.message.from_wire(read_frame(s), keyring={key.name: key}, request_mac=req1.mac)
        assert resp1.rcode() == dns.rcode.NOERROR

        # Second request chained to the first response MAC: the server must not
        # accept it (BADSIG, unsigned error, RFC 8945 §5.3.2) and must not confirm.
        _req2, wire2 = _update(key, record, value, request_mac=resp1.mac)
        s.sendall(frame(wire2))
        resp2 = dns.message.from_wire(read_frame(s), keyring=False)
        assert resp2.rcode() == dns.rcode.NOTAUTH
        assert resp2.tsig[0].error == dns.rcode.BADSIG
        assert resp2.tsig[0].mac == b''

        # The connection keeps no TSIG state: the next independent request works.
        req3, wire3 = _update(key, record, value)
        s.sendall(frame(wire3))
        resp3 = dns.message.from_wire(read_frame(s), keyring={key.name: key}, request_mac=req3.mac)
        assert resp3.rcode() == dns.rcode.NOERROR
        s.close()
        assert confirmed == [[1], [1]]
    finally:
        r.stop()


# -- bind retry --------------------------------------------------------------------

class FakeServer:
    """Stands in for DnsUpdateServer: start() answers from a list of errnos
    (None = success)."""
    results = []
    attempts = 0

    def __init__(self, app, host, port, handler=None, limits=None):
        self.port = port
        self.bind_errno = None

    def start(self, quiet=False):
        cls = type(self)
        cls.attempts += 1
        err = cls.results[min(cls.attempts, len(cls.results)) - 1]
        self.bind_errno = err
        return err is None


@pytest.fixture
def retry(app, monkeypatch):
    """start_dns_update_server with a fake server, a fake clock and no real sleep."""
    clock = {'now': 1000.0}
    sleeps = []

    def fake_sleep(seconds):
        sleeps.append(seconds)
        clock['now'] += seconds
        gevent.sleep(0)

    class Fake(FakeServer):
        results = []
        attempts = 0

    monkeypatch.setenv('UCM_DNS_UPDATE_PORT', '5353')
    monkeypatch.setattr(srv_mod, 'DnsUpdateServer', Fake)
    monkeypatch.setattr(srv_mod, '_sleep', fake_sleep)
    monkeypatch.setattr(srv_mod, '_clock', lambda: clock['now'])
    monkeypatch.setattr(srv_mod, '_server', None)
    monkeypatch.setattr(srv_mod, '_retry', None)

    def go(results, retry_for):
        Fake.results = results
        result = srv_mod.start_dns_update_server(app, retry_for=retry_for)
        if srv_mod._retry is not None:
            gevent.joinall([srv_mod._retry], timeout=5)
        return result

    go.cls = Fake
    go.sleeps = sleeps
    return go


def test_retry_busy_port_then_success_starts_the_listener_pos(retry, caplog):
    caplog.set_level(logging.INFO, logger=srv_mod.logger.name)
    busy = errno.EADDRINUSE
    # The call returns at once with None: the greenlet does the retrying.
    assert retry([busy, busy, None], retry_for=35) is None
    assert retry.cls.attempts == 3
    assert isinstance(srv_mod._server, retry.cls)
    assert retry.sleeps == [0.25, 0.5]
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and 'in use' in warnings[0].getMessage()
    assert any('after 3 attempts' in r.getMessage() for r in caplog.records)


def test_retry_does_not_block_the_caller_pos(retry, app):
    retry.cls.results = [errno.EADDRINUSE, None]
    assert srv_mod.start_dns_update_server(app, retry_for=35) is None
    assert retry.cls.attempts == 1 and srv_mod._server is None
    assert srv_mod._retry is not None and not srv_mod._retry.dead
    gevent.joinall([srv_mod._retry], timeout=5)
    assert retry.cls.attempts == 2 and srv_mod._server is not None


def test_retry_other_errno_stops_at_once_neg(retry, caplog):
    assert retry([errno.EACCES], retry_for=35) is None
    assert retry.cls.attempts == 1
    assert retry.sleeps == []
    assert srv_mod._retry is None and srv_mod._server is None
    # The first start was quiet (a retry was possible): the error is logged here.
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1 and str(errno.EACCES) in errors[0].getMessage()


def test_retry_other_errno_after_a_busy_port_stops_neg(retry, caplog):
    assert retry([errno.EADDRINUSE, errno.EACCES], retry_for=35) is None
    assert retry.cls.attempts == 2
    assert srv_mod._server is None
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_retry_for_zero_tries_once_neg(retry):
    assert retry([errno.EADDRINUSE], retry_for=0) is None
    assert retry.cls.attempts == 1
    assert retry.sleeps == [] and srv_mod._retry is None


def test_retry_first_start_works_without_a_retry_pos(retry):
    server = retry([None], retry_for=35)
    assert server is not None and srv_mod._server is server
    assert retry.cls.attempts == 1 and srv_mod._retry is None


def test_retry_gives_up_at_the_deadline_neg(retry, caplog):
    assert retry([errno.EADDRINUSE], retry_for=10) is None
    assert srv_mod._server is None
    # 0.25 + 0.5 + 1 + 2 + 4 = 7.75 s, then 4 s steps: the deadline falls after 3 more.
    assert retry.sleeps == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0]
    assert retry.cls.attempts == 7
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1 and 'still in use' in errors[0].getMessage()


def test_retry_exception_in_start_is_caught_neg(retry, caplog):
    class Boom(retry.cls):
        def start(self, quiet=False):
            if type(self).attempts:
                raise RuntimeError('secret detail')
            type(self).attempts += 1
            self.bind_errno = errno.EADDRINUSE
            return False

    srv_mod.DnsUpdateServer = Boom  # restored by the retry fixture's monkeypatch
    assert retry([], retry_for=35) is None
    assert srv_mod._server is None
    assert 'secret detail' not in caplog.text
    assert 'RuntimeError' in caplog.text


def test_bind_errno_is_kept_on_a_busy_port_pos(app):
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(('127.0.0.1', 0))
    blocker.listen(1)
    try:
        r = Running(app, FakeHandler(), ServerLimits(), port=blocker.getsockname()[1])
        assert r.ok is False
        assert r.server.bind_errno == errno.EADDRINUSE
    finally:
        blocker.close()


def test_bind_errno_is_none_after_a_success_neg(app):
    r = Running(app, FakeHandler(), ServerLimits())
    try:
        assert r.ok is True
        assert r.server.bind_errno is None
    finally:
        r.stop()


def test_retry_real_sockets_listener_starts_after_the_port_is_freed_pos(app, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG, logger=srv_mod.logger.name)
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(('127.0.0.1', 0))
    blocker.listen(1)
    port = blocker.getsockname()[1]
    monkeypatch.setenv('UCM_DNS_UPDATE_PORT', str(port))
    monkeypatch.setenv('UCM_DNS_UPDATE_HOST', '127.0.0.1')
    monkeypatch.setattr(srv_mod, '_server', None)
    monkeypatch.setattr(srv_mod, '_retry', None)
    done = threading.Event()
    result = {}

    def go():
        # Own thread, own hub: the retry greenlet runs while this thread waits.
        result['first'] = srv_mod.start_dns_update_server(app, retry_for=8)
        if srv_mod._retry is not None:
            gevent.wait([srv_mod._retry])
        result['server'] = srv_mod._server
        done.set()
        if result['server'] is not None:
            result['server'].serve_forever()

    threading.Thread(target=go, daemon=True).start()
    threading.Timer(0.5, blocker.close).start()
    try:
        assert done.wait(10)
        assert result['first'] is None
        server = result['server']
        assert server is not None and server.port == port
        s = socket.create_connection(('127.0.0.1', port), timeout=2)
        s.close()
        # A busy port after a reload is expected: a warning, never an error.
        assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert [r for r in caplog.records if r.levelno == logging.WARNING]
    finally:
        blocker.close()
        if result.get('server'):
            result['server'].stop()


# -- startup wiring ----------------------------------------------------------------

@pytest.fixture
def gunicorn_conf(app, monkeypatch):
    """gunicorn_config.py loaded without monkey patching this process. Returns
    (module, calls): start_* calls of post_worker_init in order."""
    import gevent.monkey
    import protocol_http_server

    monkeypatch.setattr(gevent.monkey, 'patch_all', lambda *a, **k: None)
    spec = importlib.util.spec_from_file_location('_ucm_gunicorn_config_test',
                                                  BACKEND / 'gunicorn_config.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    wsgi = types.ModuleType('wsgi')
    wsgi.app = app
    monkeypatch.setitem(sys.modules, 'wsgi', wsgi)
    # post_worker_init replaces the handle_error of the hub: use a stand-in hub
    monkeypatch.setattr(gevent, 'get_hub', lambda: types.SimpleNamespace(handle_error=None))
    calls = []
    monkeypatch.setattr(protocol_http_server, 'start_http_protocol_server',
                        lambda a, **kw: calls.append(('http', a, kw)))
    monkeypatch.setattr(srv_mod, 'start_dns_update_server',
                        lambda a, **kw: calls.append(('dns', a, kw)))
    return module, calls


def _worker(graceful_timeout=30):
    cfg = types.SimpleNamespace(graceful_timeout=graceful_timeout)
    return types.SimpleNamespace(cfg=cfg, log=logging.getLogger('test.worker'))


def test_startup_gunicorn_starts_the_dns_update_listener_with_a_retry_pos(gunicorn_conf, app):
    module, calls = gunicorn_conf
    module.post_worker_init(_worker(30))
    assert [c[0] for c in calls] == ['http', 'dns']
    assert calls[1][1] is app
    assert calls[1][2] == {'retry_for': 35.0}


def test_startup_gunicorn_retry_follows_graceful_timeout_pos(gunicorn_conf):
    module, calls = gunicorn_conf
    module.post_worker_init(_worker(60))
    assert calls[1][2] == {'retry_for': 65.0}


def test_startup_gunicorn_dns_update_starts_when_the_http_server_fails_neg(gunicorn_conf, monkeypatch):
    import protocol_http_server
    module, calls = gunicorn_conf

    def boom(app, **kw):
        raise RuntimeError('http down')

    monkeypatch.setattr(protocol_http_server, 'start_http_protocol_server', boom)
    module.post_worker_init(_worker())
    assert [c[0] for c in calls] == ['dns']


def test_startup_gunicorn_dns_update_failure_does_not_raise_neg(gunicorn_conf, monkeypatch):
    module, calls = gunicorn_conf

    def boom(app, **kw):
        raise RuntimeError('dns down')

    monkeypatch.setattr(srv_mod, 'start_dns_update_server', boom)
    module.post_worker_init(_worker())
    assert [c[0] for c in calls] == ['http']
