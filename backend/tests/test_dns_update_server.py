"""UDP/TCP server of the DNS UPDATE (RFC 2136) listener.

The real gevent servers run on 127.0.0.1 port 0 in their own thread (own hub):
the test process is not monkey-patched, so blocking client calls in the main
thread would starve the hub otherwise. Most tests use a fake handler. Test
names carry the invariant ID of the plan (section 4): test_<ID>_<what>_pos / _neg.
"""
import ast
import logging
import pathlib
import socket
import threading
import time

import dns.flags
import dns.message
import dns.rcode
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
    assert udp_ask(r, b'a') == b'Ra'
    r.stop()
    assert status.is_listening() is False
    with pytest.raises(OSError):
        socket.create_connection(('127.0.0.1', r.port), timeout=1)


# -- N1 / F8 -----------------------------------------------------------------------

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
    snap = ActiveSnapshot({record: (row,)}, frozenset({'example.com.'}))
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


# -- startup wiring ----------------------------------------------------------------

def _post_worker_init():
    tree = ast.parse((BACKEND / 'gunicorn_config.py').read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == 'post_worker_init':
            return node
    pytest.fail('post_worker_init not found')


def _imports_and_calls_in_try(fn, name):
    for node in ast.walk(fn):
        if isinstance(node, ast.Try):
            body = ast.Module(body=node.body, type_ignores=[])
            calls = any(isinstance(n, ast.Call) and getattr(n.func, 'id', None) == name
                        for n in ast.walk(body))
            if calls:
                return True
    return False


def test_startup_gunicorn_starts_the_dns_update_listener_in_a_try_pos():
    assert _imports_and_calls_in_try(_post_worker_init(), 'start_dns_update_server')


def test_startup_gunicorn_still_starts_the_http_protocol_server_neg():
    assert _imports_and_calls_in_try(_post_worker_init(), 'start_http_protocol_server')
