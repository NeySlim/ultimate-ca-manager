"""Protocol handler of the DNS UPDATE (RFC 2136) + TSIG (RFC 8945) listener.

Requests are built with dnspython as an independent client; responses are
parsed with dnspython, and the TSIG of every signed response is verified by
dnspython as a client. The server side (key store, zone index, snapshot, audit)
is replaced by fakes in the unit tests and is real in the integration tests.
Test names carry the invariant ID of the plan (section 4): test_<ID>_<what>_pos
and _neg. The negative test changes exactly one thing and checks that there
is no side effect.
"""
import base64
import io
import logging
import random
import socket
import struct
import threading
from datetime import datetime, timedelta, timezone
from unittest import mock

import dns.edns
import dns.flags
import dns.message
import dns.name
import dns.opcode
import dns.rcode
import dns.rdataclass
import dns.rdatatype
import dns.rdtypes.ANY.TSIG
import dns.rrset
import dns.tsig
import dns.update
import pytest

from services.acme.dns_update import handler as handler_mod
from services.acme.dns_update.constants import MAX_FUDGE, REPLAY_TTL_S, SOA_TIMERS
from services.acme.dns_update.handler import DnsUpdateHandler, LogSampler, ReplayCache
from services.acme.dns_update.keys import KeyScope
from services.acme.dns_update.records import ActiveRecord, ActiveSnapshot
from services.acme.dns_update.tsig import TsigKeyMaterial, tsig_start_offset

NOW = 1_700_000_000
NOW_DT = datetime.fromtimestamp(NOW, tz=timezone.utc).replace(tzinfo=None)
PEER = "192.0.2.7"
SHA256 = dns.tsig.HMAC_SHA256
SECRET = bytes(range(1, 33))
IN = dns.rdataclass.IN

ZONE = "example.com."
RECORD1 = "_acme-challenge.app.example.com."
RECORD2 = "_acme-challenge.other.example.com."
VALUE1 = "Qm9ndXNWYWx1ZUZvclRlc3RpbmdPbmx5MDEyMzQ1Njc"
VALUE2 = "T3RoZXJCb2d1c1ZhbHVlRm9yVGVzdGluZ09ubHkwMTI"

# Everything that must never appear in a log line (N11).
SECRETS_SEEN = {SECRET.hex(), base64.b64encode(SECRET).decode(), SECRET.decode("latin-1")}
VALUES_SEEN = {VALUE1, VALUE2}
MACS_SEEN = set()
LOGGED = []


def _key(name):
    return dns.tsig.Key(dns.name.from_text(name), SECRET, SHA256)


KEY = _key("k1.example.")  # proxy account 1
KEY2 = _key("k2.example.")  # proxy account 2
KEY3 = _key("k3.example.")  # proxy account 3, no rows
KEYE = _key("keab.example.")  # proxy account 1, bound to ACME account acct-9
KEYU = _key("unknown.example.")  # not in the store

ROW1 = ActiveRecord(1, 11, RECORD1, VALUE1, ZONE, 1, "acct-1")
ROW2 = ActiveRecord(2, 12, RECORD2, VALUE2, ZONE, 2, "acct-2")


def snapshot_of(*rows, closed=()):
    """rows are active (by_name and soa_rows); closed rows are visible to SOA discovery only."""
    by_name = {}
    for r in rows:
        by_name.setdefault(r.record_name, []).append(r)
    soa_rows = tuple(rows) + tuple(closed)
    return ActiveSnapshot({k: tuple(v) for k, v in by_name.items()},
                          frozenset(r.zone_name for r in soa_rows), soa_rows)


# --- fakes --------------------------------------------------------------------

class FakeKeys:
    def __init__(self):
        self.materials = {}
        self.scopes = {}
        self.touched = []
        self.calls = []
        for i, (k, scope) in enumerate((
                (KEY, KeyScope(1, False, None)),
                (KEY2, KeyScope(2, False, None)),
                (KEY3, KeyScope(3, False, None)),
                (KEYE, KeyScope(1, True, "acct-9"))), start=1):
            self.materials[k.name] = TsigKeyMaterial(i, k.name, SHA256, SECRET)
            self.scopes[i] = scope

    def lookup(self, name):
        self.calls.append("lookup")
        return self.materials.get(name)

    def scope(self, key_id):
        self.calls.append("scope")
        return self.scopes.get(key_id)

    def touch(self, key_id, now):
        self.touched.append((key_id, now))


class FakeZones:
    def __init__(self, names):
        self.names = {dns.name.from_text(n) for n in names}
        self.calls = []

    def is_authoritative(self, zname):
        self.calls.append(zname)
        return zname in self.names


class FakeAudit:
    def __init__(self):
        self.records = []
        self.authenticated = []

    def audit_limited(self, **kw):
        self.records.append(kw)
        return True

    def audit_authenticated(self, **kw):
        self.authenticated.append(kw)
        return True


class Snap:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.calls = 0
        self.error = None
        self.hook = None  # runs once, inside the first call (a duplicate "in flight")

    def __call__(self, *a):
        self.calls += 1
        if self.hook:
            hook, self.hook = self.hook, None
            hook()
        if self.error:
            raise self.error
        return self.snapshot


class Harness:
    def __init__(self, rows=(ROW1, ROW2), zones=(ZONE, "app.example.com."), clock=None,
                 closed=(), **kw):
        self.keys = FakeKeys()
        self.zones = FakeZones(zones)
        self.audit = FakeAudit()
        self.snap = Snap(snapshot_of(*rows, closed=closed))
        self.marks = []
        self.sampler = LogSampler(clock=lambda: 0.0)
        self.handler = DnsUpdateHandler(
            key_store=self.keys, zone_index=self.zones, audit=self.audit,
            snapshot_fn=self.snap, mark_confirmed_fn=lambda ids, now: self.marks.append(
                (list(ids), now)),
            clock=clock or (lambda: float(NOW)), log_sampler=self.sampler, **kw)

    def send(self, wire, transport="udp", peer=PEER):
        raw = self.handler.handle(wire, peer, transport)
        if raw is not None:
            _note_macs(raw)
        return raw

    def quiet(self):
        """True when nothing was written or looked up: the negative-test check."""
        return (not self.marks and not self.keys.touched and not self.audit.records
                and not self.audit.authenticated)

    def no_db(self):
        return (self.snap.calls == 0 and not self.zones.calls
                and "scope" not in self.keys.calls)


@pytest.fixture
def h():
    return Harness()


@pytest.fixture(autouse=True)
def _collect_logs(caplog):
    caplog.set_level(logging.DEBUG)
    yield
    LOGGED.extend(f"{r.name} {r.levelname} {r.getMessage()} {r.exc_text or ''}"
                  for r in caplog.get_records("call"))


# --- client helpers ------------------------------------------------------------

def at(t):
    """Make dnspython think that it is time t, for the client side."""
    return mock.patch.object(dns.message.time, "time", lambda: t)


def _note_macs(wire):
    try:
        m = dns.message.from_wire(wire, keyring=False)
        if m.tsig is not None and m.tsig[0].mac:
            _record_mac(m.tsig[0].mac)
    except Exception:
        pass


def _record_mac(mac):
    MACS_SEEN.add(mac.hex())
    MACS_SEEN.add(base64.b64encode(mac).decode())


def parse(raw):
    return dns.message.from_wire(raw, keyring=False)


def counts(raw):
    return struct.unpack("!6H", raw[:12])[2:]


class Req:
    def __init__(self, wire, mac=b"", key=None):
        self.wire, self.mac, self.key = wire, mac, key


def plain(msg):
    return Req(msg.to_wire())


def sign(msg, key=KEY, t=NOW, fudge=300):
    msg.use_tsig(key, fudge=fudge)
    with at(t):
        wire = msg.to_wire()
    _record_mac(msg.mac)
    return Req(wire, msg.mac, key)


def sign_wire(wire, key=KEY, t=NOW, fudge=300):
    """Sign a hand-made wire (the request builder of dnspython cannot make it)."""
    ident = struct.unpack("!H", wire[:2])[0]
    template = dns.rdtypes.ANY.TSIG.TSIG(dns.rdataclass.ANY, dns.rdatatype.TSIG, key.algorithm,
                                         t, fudge, b"", ident, 0, b"")
    signed, _ctx = dns.tsig.sign(wire, key, template, time=t)
    f = io.BytesIO()
    dns.rrset.from_rdata(key.name, 0, signed).to_wire(f)
    ar = struct.unpack("!H", wire[10:12])[0] + 1
    _record_mac(signed.mac)
    return Req(wire[:10] + struct.pack("!H", ar) + wire[12:] + f.getvalue(), signed.mac, key)


def verified(raw, req, t=NOW):
    """The response parsed with dnspython as a client, which verifies the TSIG."""
    assert raw is not None
    with at(t):
        resp = dns.message.from_wire(raw, keyring=req.key, request_mac=req.mac)
    assert resp.had_tsig
    return resp


def soa_query(name, rdtype="SOA", rdclass="IN", edns=None, payload=1232, flags=dns.flags.RD,
              options=None, ednsflags=None, ident=None):
    return dns.message.make_query(name, rdtype, rdclass, use_edns=edns, payload=payload if edns is not None else None,
                                  flags=flags, options=options, ednsflags=ednsflags, id=ident)


def upd(zone=ZONE, adds=(), deletes_any=(), deletes_none=(), ident=None):
    """adds: (name, ttl, value); deletes_any: names; deletes_none: (name, value)."""
    u = dns.update.UpdateMessage(zone)
    if ident is not None:
        u.id = ident
    for name in deletes_any:
        u.delete(name, "TXT")
    for name, value in deletes_none:
        u.delete(name, "TXT", f'"{value}"')
    for name, ttl, value in adds:
        u.add(name, ttl, "TXT", f'"{value}"')
    return u


GOOD_ADD = (RECORD1, 60, VALUE1)


def good_update(**kw):
    return upd(adds=[GOOD_ADD], **kw)


def soa_rdata(resp):
    return [rd for rr in resp.answer for rd in rr][0]


def set_opcode(wire, op):
    return wire[:2] + bytes([(wire[2] & 0x87) | (op << 3)]) + wire[3:]


def set_flags(wire, bits):
    flags = struct.unpack("!H", wire[2:4])[0] | bits
    return wire[:2] + struct.pack("!H", flags) + wire[4:]


def with_counts(wire, qd=None, an=None, ns=None, ar=None):
    cur = list(struct.unpack("!6H", wire[:12]))
    for idx, v in zip((2, 3, 4, 5), (qd, an, ns, ar)):
        if v is not None:
            cur[idx] = v
    return struct.pack("!6H", *cur) + wire[12:]


def header_only_ok(raw, rcode, wire):
    ident, flags = struct.unpack("!HH", wire[:4])
    assert len(raw) == 12
    assert struct.unpack("!H", raw[:2])[0] == ident
    f = struct.unpack("!H", raw[2:4])[0]
    assert f & 0x8000
    assert (f >> 11) & 0xF == (flags >> 11) & 0xF
    assert f & 0x0100 == flags & 0x0100
    assert f & 0xF == rcode
    assert counts(raw) == (0, 0, 0, 0)


# =============================================================================
# M: message
# =============================================================================

def test_M1_query_gets_response_pos(h):
    assert h.send(plain(soa_query("x.example.org.")).wire) is not None


def test_M1_message_with_qr_gets_no_response_neg(h):
    wire = set_flags(plain(soa_query("x.example.org.")).wire, 0x8000)
    assert h.send(wire) is None
    assert h.quiet() and h.no_db()
    assert h.sampler.counts()["qr"] == 1


def test_M2_header_only_message_gets_response_pos(h):
    wire = struct.pack("!6H", 1, 0, 0, 0, 0, 0)
    raw = h.send(wire)
    assert raw is not None and parse(raw).rcode() == dns.rcode.FORMERR


def test_M2_short_message_gets_no_response_neg(h):
    assert h.send(struct.pack("!6H", 1, 0, 0, 0, 0, 0)[:11]) is None
    assert h.send(b"") is None
    assert h.quiet() and h.no_db()
    assert h.sampler.counts()["short"] == 2


@pytest.mark.parametrize("op", [0, 5])
def test_M3_query_and_update_are_not_notimp_pos(h, op):
    raw = h.send(set_opcode(plain(soa_query("x.example.org.")).wire, op))
    assert raw is not None and parse(raw).rcode() != dns.rcode.NOTIMP


@pytest.mark.parametrize("op", [1, 2, 4, 6, 15])
def test_M3_other_opcodes_get_notimp_header_only_neg(h, op):
    wire = set_opcode(plain(soa_query("x.example.org.", flags=dns.flags.RD)).wire, op)
    raw = h.send(wire)
    header_only_ok(raw, dns.rcode.NOTIMP, wire)
    assert h.quiet() and h.no_db()
    # A signed request gets no TSIG either (decision 11).
    wire = set_opcode(sign(soa_query("x.example.org.")).wire, op)
    raw = h.send(wire)
    header_only_ok(raw, dns.rcode.NOTIMP, wire)


def test_M4_valid_message_is_not_formerr_pos(h):
    raw = h.send(plain(good_update()).wire)
    assert parse(raw).rcode() != dns.rcode.FORMERR


def _long_label_query():
    return (struct.pack("!6H", 7, 0x0100, 1, 0, 0, 0) + b"\x40" + b"a" * 64 + b"\x00"
            + struct.pack("!HH", 6, 1))


def _pointer_loop_query():
    return struct.pack("!6H", 7, 0x0100, 1, 0, 0, 0) + b"\xc0\x0c" + struct.pack("!HH", 6, 1)


@pytest.mark.parametrize("make", [
    lambda: plain(good_update()).wire[:-5],  # truncated RR
    lambda: plain(good_update()).wire + b"\x00\x01",  # trailing junk
    _long_label_query,  # bad label
    _pointer_loop_query,
])
def test_M4_malformed_message_gets_formerr_header_only_neg(h, make):
    wire = make()
    raw = h.send(wire)
    header_only_ok(raw, dns.rcode.FORMERR, wire)
    assert h.quiet() and h.no_db()
    assert h.sampler.counts()["formerr"] == 1


def test_M5_one_question_gets_answer_pos(h):
    assert parse(h.send(plain(soa_query("x.example.org.")).wire)).rcode() == dns.rcode.REFUSED


@pytest.mark.parametrize("n", [0, 2])
def test_M5_qdcount_not_one_gets_formerr_neg(h, n):
    q = soa_query("x.example.org.")
    q.question = [] if n == 0 else q.question * 2
    wire = q.to_wire()
    raw = h.send(wire)
    header_only_ok(raw, dns.rcode.FORMERR, wire)
    assert h.no_db() and h.quiet()
    # Signed: the FORMERR is signed and still has no section.
    req = sign(q)
    resp = verified(h.send(req.wire), req)
    assert resp.rcode() == dns.rcode.FORMERR and resp.question == []


def test_M6_z_zero_in_response_pos(h):
    raw = h.send(plain(soa_query("x.example.org.")).wire)
    assert struct.unpack("!H", raw[2:4])[0] & 0x0070 == 0


def test_M6_z_ad_cd_in_request_are_not_echoed_neg(h):
    wire = set_flags(plain(soa_query("x.example.org.")).wire, 0x0040 | 0x0020 | 0x0010)
    flags = struct.unpack("!H", h.send(wire)[2:4])[0]
    assert flags & (0x0040 | 0x0020 | 0x0010) == 0


def test_M7_rd_zero_stays_zero_pos(h):
    raw = h.send(plain(soa_query("x.example.org.", flags=0)).wire)
    flags = struct.unpack("!H", raw[2:4])[0]
    assert flags & 0x0100 == 0 and flags & 0x0080 == 0


def test_M7_rd_is_copied_and_ra_is_zero_neg(h):
    raw = h.send(plain(soa_query("x.example.org.")).wire)
    flags = struct.unpack("!H", raw[2:4])[0]
    assert flags & 0x0100 and flags & 0x0080 == 0


def test_M8_id_and_opcode_are_copied_pos(h):
    rng = random.Random(8)
    for _ in range(100):
        ident = rng.randrange(65536)
        resp = parse(h.send(plain(soa_query("x.example.org.", ident=ident)).wire))
        assert resp.id == ident and resp.opcode() == dns.opcode.QUERY
    u = plain(good_update(ident=0x2468))
    resp = parse(h.send(u.wire))
    assert resp.id == 0x2468 and resp.opcode() == dns.opcode.UPDATE


def test_M8_response_for_other_id_does_not_match_neg(h):
    q = soa_query("x.example.org.", ident=0x1234)
    resp = parse(h.send(plain(q).wire))
    assert resp.id != 0x1235 and resp.id != 0x1234 ^ 0xFFFF


# =============================================================================
# E: EDNS
# =============================================================================

def test_E1_opt_is_echoed_pos(h):
    resp = parse(h.send(plain(soa_query("x.example.org.", edns=0)).wire))
    assert resp.edns == 0


def test_E1_no_opt_without_opt_in_request_neg(h):
    raw = h.send(plain(soa_query("x.example.org.")).wire)
    assert parse(raw).edns == -1 and counts(raw)[3] == 0


def test_E1_advertised_payload_is_listener_limit_pos(h):
    # RFC 6891 §6.2.5: advertise what the listener accepts (MAX_MESSAGE_SIZE).
    from services.acme.dns_update.constants import MAX_MESSAGE_SIZE
    resp = parse(h.send(plain(soa_query("x.example.org.", edns=0)).wire))
    assert resp.payload == MAX_MESSAGE_SIZE


def test_E1_advertised_payload_not_dnspython_default_neg(h):
    resp = parse(h.send(plain(soa_query("x.example.org.", edns=0, payload=1232)).wire))
    assert resp.payload != 8192


def _two_opt_wire():
    wire = plain(soa_query("x.example.org.", edns=0)).wire
    opt = b"\x00\x00\x29\x10\x00\x00\x00\x00\x00\x00\x00"
    return with_counts(wire + opt, ar=2)


def test_E2_single_opt_is_valid_pos(h):
    assert parse(h.send(plain(soa_query("x.example.org.", edns=0)).wire)).rcode() \
        == dns.rcode.REFUSED


def test_E2_two_opt_get_formerr_neg(h):
    wire = _two_opt_wire()
    header_only_ok(h.send(wire), dns.rcode.FORMERR, wire)
    assert h.quiet()


def test_E3_version_zero_is_served_pos(h):
    resp = parse(h.send(plain(soa_query("x.example.org.", edns=0)).wire))
    assert resp.rcode() == dns.rcode.REFUSED


def test_E3_version_one_gets_badvers_with_opt_version_zero_neg(h):
    resp = parse(h.send(plain(soa_query("x.example.org.", edns=1)).wire))
    assert resp.rcode() == dns.rcode.BADVERS and resp.edns == 0
    assert resp.answer == [] and resp.tsig is None
    # Signed: signed BADVERS.
    req = sign(soa_query("x.example.org.", edns=1))
    resp = verified(h.send(req.wire), req)
    assert resp.rcode() == dns.rcode.BADVERS and resp.edns == 0
    assert h.quiet()


def test_E4_without_options_is_served_pos(h):
    resp = parse(h.send(plain(soa_query("x.example.org.", edns=0)).wire))
    assert resp.options == ()


def test_E4_unknown_option_and_flag_are_ignored_and_not_echoed_neg(h):
    q = soa_query("x.example.org.", edns=0, ednsflags=0x8000 | 0x4000,
                  options=[dns.edns.GenericOption(65001, b"junk")])
    resp = parse(h.send(plain(q).wire))
    assert resp.rcode() == dns.rcode.REFUSED
    assert resp.options == () and resp.ednsflags == 0


def test_E5_no_padding_without_padding_request_pos(h):
    resp = parse(h.send(plain(soa_query("x.example.org.", edns=0)).wire))
    assert all(o.otype != dns.edns.OptionType.PADDING for o in resp.options)


def test_E5_padding_request_gets_no_padding_neg(h):
    q = soa_query("x.example.org.", edns=0,
                  options=[dns.edns.GenericOption(dns.edns.OptionType.PADDING, b"\x00" * 100)])
    wire = plain(q).wire
    raw = h.send(wire)
    resp = parse(raw)
    assert all(o.otype != dns.edns.OptionType.PADDING for o in resp.options)
    assert len(raw) <= len(wire)


# =============================================================================
# T: size over UDP and TCP
# =============================================================================

def test_T1_refused_that_fits_is_not_truncated_pos(h):
    wire = plain(soa_query("x.example.org.")).wire
    raw = h.send(wire)
    resp = parse(raw)
    assert resp.rcode() == dns.rcode.REFUSED and not resp.flags & dns.flags.TC
    assert len(raw) <= len(wire)


@pytest.mark.parametrize("edns", [None, 0])
def test_T1_unsigned_soa_over_udp_is_truncated_neg(h, edns):
    wire = plain(soa_query(ZONE, edns=edns, payload=4096)).wire
    raw = h.send(wire, "udp")
    resp = parse(raw)
    assert resp.flags & dns.flags.TC and resp.rcode() == dns.rcode.NOERROR
    assert resp.answer == [] and resp.authority == [] and len(resp.question) == 1
    assert len(raw) <= len(wire)
    assert resp.tsig is None


def test_T4_unsigned_soa_over_tcp_is_full_pos(h):
    raw = h.send(plain(soa_query(ZONE)).wire, "tcp")
    resp = parse(raw)
    assert not resp.flags & dns.flags.TC and len(resp.answer) == 1


def test_T2_signed_soa_over_udp_without_edns_is_full_pos(h):
    req = sign(soa_query(RECORD1))
    raw = h.send(req.wire, "udp")
    resp = verified(raw, req)
    assert not resp.flags & dns.flags.TC and len(raw) <= 512
    assert resp.rcode() == dns.rcode.NOERROR


def _long(label, n=3):
    return ".".join([label * 60] * n) + ".example.net."


def test_T2_signed_response_above_512_is_truncated_with_tsig_neg():
    zone = _long("z")
    long_key = _key(_long("k"))
    row = ActiveRecord(1, 11, "_acme-challenge." + zone, VALUE1, zone, 1, "acct-1")
    hh = Harness(rows=(row,), zones=(zone,))
    hh.keys.materials[long_key.name] = TsigKeyMaterial(1, long_key.name, SHA256, SECRET)
    req = sign(soa_query(zone), key=long_key)
    full = hh.send(req.wire, "tcp")
    assert len(full) > 512 and len(verified(full, req).answer) == 1  # the precondition
    req2 = sign(soa_query(zone), key=long_key)
    raw = hh.send(req2.wire, "udp")
    resp = verified(raw, req2)
    assert resp.flags & dns.flags.TC and resp.answer == [] and len(resp.question) == 1
    assert len(raw) <= 512
    # With EDNS 4096 the same answer is not truncated.
    req3 = sign(soa_query(zone, edns=0, payload=4096), key=long_key)
    resp = verified(hh.send(req3.wire, "udp"), req3)
    assert not resp.flags & dns.flags.TC and len(resp.answer) == 1


def test_F1_udp_drop_when_truncated_form_is_still_too_large_pos():
    qname = ".".join(["a" * 60] * 4) + ".net."
    long_key = _key(".".join(["k" * 60] * 4) + ".org.")
    hh = Harness()
    hh.keys.materials[long_key.name] = TsigKeyMaterial(1, long_key.name, SHA256, SECRET)
    req = sign(soa_query(qname), key=long_key)
    assert hh.send(req.wire, "udp") is None
    assert hh.sampler.counts().get("udp_drop") == 1
    assert len(hh.handler._replay) == 0  # None is not cached
    # Over TCP the same request is answered (no size limit) and the answer is cached.
    assert hh.send(req.wire, "tcp") is not None
    assert len(hh.handler._replay) == 1


def test_F1_signed_answer_above_512_with_small_truncated_form_is_cached_neg():
    zone = _long("x")
    long_key = _key(_long("j"))
    row = ActiveRecord(1, 11, "_acme-challenge." + zone, VALUE1, zone, 1, "acct-1")
    hh = Harness(rows=(row,), zones=(zone,))
    hh.keys.materials[long_key.name] = TsigKeyMaterial(1, long_key.name, SHA256, SECRET)
    req = sign(soa_query(zone), key=long_key)
    raw = hh.send(req.wire, "udp")
    assert raw is not None and len(raw) <= 512
    assert verified(raw, req).flags & dns.flags.TC
    assert "udp_drop" not in hh.sampler.counts()
    assert len(hh.handler._replay) == 1


def test_S12_truncated_response_keeps_tsig_pos_and_neg():
    zone = _long("y")
    long_key = _key(_long("m"))
    row = ActiveRecord(1, 11, "_acme-challenge." + zone, VALUE1, zone, 1, "acct-1")
    hh = Harness(rows=(row,), zones=(zone,))
    hh.keys.materials[long_key.name] = TsigKeyMaterial(1, long_key.name, SHA256, SECRET)
    req = sign(soa_query(zone), key=long_key)
    raw = hh.send(req.wire, "udp")
    resp = parse(raw)
    assert resp.flags & dns.flags.TC and resp.tsig is not None  # TC with a TSIG
    verified(raw, req)
    # neg: the TSIG of the truncated response does not verify with another request MAC
    with pytest.raises(dns.tsig.BadSignature), at(NOW):
        dns.message.from_wire(raw, keyring=long_key, request_mac=b"\x00" * 32)


# =============================================================================
# Q: SOA discovery
# =============================================================================

def test_Q1_soa_for_zone_of_row_pos(h):
    resp = parse(h.send(plain(soa_query(ZONE)).wire, "tcp"))
    assert resp.rcode() == dns.rcode.NOERROR and resp.flags & dns.flags.AA
    assert len(resp.answer) == 1 and resp.authority == []
    rr = resp.answer[0]
    assert rr.name == dns.name.from_text(ZONE) and rr.ttl == 0 and rr.rdclass == IN
    assert rr.rdtype == dns.rdatatype.SOA and len(rr) == 1


def test_Q1_soa_rdata_has_the_fixed_values_pos(h):
    rd = soa_rdata(parse(h.send(plain(soa_query(ZONE)).wire, "tcp")))
    assert rd.mname == dns.name.from_text(ZONE)
    assert rd.rname == dns.name.from_text("hostmaster." + ZONE)
    assert (rd.serial, rd.refresh, rd.retry, rd.expire, rd.minimum) == SOA_TIMERS == \
        (1, 3600, 600, 86400, 0)


def test_Q1_no_row_gets_refused_neg():
    hh = Harness(rows=())
    resp = parse(hh.send(plain(soa_query(ZONE)).wire, "tcp"))
    assert resp.rcode() == dns.rcode.REFUSED and resp.answer == []
    assert not resp.flags & dns.flags.AA


def test_Q2_signed_soa_in_scope_is_signed_pos(h):
    req = sign(soa_query(ZONE))
    resp = verified(h.send(req.wire, "tcp"), req)
    assert resp.rcode() == dns.rcode.NOERROR and len(resp.answer) == 1
    assert h.quiet()  # no audit for queries


def test_Q2_signed_soa_for_row_of_another_account_is_refused_neg():
    hh = Harness(rows=(ROW2,))
    req = sign(soa_query(ZONE), key=KEY)  # account 1; the only row is of account 2
    resp = verified(hh.send(req.wire, "tcp"), req)
    assert resp.rcode() == dns.rcode.REFUSED and resp.answer == []
    # The same row answers for the key of account 2, and unsigned for everybody.
    req = sign(soa_query(ZONE), key=KEY2)
    assert len(verified(hh.send(req.wire, "tcp"), req).answer) == 1
    assert len(parse(hh.send(plain(soa_query(ZONE)).wire, "tcp")).answer) == 1


def test_Q2_key_without_scope_sees_no_rows_neg(h):
    h.keys.scopes.pop(1)
    req = sign(soa_query(ZONE))
    assert verified(h.send(req.wire, "tcp"), req).rcode() == dns.rcode.REFUSED


@pytest.mark.parametrize("rdtype", ["TXT", "A", "NS"])
@pytest.mark.parametrize("name", [RECORD1, ZONE])
def test_Q3_other_types_are_refused_neg(h, rdtype, name):
    resp = parse(h.send(plain(soa_query(name, rdtype)).wire, "tcp"))
    assert resp.rcode() == dns.rcode.REFUSED and resp.answer == [] and resp.authority == []
    assert h.quiet()


def test_Q3_soa_for_ancestor_of_zone_is_refused_neg(h):
    assert parse(h.send(plain(soa_query("com.")).wire, "tcp")).rcode() == dns.rcode.REFUSED


def test_Q4_class_in_is_served_pos(h):
    assert parse(h.send(plain(soa_query(ZONE)).wire, "tcp")).rcode() == dns.rcode.NOERROR


def test_Q4_class_ch_is_refused_neg(h):
    resp = parse(h.send(plain(soa_query(ZONE, rdclass="CH")).wire, "tcp"))
    assert resp.rcode() == dns.rcode.REFUSED and resp.answer == []


@pytest.mark.parametrize("rdtype", ["AXFR", "IXFR", "ANY"])
def test_Q5_meta_types_are_refused_neg(h, rdtype):
    for transport in ("tcp", "udp"):
        resp = parse(h.send(plain(soa_query(ZONE, rdtype)).wire, transport))
        assert resp.rcode() == dns.rcode.REFUSED and resp.answer == []


def test_Q6_names_are_compared_without_case_pos(h):
    resp = parse(h.send(plain(soa_query("EXAMPLE.Com.")).wire, "tcp"))
    assert len(resp.answer) == 1
    resp = parse(h.send(plain(soa_query("_ACME-Challenge.App.Example.COM.")).wire, "tcp"))
    assert resp.rcode() == dns.rcode.NOERROR and resp.answer == [] and len(resp.authority) == 1


def test_Q6_other_name_is_refused_neg(h):
    assert parse(h.send(plain(soa_query("EXAMPLE.org.")).wire, "tcp")).rcode() \
        == dns.rcode.REFUSED


def test_Q7_nsupdate_pattern_gets_nodata_with_soa_in_authority_pos(h):
    """nsupdate: signed SOA query for the record name, over UDP, without EDNS."""
    req = sign(soa_query(RECORD1))
    raw = h.send(req.wire, "udp")
    resp = verified(raw, req)
    assert resp.rcode() == dns.rcode.NOERROR and resp.flags & dns.flags.AA
    assert resp.answer == [] and len(resp.authority) == 1
    assert resp.authority[0].name == dns.name.from_text(ZONE)
    assert resp.authority[0].rdtype == dns.rdatatype.SOA and resp.authority[0].ttl == 0
    assert not resp.flags & dns.flags.TC and len(raw) <= 512


def test_Q7_certbot_walk_up_over_tcp_pos(h):
    names = [RECORD1, "app.example.com.", ZONE]
    resps = [parse(h.send(plain(soa_query(n)).wire, "tcp")) for n in names]
    assert [r.rcode() for r in resps] == [dns.rcode.NOERROR] * 3
    assert resps[0].answer == [] and resps[1].answer == []
    assert resps[0].authority and resps[1].authority
    assert len(resps[2].answer) == 1 and resps[2].flags & dns.flags.AA
    assert resps[2].answer[0].name == dns.name.from_text(names[2])


def test_Q7_lego_pattern_truncated_then_tcp_pos(h):
    wire = plain(soa_query(ZONE, edns=0, payload=4096)).wire
    first = parse(h.send(wire, "udp"))
    assert first.flags & dns.flags.TC
    second = parse(h.send(wire, "tcp"))
    assert not second.flags & dns.flags.TC and len(second.answer) == 1


@pytest.mark.parametrize("name", ["foo.example.com.", "_acme-challenge.foo.example.com.",
                                  "x.app.example.com.", "_acme-challenge.app.example.org."])
def test_Q7_name_without_active_row_is_refused_neg(h, name):
    resp = parse(h.send(plain(soa_query(name)).wire, "tcp"))
    assert resp.rcode() == dns.rcode.REFUSED and resp.authority == [] and resp.answer == []


def test_Q8_soa_for_apex_and_inner_name_of_closed_row_is_answered_pos():
    hh = Harness(rows=(), closed=(ROW1,))  # closed, expired or order done: not in by_name
    apex = parse(hh.send(plain(soa_query(ZONE)).wire, "tcp"))  # Q1 form
    assert apex.rcode() == dns.rcode.NOERROR and apex.flags & dns.flags.AA
    assert len(apex.answer) == 1 and apex.authority == []
    inner = parse(hh.send(plain(soa_query("app.example.com.")).wire, "tcp"))  # Q7 form
    assert inner.rcode() == dns.rcode.NOERROR and inner.answer == []
    assert len(inner.authority) == 1 and inner.authority[0].name == dns.name.from_text(ZONE)
    assert hh.quiet()


def test_Q8_signed_soa_sees_closed_rows_of_the_key_scope_only_neg():
    hh = Harness(rows=(), closed=(ROW2,))  # the closed row is of account 2
    req = sign(soa_query(ZONE), key=KEY)  # account 1
    resp = verified(hh.send(req.wire, "tcp"), req)
    assert resp.rcode() == dns.rcode.REFUSED and resp.answer == [] and resp.authority == []
    req = sign(soa_query(RECORD2), key=KEY)
    assert verified(hh.send(req.wire, "tcp"), req).rcode() == dns.rcode.REFUSED
    req = sign(soa_query(ZONE), key=KEY2)  # pos: the owner of the row
    assert len(verified(hh.send(req.wire, "tcp"), req).answer) == 1
    assert hh.quiet()


def test_Q8_update_add_with_value_of_closed_row_is_refused_neg():
    hh = Harness(rows=(), closed=(ROW1,))
    resp = send_signed(hh, good_update())
    assert resp.rcode() == dns.rcode.REFUSED
    assert hh.audit.records[-1]["reason"] == "no_pending_order"
    assert not hh.marks and not hh.keys.touched and not hh.audit.authenticated


def test_Q8_row_past_the_grace_is_refused_neg():
    hh = Harness(rows=(), closed=())  # a snapshot holds no row older than SOA_GRACE
    assert parse(hh.send(plain(soa_query(ZONE)).wire, "tcp")).rcode() == dns.rcode.REFUSED
    assert parse(hh.send(plain(soa_query(RECORD1)).wire, "tcp")).rcode() == dns.rcode.REFUSED
    assert hh.quiet()


def test_F6_rows_of_unrelated_zone_are_not_looked_at_pos():
    other = ActiveRecord(3, 13, "_acme-challenge.x.example.org.", VALUE2, "example.org.", 1,
                         "acct-1")
    hh = Harness(rows=(ROW1, other), zones=(ZONE, "example.org."))
    scope = mock.Mock()
    scope.allows.return_value = True
    hh.keys.scopes[1] = scope
    req = sign(soa_query(RECORD1))
    resp = verified(hh.send(req.wire, "udp"), req)
    assert len(resp.authority) == 1
    seen = [c.args for c in scope.allows.call_args_list]
    assert seen == [(ROW1.acme_client_account_id, ROW1.account_id)]


def test_F6_nested_zones_deepest_wins_pos():
    sub = "sub.example.com."
    r_sub = ActiveRecord(3, 13, "_acme-challenge.host.sub.example.com.", VALUE2, sub, 1,
                         "acct-1")
    r_top = ActiveRecord(4, 14, "_acme-challenge.sub.example.com.", VALUE1, ZONE, 1, "acct-1")
    hh = Harness(rows=(r_top, r_sub), zones=(ZONE, sub))
    resp = parse(hh.send(plain(soa_query(sub)).wire, "tcp"))
    assert len(resp.answer) == 1 and resp.answer[0].name == dns.name.from_text(sub)
    # NODATA below sub.example.com.: both zones have a matching row, the deepest one wins.
    r_top2 = ActiveRecord(5, 15, "_acme-challenge.host.sub.example.com.", VALUE1, ZONE, 1,
                          "acct-1")
    hh = Harness(rows=(r_top2, r_sub), zones=(ZONE, sub))
    resp = parse(hh.send(plain(soa_query("host.sub.example.com.")).wire, "tcp"))
    assert resp.answer == [] and len(resp.authority) == 1
    assert resp.authority[0].name == dns.name.from_text(sub)


def test_F6_index_is_rebuilt_only_for_a_new_snapshot_object_pos_and_neg(h):
    builds = []
    orig = h.handler._rows_by_zone.__func__

    def counting(self, snapshot):
        before = self._index_snapshot
        out = orig(self, snapshot)
        if snapshot is not before:
            builds.append(snapshot)
        return out

    with mock.patch.object(DnsUpdateHandler, "_rows_by_zone", counting):
        h.send(plain(soa_query(RECORD1)).wire, "tcp")
        h.send(plain(soa_query(ZONE)).wire, "tcp")
        assert len(builds) == 1  # neg: the same object does not rebuild
        h.snap.snapshot = snapshot_of(ROW1, ROW2)
        h.send(plain(soa_query(ZONE)).wire, "tcp")
        assert len(builds) == 2  # pos: a new object rebuilds


# =============================================================================
# U: UPDATE
# =============================================================================

def send_signed(h, msg, key=KEY, transport="udp", t=NOW):
    req = sign(msg, key=key, t=t)
    return verified(h.send(req.wire, transport), req, t)


def test_U1_one_soa_zone_goes_on_pos(h):
    assert send_signed(h, good_update()).rcode() == dns.rcode.NOERROR


def test_U1_empty_zone_section_is_formerr_neg(h):
    u = good_update()
    u.question = []
    u.update = []
    resp = send_signed(h, u)
    assert resp.rcode() == dns.rcode.FORMERR and not h.marks and h.keys.touched == []
    assert h.audit.records[-1]["reason"] == "format"


def test_U1_two_zone_records_and_other_ztype_are_formerr_neg(h):
    wire = plain(good_update()).wire
    # ZTYPE = A
    off = 12 + len(dns.name.from_text(ZONE).to_wire())
    wire_a = wire[:off] + struct.pack("!H", dns.rdatatype.A) + wire[off + 2:]
    header_only_ok(h.send(wire_a), dns.rcode.FORMERR, wire_a)
    # ZOCOUNT = 2
    q = good_update()
    q.question = q.question * 2
    wire2 = q.to_wire()
    header_only_ok(h.send(wire2), dns.rcode.FORMERR, wire2)
    assert h.quiet() and h.no_db()


def test_U2_class_in_goes_on_pos(h):
    assert send_signed(h, good_update()).rcode() == dns.rcode.NOERROR


def test_U2_class_ch_is_notauth_neg(h):
    u = dns.update.UpdateMessage(ZONE, rdclass=dns.rdataclass.CH)
    u.add(RECORD1, 60, "TXT", f'"{VALUE1}"')
    resp = send_signed(h, u)
    assert resp.rcode() == dns.rcode.NOTAUTH and not h.marks
    assert h.audit.records[-1]["reason"] == "not_authoritative"
    assert h.zones.calls == []  # the zone is not even looked up


def test_U2_class_any_is_formerr_in_dnspython_neg(h):
    """dnspython rejects a zone section of a meta class while it parses (FORMERR,
    unsigned), before the NOTAUTH check can run."""
    wire = plain(good_update()).wire
    off = 12 + len(dns.name.from_text(ZONE).to_wire()) + 2
    wire = wire[:off] + struct.pack("!H", dns.rdataclass.ANY) + wire[off + 2:]
    header_only_ok(h.send(wire), dns.rcode.FORMERR, wire)
    assert h.quiet()


@pytest.mark.parametrize("zone", [ZONE, "app.example.com."])
def test_U3_own_zone_and_its_ancestor_go_on_pos(h, zone):
    assert send_signed(h, upd(zone, adds=[GOOD_ADD])).rcode() == dns.rcode.NOERROR


@pytest.mark.parametrize("zone", ["other.org.", "sub.example.com.", "com.", "."])
def test_U3_foreign_zone_is_notauth_neg(h, zone):
    resp = send_signed(h, upd(zone, adds=[GOOD_ADD]))
    assert resp.rcode() == dns.rcode.NOTAUTH
    assert not h.marks and not h.keys.touched
    assert h.audit.records[-1]["reason"] == "not_authoritative"
    assert not h.audit.authenticated


def test_U4_signed_update_is_accepted_pos(h):
    assert send_signed(h, good_update()).rcode() == dns.rcode.NOERROR


def test_U4_unsigned_update_is_refused_at_once_neg():
    out = []
    for zone in (ZONE, "other.org."):  # a zone of ACME Domains and a foreign zone
        hh = Harness()
        raw = hh.send(plain(upd(zone, adds=[GOOD_ADD], ident=0x1111)).wire)
        resp = parse(raw)
        assert resp.rcode() == dns.rcode.REFUSED and resp.tsig is None
        assert len(raw) == 12 and counts(raw) == (0, 0, 0, 0)
        # No DB access of any kind and no audit (F6, F1).
        assert hh.snap.calls == 0 and hh.zones.calls == [] and hh.keys.calls == []
        assert hh.quiet() and hh.sampler.counts() == {"unsigned_update": 1}
        out.append(raw)
    assert out[0] == out[1]  # byte for byte, the ID included (it is the same here)
    # And the response does not depend on the ID except for the ID itself.
    other = Harness().send(plain(upd(ZONE, adds=[GOOD_ADD], ident=0x2222)).wire)
    assert other[2:] == out[0][2:] and other[:2] == b"\x22\x22"


@pytest.mark.parametrize("form", range(5))
def test_U5_prerequisite_forms_are_refused_neg(h, form):
    u = good_update()
    name = RECORD1
    [lambda: u.present(name),  # RFC 2136 §2.4.4 name is in use
     lambda: u.present(name, "TXT"),  # §2.4.1 RRset exists (value independent)
     lambda: u.present(name, "TXT", f'"{VALUE1}"'),  # §2.4.2 value dependent
     lambda: u.absent(name),  # §2.4.5 name is not in use
     lambda: u.absent(name, "TXT")][form]()  # §2.4.3 RRset does not exist
    resp = send_signed(h, u)
    assert resp.rcode() == dns.rcode.REFUSED and not h.marks and not h.keys.touched
    assert h.audit.records[-1]["reason"] == "prerequisite" and h.snap.calls == 0


def test_U5_empty_prerequisite_goes_on_pos(h):
    assert send_signed(h, good_update()).rcode() == dns.rcode.NOERROR


def test_U6_classes_in_any_none_go_on_pos(h):
    u = upd(adds=[GOOD_ADD], deletes_any=[RECORD1], deletes_none=[(RECORD1, VALUE1)])
    assert send_signed(h, u).rcode() == dns.rcode.NOERROR


def test_U6_class_ch_is_formerr_neg(h):
    u = good_update()
    u.sections[2][0] = dns.rrset.from_text(RECORD1, 60, "CH", "TXT", f'"{VALUE1}"')
    resp = send_signed(h, u)
    assert resp.rcode() == dns.rcode.FORMERR and not h.marks
    assert h.audit.records[-1]["reason"] == "format"


def test_U7_name_inside_zone_goes_on_pos(h):
    resp = send_signed(h, upd("app.example.com.", adds=[GOOD_ADD]))
    assert resp.rcode() == dns.rcode.NOERROR


def test_U7_name_outside_zone_is_notzone_neg(h):
    # The name is allowed for the key of account 2, but it is not below ZNAME.
    u = upd("app.example.com.", adds=[(RECORD2, 60, VALUE2)])
    resp = send_signed(h, u, key=KEY2)
    assert resp.rcode() == dns.rcode.NOTZONE and not h.marks and not h.keys.touched
    assert h.audit.records[-1]["reason"] == "not_in_zone"


def _patch_ttl(wire, ttl):
    """Set the TTL of the last RR of an UPDATE with one delete of class ANY, no TSIG."""
    rdlen_off = len(wire) - 2
    return wire[:rdlen_off - 4] + struct.pack("!I", ttl) + wire[rdlen_off:]


def test_U8_delete_with_ttl_zero_goes_on_pos(h):
    wire = plain(upd(deletes_any=[RECORD1])).wire
    req = sign_wire(_patch_ttl(wire, 0))
    assert verified(h.send(req.wire), req).rcode() == dns.rcode.NOERROR


def test_U8_delete_class_any_with_ttl_is_formerr_neg(h):
    wire = plain(upd(deletes_any=[RECORD1])).wire
    req = sign_wire(_patch_ttl(wire, 30))
    resp = verified(h.send(req.wire), req)
    assert resp.rcode() == dns.rcode.FORMERR and not h.marks and not h.keys.touched
    assert h.audit.records[-1]["reason"] == "format"


def test_U8_delete_class_none_with_ttl_is_formerr_neg(h):
    u = upd(deletes_none=[(RECORD1, VALUE1)])
    wire = plain(u).wire
    # The RR is the last one: ... TTL(4) RDLENGTH(2) RDATA(1 + 43)
    rdata_len = 1 + len(VALUE1)
    off = len(wire) - rdata_len - 2 - 4
    wire = wire[:off] + struct.pack("!I", 60) + wire[off + 4:]
    req = sign_wire(wire)
    resp = verified(h.send(req.wire), req)
    assert resp.rcode() == dns.rcode.FORMERR and not h.marks


def test_U8_delete_class_any_with_rdata_is_formerr_neg(h):
    wire = plain(upd(deletes_any=[RECORD1])).wire
    # RDLENGTH = 1 and one byte of RDATA, class ANY (RFC 2136 §2.5.2)
    bad = wire[:-2] + struct.pack("!H", 1) + b"\x00"
    header_only_ok(h.send(bad), dns.rcode.FORMERR, bad)


def test_U9_txt_at_challenge_name_goes_on_pos(h):
    assert send_signed(h, good_update()).rcode() == dns.rcode.NOERROR


def _add_rr(rdtype, name=RECORD1, rdata='"x"'):
    u = dns.update.UpdateMessage(ZONE)
    u.add(name, 60, rdtype, rdata)
    return u


@pytest.mark.parametrize("make", [
    lambda: _add_rr("A", rdata="192.0.2.1"),
    lambda: _add_rr("TXT", name="foo.app.example.com.", rdata=f'"{VALUE1}"'),
    lambda: _add_rr("CNAME", rdata="x.example.net."),
    lambda: _add_rr("TXT", name="example.com.", rdata=f'"{VALUE1}"'),
])
def test_U9_other_types_and_names_are_refused_neg(h, make):
    resp = send_signed(h, make())
    assert resp.rcode() == dns.rcode.REFUSED and not h.marks and not h.keys.touched
    assert h.audit.records[-1]["reason"] == "type_not_allowed" and not h.audit.authenticated


def test_U9_first_label_is_compared_without_case_pos(h):
    u = upd(adds=[("_ACME-Challenge.App.Example.com.", 60, VALUE1)])
    assert send_signed(h, u).rcode() == dns.rcode.NOERROR
    assert h.marks == [([1], NOW_DT)]


def test_U10_exact_value_is_accepted_pos(h):
    assert send_signed(h, good_update()).rcode() == dns.rcode.NOERROR
    assert h.marks == [([1], NOW_DT)]


def test_U10_value_in_two_strings_is_accepted_pos(h):
    u = dns.update.UpdateMessage(ZONE)
    u.add(RECORD1, 60, "TXT", f'"{VALUE1[:20]}" "{VALUE1[20:]}"')
    assert send_signed(h, u).rcode() == dns.rcode.NOERROR
    assert h.marks == [([1], NOW_DT)]


def test_U10_one_character_other_is_refused_neg(h):
    bad = VALUE1[:-1] + ("A" if VALUE1[-1] != "A" else "B")
    resp = send_signed(h, upd(adds=[(RECORD1, 60, bad)]))
    assert resp.rcode() == dns.rcode.REFUSED and h.quiet() is False
    assert not h.marks and not h.keys.touched and not h.audit.authenticated
    assert h.audit.records[-1]["reason"] == "value_mismatch"


def test_U10_row_of_another_proxy_account_is_refused_neg(h):
    resp = send_signed(h, upd(adds=[(RECORD2, 60, VALUE2)]))  # key of account 1
    assert resp.rcode() == dns.rcode.REFUSED and not h.marks and not h.keys.touched
    assert h.audit.records[-1]["reason"] == "no_pending_order"


def test_U10_value_of_another_row_at_the_name_is_refused_neg(h):
    resp = send_signed(h, upd(adds=[(RECORD1, 60, VALUE2)]))
    assert resp.rcode() == dns.rcode.REFUSED and not h.marks
    assert h.audit.records[-1]["reason"] == "value_mismatch"


def test_U10_no_active_row_is_refused_neg():
    hh = Harness(rows=())  # an expired or a closed row is not in the snapshot
    resp = send_signed(hh, good_update())
    assert resp.rcode() == dns.rcode.REFUSED and not hh.marks
    assert hh.audit.records[-1]["reason"] == "no_pending_order"


def test_U10_non_ascii_value_is_refused_neg(h):
    u = dns.update.UpdateMessage(ZONE)
    u.add(RECORD1, 60, "TXT", '"\\200\\201"')
    resp = send_signed(h, u)
    assert resp.rcode() == dns.rcode.REFUSED and not h.marks


def test_U11_delete_none_and_any_need_no_row_pos():
    hh = Harness(rows=())  # the order is gone
    for u in (upd(deletes_none=[(RECORD1, VALUE1)]), upd(deletes_any=[RECORD1])):
        assert send_signed(hh, u).rcode() == dns.rcode.NOERROR
    assert not hh.marks and hh.snap.calls == 0
    assert len(hh.audit.authenticated) == 2


def test_U11_delete_of_a_is_refused_neg(h):
    u = dns.update.UpdateMessage(ZONE)
    u.delete(RECORD1, "A")
    assert send_signed(h, u).rcode() == dns.rcode.REFUSED
    assert not h.marks and not h.keys.touched and not h.audit.authenticated


def test_U12_lego_delete_then_add_is_accepted_pos(h):
    u = upd(adds=[(RECORD1, 120, VALUE1)], deletes_any=[RECORD1])  # [ANY TXT, IN TXT]
    assert [rr.deleting for rr in dns.message.from_wire(u.to_wire(), keyring=False).update] \
        == [dns.rdataclass.ANY, None]
    assert send_signed(h, u).rcode() == dns.rcode.NOERROR
    assert h.marks == [([1], NOW_DT)]


def test_U12_one_bad_rr_rejects_the_whole_message_neg(h):
    u = upd(adds=[(RECORD1, 120, VALUE2)], deletes_any=[RECORD1])
    resp = send_signed(h, u)
    assert resp.rcode() == dns.rcode.REFUSED and not h.marks and not h.keys.touched
    assert h.audit.records[-1]["reason"] == "value_mismatch"
    assert h.audit.records[-1]["action"] == "acme.dns_update.refused"


def test_U12_good_add_after_bad_add_is_not_applied_neg(h):
    u = upd(adds=[(RECORD1, 60, VALUE1), (RECORD2, 60, VALUE2)])
    resp = send_signed(h, u)
    assert resp.rcode() == dns.rcode.REFUSED and not h.marks


def test_U13_second_identical_add_is_accepted_pos(h):
    for _ in range(2):  # two requests with different IDs: not a replay
        assert send_signed(h, good_update()).rcode() == dns.rcode.NOERROR
    assert len(h.marks) == 2


def test_U13_same_value_twice_in_one_message_pos(h):
    u = dns.update.UpdateMessage(ZONE)
    u.add(RECORD1, 60, "TXT", f'"{VALUE1}"')
    u.add(RECORD1, 60, "TXT", f'"{VALUE1}"')
    assert send_signed(h, u).rcode() == dns.rcode.NOERROR
    assert h.marks == [([1], NOW_DT)]


def test_U14_response_header_has_no_sections_pos(h):
    req = sign(good_update(ident=0x4321))
    raw = h.send(req.wire)
    resp = verified(raw, req)
    assert resp.id == 0x4321 and resp.opcode() == dns.opcode.UPDATE
    assert resp.flags & dns.flags.QR and resp.rcode() == dns.rcode.NOERROR
    assert counts(raw)[:3] == (0, 0, 0)  # only the TSIG is in the additional section
    assert counts(raw)[3] == 1


def test_U14_update_section_is_never_echoed_neg(h):
    u = upd(adds=[GOOD_ADD, (RECORD1, 60, VALUE2)])  # refused: the second value
    req = sign(u)
    raw = h.send(req.wire)
    resp = verified(raw, req)
    assert resp.zone == [] and resp.prerequisite == [] and resp.update == []
    assert VALUE1.encode() not in raw and VALUE2.encode() not in raw
    assert counts(raw)[:3] == (0, 0, 0)


def test_U15_accepted_update_sets_fields_and_audit_pos(h):
    assert send_signed(h, good_update(), t=NOW).rcode() == dns.rcode.NOERROR
    assert h.marks == [([1], NOW_DT)]
    assert h.keys.touched == [(1, NOW_DT)]
    assert len(h.audit.authenticated) == 1 and not h.audit.records
    rec = h.audit.authenticated[0]
    assert rec["action"] == "acme.dns_update.accepted" and rec["success"] is True
    assert rec["details"]["zone"] == ZONE and rec["details"]["names"] == [RECORD1]
    assert rec["details"]["adds"] == 1 and rec["details"]["deletes"] == 0
    assert VALUE1 not in repr(rec)


def test_U15_refused_update_changes_nothing_neg(h):
    send_signed(h, upd(adds=[(RECORD1, 60, VALUE2)]))
    assert not h.marks and not h.keys.touched and not h.audit.authenticated


def _delete_all(name=RECORD1):
    """Wire of an UPDATE with one "delete all RRsets" RR: class ANY, type ANY, TTL 0, RDLENGTH 0."""
    u = dns.update.UpdateMessage(ZONE)
    u.delete(name)
    return u.to_wire()


def _with_rr_class(wire, rclass):
    """The class of the last RR (it has no RDATA: ... CLASS(2) TTL(4) RDLENGTH(2))."""
    return wire[:-8] + struct.pack("!H", rclass) + wire[-6:]


def test_U17_delete_all_rrsets_at_challenge_name_is_accepted_as_delete_pos():
    hh = Harness(rows=())  # no row: a delete needs none
    u = dns.update.UpdateMessage(ZONE)
    u.delete("_acme-challenge.x.example.com.")  # class ANY, type ANY
    parsed = dns.message.from_wire(u.to_wire(), keyring=False).update[0]
    assert parsed.rdtype == dns.rdatatype.ANY and parsed.deleting == dns.rdataclass.ANY
    assert send_signed(hh, u).rcode() == dns.rcode.NOERROR
    assert not hh.marks and hh.snap.calls == 0 and not hh.audit.records
    details = hh.audit.authenticated[0]["details"]
    assert details["adds"] == 0 and details["deletes"] == 1


@pytest.mark.parametrize("rclass", [dns.rdataclass.NONE, dns.rdataclass.IN])
def test_U17_type_any_with_class_none_or_in_is_refused_neg(h, rclass):
    req = sign_wire(_with_rr_class(_delete_all(), rclass))
    resp = verified(h.send(req.wire), req)
    assert resp.rcode() == dns.rcode.REFUSED
    assert h.audit.records[-1]["reason"] == "type_not_allowed"
    assert not h.marks and not h.keys.touched and not h.audit.authenticated


def test_U17_delete_all_rrsets_at_other_name_is_refused_neg(h):
    for name in ("www.example.com.", "example.com.", "x._acme-challenge.example.com."):
        req = sign_wire(_delete_all(name))
        resp = verified(h.send(req.wire), req)
        assert resp.rcode() == dns.rcode.REFUSED
        assert h.audit.records[-1]["reason"] == "type_not_allowed"
    assert not h.marks and not h.keys.touched and not h.audit.authenticated


def test_U17_delete_all_rrsets_with_rdata_is_formerr_neg(h):
    # RDLENGTH = 1 and one byte of RDATA with class ANY. dnspython refuses this while it
    # parses, so the answer is FORMERR without TSIG, before the prescan can run.
    wire = _delete_all()
    bad = wire[:-2] + struct.pack("!H", 1) + b"\x00"
    req = sign_wire(bad)
    header_only_ok(h.send(req.wire), dns.rcode.FORMERR, req.wire)
    assert h.quiet() and h.no_db()


# --- client shapes (plan section 9) ---------------------------------------------

def test_U_cert_manager_shape_pos():
    """Zone = example.com. (public apex), record below app; add TTL 60; delete class NONE."""
    hh = Harness()
    assert send_signed(hh, upd(ZONE, adds=[(RECORD1, 60, VALUE1)])).rcode() == dns.rcode.NOERROR
    assert send_signed(hh, upd(ZONE, deletes_none=[(RECORD1, VALUE1)]),
                       transport="tcp").rcode() == dns.rcode.NOERROR
    assert hh.marks == [([1], NOW_DT)]


def test_U_acme_sh_shape_pos(h):
    assert send_signed(h, upd(adds=[(RECORD1, 60, VALUE1)])).rcode() == dns.rcode.NOERROR
    assert send_signed(h, upd(deletes_any=[RECORD1])).rcode() == dns.rcode.NOERROR


def test_U_certbot_shape_pos(h):
    """Zone from SOA discovery, add TTL 120 over TCP, delete class NONE."""
    soa = parse(h.send(plain(soa_query(ZONE)).wire, "tcp"))
    zone = soa.answer[0].name.to_text()
    assert send_signed(h, upd(zone, adds=[(RECORD1, 120, VALUE1)]),
                       transport="tcp").rcode() == dns.rcode.NOERROR
    assert send_signed(h, upd(zone, deletes_none=[(RECORD1, VALUE1)]),
                       transport="tcp").rcode() == dns.rcode.NOERROR


def test_U_win_acme_shape_pos_and_neg(h):
    """ZNAME from the registrable domain down: the first fits, a wrong one is NOTAUTH."""
    wrong = send_signed(h, upd("other.org.", adds=[GOOD_ADD]))
    assert wrong.rcode() == dns.rcode.NOTAUTH and not h.marks
    right = send_signed(h, upd(ZONE, adds=[GOOD_ADD]))
    assert right.rcode() == dns.rcode.NOERROR and h.marks == [([1], NOW_DT)]


# =============================================================================
# S: TSIG at handler level
# =============================================================================

def _append_rr(wire, rr_bytes):
    ar = struct.unpack("!H", wire[10:12])[0]
    return wire[:10] + struct.pack("!H", ar + 1) + wire[12:] + rr_bytes


def _tsig_rr_bytes(wire):
    return wire[tsig_start_offset(wire):]


def test_S1_tsig_last_is_processed_pos(h):
    assert send_signed(h, good_update()).rcode() == dns.rcode.NOERROR


def test_S1_two_tsig_and_tsig_not_last_are_formerr_neg(h):
    req = sign(good_update())
    two = _append_rr(req.wire, _tsig_rr_bytes(req.wire))
    header_only_ok(h.send(two), dns.rcode.FORMERR, two)
    opt = b"\x00\x00\x29\x10\x00\x00\x00\x00\x00\x00\x00"
    not_last = _append_rr(req.wire, opt)
    raw = h.send(not_last)
    header_only_ok(raw, dns.rcode.FORMERR, not_last)
    assert parse(raw).tsig is None and h.quiet()


def test_S10_every_response_to_a_signed_request_verifies_pos(h):
    cases = [
        soa_query(ZONE), soa_query(RECORD1), soa_query(ZONE, "TXT"), soa_query("x.org."),
        soa_query(ZONE, edns=0), soa_query(ZONE, edns=1),
        good_update(), upd(adds=[(RECORD1, 60, VALUE2)]), upd("other.org.", adds=[GOOD_ADD]),
        upd(deletes_any=[RECORD1]), upd(ident=5),
    ]
    q0 = soa_query(ZONE)
    q0.question = []
    cases.append(q0)
    p = good_update()
    p.present(RECORD1)
    cases.append(p)
    for transport in ("udp", "tcp"):
        for i, msg in enumerate(cases):
            req = sign(msg)
            req = Req(req.wire, req.mac, KEY)
            # a new ID makes each request a new one for the replay cache
            resp = verified(h.send(req.wire, transport), req)
            assert resp.had_tsig, i


def test_S10_unsigned_requests_get_no_tsig_neg(h):
    wires = [plain(soa_query(ZONE)).wire, plain(good_update()).wire,
             plain(soa_query("x.org.", edns=1)).wire, plain(soa_query("x.org.", "A")).wire,
             set_opcode(plain(soa_query(ZONE)).wire, 4), plain(soa_query(ZONE)).wire[:-3]]
    for transport in ("udp", "tcp"):
        for wire in wires:
            raw = h.send(wire, transport)
            assert raw is not None and parse(raw).tsig is None
            assert counts(raw)[3] == 0 or parse(raw).edns >= 0


def test_S2_badkey_is_answered_and_audited_pos(h):
    req = sign(good_update(), key=KEYU)
    raw = h.send(req.wire, "udp")
    resp = parse(raw)
    assert resp.rcode() == dns.rcode.NOTAUTH and resp.tsig[0].error == dns.rcode.BADKEY
    assert resp.tsig[0].mac == b"" and counts(raw)[:3] == (0, 0, 0)
    assert [(r["reason"], r["keyname"], r["peer_ip"], r["success"]) for r in h.audit.records] \
        == [("badkey", "unknown.example.", PEER, False)]
    assert h.sampler.counts() == {"badkey": 1}
    assert not h.marks and not h.keys.touched and h.snap.calls == 0 and not h.zones.calls


def test_S4_badsig_is_unsigned_and_audited_pos(h):
    req = sign(good_update())
    bad = bytearray(req.wire)
    i = bytes(req.wire).rfind(req.mac)
    bad[i + 3] ^= 1
    raw = h.send(bytes(bad), "udp")
    resp = parse(raw)
    assert resp.rcode() == dns.rcode.NOTAUTH and resp.tsig[0].error == dns.rcode.BADSIG
    assert resp.tsig[0].mac == b""
    assert h.audit.records[0]["reason"] == "badsig" and not h.marks


def test_S6_badtime_is_signed_and_audited_pos(h):
    req = sign(good_update(), t=NOW - 301)
    raw = h.send(req.wire, "udp")
    resp = parse(raw)  # dnspython refuses to verify an error response: look at the fields
    assert resp.rcode() == dns.rcode.NOTAUTH and resp.tsig[0].error == dns.rcode.BADTIME
    assert resp.tsig[0].time_signed == NOW - 301 and resp.tsig[0].mac  # client time, signed
    assert struct.unpack("!HI", resp.tsig[0].other) == (0, NOW)  # server time
    assert h.audit.records[0]["reason"] == "badtime" and not h.marks and not h.keys.touched


def test_S8_badtrunc_is_signed_and_audited_pos(h):
    req = sign(good_update())
    start = tsig_start_offset(req.wire)
    msg = parse(req.wire)
    short = dns.rrset.from_rdata(msg.tsig.name, 0, msg.tsig[0].replace(mac=req.mac[:16]))
    f = io.BytesIO()
    short.to_wire(f)
    wire = req.wire[:start] + f.getvalue()
    raw = h.send(wire, "udp")
    resp = parse(raw)
    assert resp.rcode() == dns.rcode.NOTAUTH and resp.tsig[0].error == dns.rcode.BADTRUNC
    assert resp.tsig[0].mac  # signed
    assert h.audit.records[0]["reason"] == "badtrunc" and not h.marks


def test_S_tsig_error_over_udp_is_not_larger_than_the_request_neg(h):
    req = sign(good_update(), key=KEYU)
    raw = h.send(req.wire, "udp")
    assert len(raw) <= len(req.wire)


# --- S15 replay -----------------------------------------------------------------------

def test_S15_udp_retransmit_gets_identical_bytes_once_pos(h):
    req = sign(good_update())
    first = h.send(req.wire, "udp")
    second = h.send(req.wire, "udp")
    assert first == second
    assert len(h.marks) == 1 and len(h.keys.touched) == 1 and len(h.audit.authenticated) == 1
    assert h.snap.calls == 1  # the replay does no work at all


def test_S15_other_transport_gets_own_response_without_new_side_effects_pos(h):
    req = sign(good_update())
    first = h.send(req.wire, "udp")
    tcp = h.send(req.wire, "tcp")
    assert verified(tcp, req).rcode() == dns.rcode.NOERROR
    assert len(h.marks) == 1 and len(h.audit.authenticated) == 1 and len(h.keys.touched) == 1
    assert h.snap.calls == 2  # the tcp response was rendered, the update was not repeated
    assert first == tcp  # same bytes here
    assert h.send(req.wire, "tcp") == tcp and h.snap.calls == 2  # now a plain cache hit
    assert h.send(req.wire, "udp") == first and len(h.marks) == 1


def test_S15_resend_with_other_header_id_is_the_same_request_pos(h):
    # The MAC covers the original ID in the TSIG, not the header ID (RFC 8945 §4.3.2):
    # a captured request resent with another header ID is still the same request.
    req = sign(good_update())
    first = h.send(req.wire, "udp")
    other_id = (struct.unpack("!H", req.wire[:2])[0] + 1) & 0xFFFF
    resent = struct.pack("!H", other_id) + req.wire[2:]
    second = h.send(resent, "udp")
    assert second[:2] == resent[:2] and second[2:] == first[2:]
    resp = verified(second, req)  # the response MAC still verifies (original ID in the TSIG)
    assert resp.rcode() == dns.rcode.NOERROR
    assert len(h.marks) == 1 and len(h.keys.touched) == 1 and len(h.audit.authenticated) == 1
    assert h.snap.calls == 1


def test_S15_new_request_with_new_mac_is_processed_neg(h):
    first = sign(good_update())
    h.send(first.wire, "udp")
    again = sign(good_update())  # new ID and new MAC: a new request, not a replay
    assert again.mac != first.mac
    assert verified(h.send(again.wire, "udp"), again).rcode() == dns.rcode.NOERROR
    assert len(h.marks) == 2 and len(h.audit.authenticated) == 2


def test_S15_refused_request_is_replayed_without_new_audit_pos(h):
    req = sign(upd(adds=[(RECORD1, 60, VALUE2)]))
    first = h.send(req.wire)
    assert h.send(req.wire) == first
    assert len(h.audit.records) == 1


def _clocked_harness(t):
    return Harness(clock=lambda: float(t[0]))


def test_S15_replay_after_later_request_gets_stored_answer_pos():
    t = [NOW]
    h = _clocked_harness(t)
    a = sign(good_update(), t=NOW - 1)
    b = sign(good_update(), t=NOW)
    first = h.send(a.wire)
    assert verified(first, a, t=NOW).rcode() == dns.rcode.NOERROR
    assert verified(h.send(b.wire), b).rcode() == dns.rcode.NOERROR
    assert len(h.marks) == 2 and len(h.audit.authenticated) == 2 and len(h.keys.touched) == 2
    assert h.audit.records == []
    again = h.send(a.wire)
    assert again == first
    assert len(h.marks) == 2 and len(h.audit.authenticated) == 2 and len(h.keys.touched) == 2
    assert h.audit.records == []  # no "rejected badtime" row
    assert h.handler._watermark.is_older(1, NOW - 1) is True  # watermark stayed at NOW
    assert h.handler._watermark.is_older(1, NOW) is False


def test_S15_replay_over_other_transport_after_later_request_changes_nothing_pos():
    t = [NOW]
    h = _clocked_harness(t)
    a = sign(good_update(), t=NOW - 1)
    h.send(a.wire, "udp")
    h.send(sign(good_update(), t=NOW).wire)
    marks, aud, touched = len(h.marks), len(h.audit.authenticated), len(h.keys.touched)
    tcp = h.send(a.wire, "tcp")
    assert verified(tcp, a, t=NOW).rcode() == dns.rcode.NOERROR
    assert (len(h.marks), len(h.audit.authenticated), len(h.keys.touched)) == (marks, aud, touched)
    assert h.audit.records == []


def test_S15_new_request_older_than_watermark_is_badtime_neg():
    t = [NOW]
    h = _clocked_harness(t)
    h.send(sign(good_update(), t=NOW).wire)
    marks, aud, touched = len(h.marks), len(h.audit.authenticated), len(h.keys.touched)
    raw = h.send(sign(good_update(), t=NOW - 1).wire)
    assert parse(raw).rcode() == dns.rcode.BADTIME or parse(raw).tsig[0].error == dns.rcode.BADTIME
    assert len(h.audit.records) == 1 and h.audit.records[0]["reason"] == "badtime"
    assert (len(h.marks), len(h.audit.authenticated), len(h.keys.touched)) == (marks, aud, touched)


def test_S15_replay_with_changed_mac_is_badsig_and_cache_not_asked_neg():
    h = Harness()
    req = sign(good_update())
    h.send(req.wire)
    asked = []
    real_seen = h.handler._replay.seen
    h.handler._replay.seen = lambda k: asked.append(k) or real_seen(k)
    mac = req.mac
    i = req.wire.rfind(mac)
    bad = bytearray(req.wire)
    bad[i + 3] ^= 1
    raw = h.send(bytes(bad))
    assert parse(raw).tsig[0].error == dns.rcode.BADSIG
    assert asked == []
    assert len(h.marks) == 1 and len(h.audit.authenticated) == 1 and len(h.keys.touched) == 1
    assert [r["reason"] for r in h.audit.records] == ["badsig"]


def test_S15_replay_after_ttl_outside_window_is_badtime_neg():
    t = [NOW]
    h = _clocked_harness(t)
    a = sign(good_update(), t=NOW)
    h.send(a.wire)
    t[0] = NOW + REPLAY_TTL_S + 1000  # entry expired and the time window is over
    raw = h.send(a.wire)
    assert parse(raw).tsig[0].error == dns.rcode.BADTIME
    assert len(h.marks) == 1 and len(h.audit.authenticated) == 1 and len(h.keys.touched) == 1
    assert [r["reason"] for r in h.audit.records] == ["badtime"]


def test_S15_unsigned_request_is_not_cached_neg(h):
    wire = plain(good_update()).wire
    h.send(wire)
    h.send(wire)
    assert h.sampler.counts()["unsigned_update"] == 2


def test_S15_replay_cache_is_bounded_and_expires_pos_and_neg():
    t = [0.0]
    cache = ReplayCache(size=3, ttl_s=10, clock=lambda: t[0])
    for i in range(5):
        cache.put(i, b"v%d" % i)
    assert len(cache) == 3 and cache.get(0) is None and cache.get(4) == b"v4"
    t[0] = 10.0
    assert cache.get(4) is None and len(cache) == 2  # expired, and dropped


def test_S15_replay_cache_is_thread_safe_pos():
    cache = ReplayCache(size=50, ttl_s=100)
    errors = []

    def work(n):
        try:
            for i in range(500):
                cache.put((n, i % 80), b"x")
                cache.get((n, (i * 7) % 80))
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(n,)) for n in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors and len(cache) <= 50


def test_A1_default_ttl_covers_both_sides_of_the_fudge_pos_and_neg():
    assert REPLAY_TTL_S == 2 * MAX_FUDGE
    t = [0.0]
    cache = ReplayCache(clock=lambda: t[0])
    cache.put(b"d", b"v")
    t[0] = 2 * MAX_FUDGE - 1
    assert cache.get(b"d") == b"v"
    t[0] = 2 * MAX_FUDGE + 1
    assert cache.get(b"d") is None and not cache.seen(b"d")


def test_A1_replay_450s_after_the_first_copy_is_a_cache_hit_pos():
    clock = [float(NOW)]
    hh = Harness(clock=lambda: clock[0])
    req = sign(good_update(), t=NOW + 250)  # Time Signed is 250 s ahead of the server
    first = hh.send(req.wire)
    assert verified(first, req, t=NOW).rcode() == dns.rcode.NOERROR
    clock[0] = NOW + 450.0  # 200 s after Time Signed: still inside the fudge
    assert hh.send(req.wire) == first
    assert len(hh.marks) == 1 and len(hh.audit.authenticated) == 1 and hh.snap.calls == 1
    assert hh.sampler.counts().get("badtime") is None


def test_A1_replay_outside_the_fudge_is_badtime_not_a_second_update_neg():
    clock = [float(NOW)]
    hh = Harness(clock=lambda: clock[0])
    req = sign(good_update(), t=NOW + 250)
    first = hh.send(req.wire)
    # 301 s after Time Signed, entry still live: the stored answer (S15, step 6e before 6f).
    clock[0] = NOW + 551.0
    assert hh.send(req.wire) == first
    assert "badtime" not in hh.sampler.counts()
    # The entry is gone after REPLAY_TTL_S: BADTIME, and no second update.
    clock[0] = NOW + 250 + REPLAY_TTL_S + 1.0
    assert hh.send(req.wire) is not None
    assert hh.sampler.counts()["badtime"] == 1
    assert len(hh.marks) == 1 and len(hh.audit.authenticated) == 1 and hh.snap.calls == 1


def test_A1_udp_request_replayed_over_tcp_has_side_effects_once_pos(h):
    req = sign(good_update())
    h.send(req.wire, "udp")
    raw = h.send(req.wire, "tcp")
    assert verified(raw, req).rcode() == dns.rcode.NOERROR
    assert len(h.marks) == 1 and len(h.keys.touched) == 1 and len(h.audit.authenticated) == 1


def test_A1_other_wire_over_tcp_runs_side_effects_neg(h):
    first = sign(good_update(ident=1111))
    other = sign(good_update(ident=2222))
    h.send(first.wire, "udp")
    assert verified(h.send(other.wire, "tcp"), other).rcode() == dns.rcode.NOERROR
    assert len(h.marks) == 2 and len(h.keys.touched) == 2 and len(h.audit.authenticated) == 2


def test_A1_tcp_first_then_udp_has_side_effects_once_pos(h):
    req = sign(good_update())
    h.send(req.wire, "tcp")
    assert verified(h.send(req.wire, "udp"), req).rcode() == dns.rcode.NOERROR
    assert len(h.marks) == 1 and len(h.audit.authenticated) == 1


def test_A1_duplicate_in_flight_gets_no_response_and_no_side_effect_pos(h):
    req = sign(good_update())
    inner = []
    h.snap.hook = lambda: inner.append(h.send(req.wire, "udp"))
    outer = h.send(req.wire, "udp")
    assert inner == [None]
    assert verified(outer, req).rcode() == dns.rcode.NOERROR
    assert len(h.marks) == 1 and len(h.keys.touched) == 1 and len(h.audit.authenticated) == 1
    assert h.snap.calls == 1  # the duplicate did no work
    # The retransmission after the first copy is done hits the cache.
    assert h.send(req.wire, "udp") == outer and len(h.marks) == 1


def test_A1_duplicate_in_flight_over_the_other_transport_is_dropped_pos(h):
    req = sign(good_update())
    inner = []
    h.snap.hook = lambda: inner.append(h.send(req.wire, "tcp"))
    h.send(req.wire, "udp")
    assert inner == [None] and len(h.marks) == 1


def test_A1_other_wire_in_flight_runs_normally_neg(h):
    first = sign(good_update(ident=1111))
    other = sign(good_update(ident=2222))
    inner = []
    h.snap.hook = lambda: inner.append(h.send(other.wire, "udp"))
    outer = h.send(first.wire, "udp")
    assert verified(inner[0], other).rcode() == dns.rcode.NOERROR
    assert verified(outer, first).rcode() == dns.rcode.NOERROR
    assert len(h.marks) == 2 and len(h.audit.authenticated) == 2


def test_A1_in_flight_mark_is_removed_when_processing_fails_neg(h):
    req = sign(good_update())
    h.snap.error = ValueError("x")
    assert verified(h.send(req.wire), req).rcode() == dns.rcode.SERVFAIL
    h.snap.error = None
    resp = verified(h.send(req.wire), req)  # not dropped as "in flight"
    assert resp.rcode() == dns.rcode.NOERROR and len(h.marks) == 1
    assert not h.handler._replay._in_flight


def test_A1_in_flight_mark_is_removed_when_an_exception_escapes_neg(h):
    req = sign(good_update())
    with mock.patch.object(h.handler, "_process", side_effect=RuntimeError("x")):
        raw = h.send(req.wire)
    header_only_ok(raw, dns.rcode.SERVFAIL, req.wire)
    assert not h.handler._replay._in_flight
    assert verified(h.send(req.wire), req).rcode() == dns.rcode.NOERROR


def test_A1_replay_cache_begin_end_pos_and_neg():
    cache = ReplayCache()
    assert cache.begin(b"a") and not cache.begin(b"a")
    assert cache.begin(b"b")
    cache.end(b"a")
    assert cache.begin(b"a")
    cache.end(b"zz")  # unknown digest: no error


# --- A2: signed SERVFAIL (RFC 8945 §5.3) ------------------------------------------------

def test_A2_signed_request_error_gets_signed_servfail_pos(h):
    h.snap.error = RuntimeError("db is down")
    req = sign(good_update())
    raw = h.send(req.wire, "tcp")
    resp = verified(raw, req)
    assert resp.rcode() == dns.rcode.SERVFAIL
    assert resp.question == [] and resp.answer == [] and resp.authority == []
    assert h.sampler.counts()["servfail"] == 1 and h.quiet()
    assert len(h.handler._replay) == 0  # a failure is not cached


def test_A2_signed_query_error_gets_signed_servfail_over_udp_pos(h):
    h.snap.error = RuntimeError("db is down")
    req = sign(soa_query(ZONE))
    assert verified(h.send(req.wire, "udp"), req).rcode() == dns.rcode.SERVFAIL


def test_A2_unsigned_request_error_gets_header_only_servfail_neg(h):
    h.snap.error = RuntimeError("db is down")
    wire = plain(soa_query(ZONE)).wire
    raw = h.send(wire, "tcp")
    header_only_ok(raw, dns.rcode.SERVFAIL, wire)
    assert parse(raw).tsig is None and h.quiet()


def test_A2_failure_of_the_signed_rendering_falls_back_to_header_only_neg(h):
    req = sign(good_update())
    with mock.patch.object(handler_mod.tsig, "render_signed", side_effect=RuntimeError("x")):
        raw = h.send(req.wire)
    header_only_ok(raw, dns.rcode.SERVFAIL, req.wire)
    assert parse(raw).tsig is None and h.quiet()
    assert not h.handler._replay._in_flight
    assert verified(h.send(req.wire), req).rcode() == dns.rcode.NOERROR


# --- A3: SOA query cost ------------------------------------------------------------------

def test_A3_name_outside_every_zone_parses_no_row_name_pos(h):
    handler_mod._name_of.cache_clear()
    for name in ("other.net.", "a.b.other.net.", "com.", "."):
        resp = parse(h.send(plain(soa_query(name)).wire, "tcp"))
        assert resp.rcode() == dns.rcode.REFUSED and resp.answer == [] and resp.authority == []
    assert handler_mod._name_of.cache_info().misses == 0
    req = sign(soa_query("other.net."))
    assert verified(h.send(req.wire, "tcp"), req).rcode() == dns.rcode.REFUSED
    assert handler_mod._name_of.cache_info().misses == 0


def test_A3_name_inside_a_zone_is_answered_as_before_and_parsed_once_neg(h):
    handler_mod._name_of.cache_clear()
    assert len(parse(h.send(plain(soa_query(ZONE)).wire, "tcp")).answer) == 1
    resp = parse(h.send(plain(soa_query("app.example.com.")).wire, "tcp"))
    assert resp.rcode() == dns.rcode.NOERROR and len(resp.authority) == 1  # Q7
    misses = handler_mod._name_of.cache_info().misses
    assert misses > 0
    h.send(plain(soa_query(ZONE)).wire, "tcp")
    info = handler_mod._name_of.cache_info()
    assert info.misses == misses and info.hits > 0  # the second query parses nothing


def test_A3_name_cache_is_bounded_pos():
    assert handler_mod._name_of.cache_info().maxsize == 4096


def test_A3_zone_prefilter_uses_the_snapshot_zones_neg():
    hh = Harness(rows=(ROW1,), zones=(ZONE,))
    hh.snap.snapshot = ActiveSnapshot(hh.snap.snapshot.by_name, frozenset(),
                                      hh.snap.snapshot.soa_rows)
    assert parse(hh.send(plain(soa_query(ZONE)).wire, "tcp")).rcode() == dns.rcode.REFUSED
    hh.snap.snapshot = snapshot_of(ROW1)
    assert len(parse(hh.send(plain(soa_query(ZONE)).wire, "tcp")).answer) == 1


# =============================================================================
# K6, R5: scope
# =============================================================================

def test_K6_key_without_rows_changes_nothing_neg(h):
    resp = send_signed(h, good_update(), key=KEY3)
    assert resp.rcode() == dns.rcode.REFUSED and not h.marks and not h.keys.touched
    assert h.audit.records[-1]["reason"] == "no_pending_order"
    assert send_signed(h, good_update(), key=KEY).rcode() == dns.rcode.NOERROR  # pos


def test_R5_eab_key_with_other_acme_account_is_refused_neg(h):
    resp = send_signed(h, good_update(), key=KEYE)  # bound to acct-9, the row is acct-1
    assert resp.rcode() == dns.rcode.REFUSED and not h.marks and not h.keys.touched


def test_R5_eab_key_with_its_acme_account_is_accepted_pos():
    row = ROW1._replace(account_id="acct-9")
    hh = Harness(rows=(row,))
    assert send_signed(hh, good_update(), key=KEYE).rcode() == dns.rcode.NOERROR
    assert hh.marks == [([1], NOW_DT)]


def test_R5_other_proxy_account_is_refused_neg(h):
    assert send_signed(h, good_update(), key=KEY2).rcode() == dns.rcode.REFUSED


# =============================================================================
# N: server-side safety
# =============================================================================

def test_N5_no_outgoing_connection_pos_and_neg(h):
    with mock.patch.object(socket.socket, "connect", side_effect=AssertionError("connect")) as c, \
            mock.patch.object(socket, "create_connection",
                              side_effect=AssertionError("create_connection")) as cc:
        for msg in (soa_query(ZONE), soa_query(RECORD1, flags=dns.flags.RD)):
            assert parse(h.send(plain(msg).wire, "tcp")).rcode() == dns.rcode.NOERROR
        assert send_signed(h, good_update()).rcode() == dns.rcode.NOERROR
        assert send_signed(h, upd(adds=[(RECORD1, 60, VALUE2)])).rcode() == dns.rcode.REFUSED
        assert parse(h.send(plain(good_update()).wire)).rcode() == dns.rcode.REFUSED
        assert send_signed(h, soa_query(RECORD1), transport="tcp").rcode() == dns.rcode.NOERROR
        c.assert_not_called()
        cc.assert_not_called()
    assert "servfail" not in h.sampler.counts()  # no AssertionError was swallowed


def test_N6_unsigned_and_malformed_write_no_audit_pos(h):
    for wire in (plain(good_update()).wire, plain(soa_query(ZONE)).wire, b"\x00" * 5,
                 plain(good_update()).wire[:-4], set_opcode(plain(soa_query(ZONE)).wire, 3)):
        h.send(wire)
    assert h.audit.records == [] and h.audit.authenticated == []


def test_N6_accepted_update_is_audited_once_with_peer_and_key_neg(h):
    req = sign(good_update())
    h.send(req.wire, "udp", peer="198.51.100.9")
    assert len(h.audit.authenticated) == 1 and h.audit.records == []
    rec = h.audit.authenticated[0]
    assert rec["peer_ip"] == "198.51.100.9" and rec["keyname"] == "k1.example."
    assert rec["details"]["transport"] == "udp"


def test_N6_signed_refusal_is_audited_with_reason_neg(h):
    req = sign(upd(adds=[(RECORD1, 60, VALUE2)]))
    h.send(req.wire, "tcp", peer="198.51.100.9")
    assert h.audit.authenticated == []
    rec = h.audit.records[0]
    assert rec["reason"] == "value_mismatch" and rec["action"] == "acme.dns_update.refused"
    assert rec["peer_ip"] == "198.51.100.9" and rec["keyname"] == "k1.example."
    assert rec["success"] is False
    assert VALUE1 not in repr(rec) and VALUE2 not in repr(rec)


def test_N9_counts_inside_limits_are_processed_pos(h):
    q = plain(soa_query("x.example.org.")).wire
    assert h.send(with_counts(q, qd=1)) is not None
    wire = with_counts(q, qd=16)  # in the limit: parse error, FORMERR
    header_only_ok(h.send(wire), dns.rcode.FORMERR, wire)


def test_N9_query_with_answer_count_gets_no_response_and_no_parse_pos(h):
    wire = with_counts(plain(soa_query("x.example.org.")).wire, an=1)
    with mock.patch.object(handler_mod.dns.message, "from_wire") as parser:
        assert h.send(wire) is None
        assert parser.call_count == 0
    assert h.sampler.counts()["counts"] == 1
    assert h.quiet() and h.no_db()


def test_N9_query_with_answer_count_16_gets_no_response_pos(h):
    assert h.send(with_counts(plain(soa_query("x.example.org.")).wire, an=16)) is None


def test_N9_query_with_zero_answers_is_answered_neg(h):
    with mock.patch.object(handler_mod.dns.message, "from_wire",
                           wraps=handler_mod.dns.message.from_wire) as parser:
        assert h.send(plain(soa_query("x.example.org.")).wire) is not None
        assert parser.called


def test_N9_update_with_one_prerequisite_is_still_refused_neg(h):
    u = upd(adds=[GOOD_ADD])
    u.present(RECORD1)
    raw = h.send(sign(u).wire)
    assert parse(raw).rcode() == dns.rcode.REFUSED
    assert len(h.audit.records) == 1 and h.audit.records[0]["reason"] == "prerequisite"


@pytest.mark.parametrize("kw", [dict(ar=1000), dict(ar=5), dict(qd=17), dict(an=17), dict(ns=17)])
def test_N9_counts_above_limits_get_no_response_neg(h, kw):
    q = plain(soa_query("x.example.org.")).wire
    with mock.patch("dns.message.from_wire", side_effect=AssertionError("parsed")) as p:
        assert h.send(with_counts(q, **kw)) is None
        p.assert_not_called()
    assert h.sampler.counts()["counts"] == 1 and h.quiet()


def test_N9_size_limit_pos_and_neg(h):
    pad = dns.edns.GenericOption(65001, b"\x00" * 3000)
    ok = soa_query("x.example.org.", edns=0, options=[pad]).to_wire(max_size=65535)
    assert 3000 < len(ok) <= 4096 and h.send(ok) is not None
    big = soa_query("x.example.org.", edns=0,
                    options=[dns.edns.GenericOption(65001, b"\x00" * 4100)]).to_wire(
                        max_size=65535)
    assert len(big) > 4096
    with mock.patch("dns.message.from_wire", side_effect=AssertionError("parsed")):
        assert h.send(big) is None
    assert h.sampler.counts()["oversize"] == 1


def test_N10_snapshot_error_gives_servfail_then_service_goes_on_neg(h):
    from models import db
    h.snap.error = RuntimeError("db is down")
    wire = plain(soa_query(ZONE)).wire
    with mock.patch.object(db.session, "rollback") as rb:
        raw = h.send(wire, "tcp")
        rb.assert_called_once()
    header_only_ok(raw, dns.rcode.SERVFAIL, wire)
    assert h.sampler.counts()["servfail"] == 1 and h.quiet()
    h.snap.error = None
    assert len(parse(h.send(wire, "tcp")).answer) == 1


def test_N10_signed_request_error_gives_signed_servfail_neg(h):
    h.snap.error = ValueError("x")
    req = sign(good_update())
    raw = h.send(req.wire)
    assert verified(raw, req).rcode() == dns.rcode.SERVFAIL
    # The failed request is not cached: the retransmit runs again and now works.
    h.snap.error = None
    resp = verified(h.send(req.wire), req)
    assert resp.rcode() == dns.rcode.NOERROR and len(h.marks) == 1


def test_N10_side_effect_error_keeps_the_response_neg(h):
    h.audit.audit_authenticated = mock.Mock(side_effect=RuntimeError("audit"))
    req = sign(good_update())
    resp = verified(h.send(req.wire), req)
    assert resp.rcode() == dns.rcode.NOERROR
    assert h.sampler.counts()["side_effect"] == 1


def test_N_udp_drop_when_truncated_form_is_still_too_long_neg(h):
    resp = dns.message.make_response(parse(plain(soa_query(ZONE)).wire), pad=0)
    assert h.handler._render_unsigned(resp, 20, PEER) is None
    assert h.sampler.counts()["udp_drop"] == 1
    assert h.handler._render_unsigned(resp, None, PEER) is not None  # pos: TCP


def test_log_sampler_one_line_per_reason_per_interval_pos_and_neg(caplog):
    t = [100.0]
    log = LogSampler(interval_s=10, clock=lambda: t[0])
    assert log.note("badkey", logging.WARNING, "192.0.2.1") is True
    assert log.note("badkey", logging.WARNING, "192.0.2.1") is False
    assert log.note("badsig", logging.WARNING, "192.0.2.1") is True  # another reason
    t[0] = 110.0
    assert log.note("badkey", logging.WARNING, "192.0.2.1") is True
    assert log.counts() == {"badkey": 3, "badsig": 1}


def test_handler_counts_flood_but_logs_once_neg(h, caplog):
    for _ in range(50):
        h.send(plain(good_update()).wire)
    assert h.sampler.counts() == {"unsigned_update": 50}
    lines = [r for r in caplog.records if "unsigned_update" in r.getMessage()]
    assert len(lines) == 1


def test_handler_does_not_raise_on_garbage_pos():
    hh = Harness()
    rng = random.Random(3)
    for n in range(300):
        wire = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 80)))
        hh.send(wire, "udp" if n % 2 else "tcp")  # must not raise
    good = plain(good_update()).wire
    for i in range(len(good)):  # every truncation
        hh.send(good[:i])
    for i in range(len(good)):  # every byte flipped
        hh.send(good[:i] + bytes([good[i] ^ 0xFF]) + good[i + 1:])
    assert "servfail" not in hh.sampler.counts()


# =============================================================================
# Integration with the real key store, zone index, snapshot and database
# =============================================================================

@pytest.fixture
def real(app):
    import json
    import uuid

    from sqlalchemy import event

    from models import db, AcmeClientAccount, AcmeClientOrder, AcmeDomain, DnsProvider
    from models.acme_dns_update import AcmeDnsUpdateKey, AcmeProxyDnsChallenge
    from models.audit_log import AuditLog
    from services.acme.dns_update import audit as audit_mod
    from services.acme.dns_update import keys, records, zones
    from utils.datetime_utils import utc_now

    class Real:
        pass

    r = Real()
    with app.app_context():
        floor = db.session.query(db.func.max(AcmeClientOrder.id)).scalar() or 0
        provider = DnsProvider(name=f"hnd-{uuid.uuid4().hex[:6]}", provider_type="manual",
                               zones=json.dumps(["example.com"]))
        account = AcmeClientAccount(directory_url=f"https://hnd-{uuid.uuid4().hex}.example/d",
                                    label="handler", email="ops@example.com",
                                    proxy_enabled=True)
        db.session.add_all([provider, account])
        db.session.commit()
        db.session.add(AcmeDomain(domain="example.com", dns_provider_id=provider.id))
        key = AcmeDnsUpdateKey(acme_client_account_id=account.id, name="k1.example.",
                               algorithm="hmac-sha256", status="active")
        key.secret = base64.b64encode(SECRET).decode()
        db.session.add(key)
        order = AcmeClientOrder(
            domains=json.dumps(["app.example.com"]), environment="staging",
            challenge_type="dns-01", status="pending", is_proxy_order=True,
            order_url="https://up.example/o/1", upstream_order_url="https://up.example/o/1",
            account_id="acct-int", client_jwk_thumbprint="thumb",
            acme_client_account_id=account.id)
        db.session.add(order)
        db.session.commit()
        row = AcmeProxyDnsChallenge(
            order_id=order.id, acme_client_account_id=account.id, account_id="acct-int",
            client_jwk_thumbprint="thumb", identifier="app.example.com",
            record_name=RECORD1, txt_value=VALUE1, zone_name=ZONE, status="pending",
            expires_at=utc_now() + timedelta(hours=1))
        db.session.add(row)
        db.session.commit()
        r.db, r.key_id, r.row_id = db, key.id, row.id
        r.AcmeDnsUpdateKey, r.AcmeProxyDnsChallenge, r.AuditLog = (
            AcmeDnsUpdateKey, AcmeProxyDnsChallenge, AuditLog)
        r.key_store, r.zone_index = keys.KeyStore(), zones.ZoneIndex()
        # Audit rows of this test only (rows are never deleted: hash chain).
        r.audit_mark = db.session.query(db.func.max(AuditLog.id)).scalar() or 0
        r.cache = records.ActiveRecordCache()
        r.records, r.audit_mod = records, audit_mod

        class SqlCounter:
            n = 0

            def __enter__(self):
                event.listen(db.engine, "before_cursor_execute", self._hit)
                return self

            def __exit__(self, *a):
                event.remove(db.engine, "before_cursor_execute", self._hit)

            def _hit(self, *a, **kw):
                self.n += 1

        r.SqlCounter = SqlCounter
        yield r
        db.session.rollback()
        AcmeProxyDnsChallenge.query.delete()
        AcmeDnsUpdateKey.query.delete()
        AcmeClientOrder.query.filter(AcmeClientOrder.id > floor).delete(
            synchronize_session=False)
        AcmeDomain.query.filter_by(domain="example.com").delete()
        DnsProvider.query.filter_by(id=provider.id).delete()
        AcmeClientAccount.query.filter_by(id=account.id).delete()
        # Audit rows stay: the log is a hash chain that later tests verify.
        db.session.commit()


class _TestHandler(DnsUpdateHandler):
    def send(self, wire, transport="udp", peer=PEER):
        return self.handle(wire, peer, transport)


def real_handler(real, audit):
    return _TestHandler(key_store=real.key_store, zone_index=real.zone_index, audit=audit,
                            snapshot_fn=real.cache.snapshot, clock=lambda: float(NOW),
                            log_sampler=LogSampler())


def test_N8_unsigned_and_badkey_traffic_makes_no_sql_neg(real):
    hh = real_handler(real, FakeAudit())
    real.key_store.lookup(dns.name.from_text("k1.example."))  # warm the caches
    real.zone_index.zones()
    real.cache.snapshot()
    soa = plain(soa_query(ZONE)).wire
    badkey = sign(good_update(), key=KEYU).wire
    with real.SqlCounter() as counter:
        for _ in range(1000):
            assert hh.handle(soa, PEER, "udp") is not None
        for _ in range(1000):
            raw = hh.handle(badkey, PEER, "udp")
            assert parse(raw).tsig[0].error == dns.rcode.BADKEY
        for _ in range(100):
            assert parse(hh.handle(plain(good_update()).wire, PEER, "udp")).rcode() \
                == dns.rcode.REFUSED
    assert counter.n == 0


def test_N8_signed_update_does_use_the_database_pos(real):
    """The counter works: a signed accepted update writes (mark and touch)."""
    hh = real_handler(real, FakeAudit())
    real.key_store.lookup(dns.name.from_text("k1.example."))
    real.zone_index.zones()
    real.cache.snapshot()
    req = sign(good_update())
    with real.SqlCounter() as counter:
        verified(hh.handle(req.wire, PEER, "tcp"), req)
    assert counter.n > 0


def test_end_to_end_signed_add_confirms_row_pos_and_neg(real):
    sink = real.audit_mod.AuditSink()
    hh = real_handler(real, sink)
    hh._mark_confirmed = real.records.mark_confirmed
    row = real.AcmeProxyDnsChallenge.query.get(real.row_id)
    assert row.client_confirmed_at is None
    # neg: a wrong value changes nothing in the database
    bad = sign(upd(adds=[(RECORD1, 60, VALUE2)]))
    assert verified(hh.handle(bad.wire, PEER, "udp"), bad).rcode() == dns.rcode.REFUSED
    real.db.session.expire_all()
    assert real.AcmeProxyDnsChallenge.query.get(real.row_id).client_confirmed_at is None
    refused = real.AuditLog.query.filter(real.AuditLog.id > real.audit_mark).filter_by(
        action="acme.dns_update.refused").all()
    assert len(refused) == 1 and refused[0].ip_address == PEER
    assert refused[0].username == "dns-update:k1.example."
    # pos
    req = sign(good_update())
    assert verified(hh.handle(req.wire, PEER, "udp"), req).rcode() == dns.rcode.NOERROR
    real.db.session.expire_all()
    assert real.AcmeProxyDnsChallenge.query.get(real.row_id).client_confirmed_at is not None
    assert real.AcmeDnsUpdateKey.query.get(real.key_id).last_used_at is not None
    accepted = real.AuditLog.query.filter(real.AuditLog.id > real.audit_mark).filter_by(
        action="acme.dns_update.accepted").all()
    assert len(accepted) == 1 and accepted[0].ip_address == PEER
    assert VALUE1 not in (accepted[0].details or "")


def test_audit_authenticated_is_not_limited_per_ip_pos_and_audit_limited_is_neg(real):
    sink = real.audit_mod.AuditSink()
    kw = dict(peer_ip=PEER, keyname="k1.example.", success=True, details={"zone": ZONE})
    for _ in range(3):
        assert sink.audit_authenticated(action="acme.dns_update.accepted", **kw) is True
    assert real.AuditLog.query.filter(real.AuditLog.id > real.audit_mark).filter_by(
        action="acme.dns_update.accepted").count() == 3
    results = [sink.audit_limited(action="acme.dns_update.refused", reason="x", **kw)
               for _ in range(3)]
    assert results == [True, False, False]  # the limited path still limits


def test_integration_ancestor_zone_with_real_zone_index_pos_and_neg(real):
    hh = real_handler(real, FakeAudit())
    assert send_signed(hh, upd(ZONE, adds=[GOOD_ADD])).rcode() == dns.rcode.NOERROR
    assert send_signed(hh, upd("other.org.", adds=[GOOD_ADD])).rcode() == dns.rcode.NOTAUTH
    assert send_signed(hh, upd("com.", adds=[GOOD_ADD])).rcode() == dns.rcode.NOTAUTH


def _confirmed(real, row_id):
    real.db.session.expire_all()
    return real.AcmeProxyDnsChallenge.query.get(row_id).client_confirmed_at


def test_U16_zone_below_acme_domains_entry_goes_on_pos(real):
    hh = real_handler(real, FakeAudit())
    # The entry is example.com; the zone section is app.example.com, the record is below it.
    resp = send_signed(hh, upd("app.example.com.", adds=[GOOD_ADD]))
    assert resp.rcode() == dns.rcode.NOERROR
    assert _confirmed(real, real.row_id) is not None


def test_U16_record_outside_the_zone_below_the_entry_is_notzone_neg(real):
    audit = FakeAudit()
    hh = real_handler(real, audit)
    row = real.AcmeProxyDnsChallenge.query.get(real.row_id)
    other = real.AcmeProxyDnsChallenge(
        order_id=row.order_id, acme_client_account_id=row.acme_client_account_id,
        account_id=row.account_id, client_jwk_thumbprint="thumb",
        identifier="other.example.com", record_name=RECORD2, txt_value=VALUE2,
        zone_name=ZONE, status="pending", expires_at=row.expires_at)
    real.db.session.add(other)
    real.db.session.commit()
    other_id = other.id
    # The key may write both names; the second one is not below the zone section.
    resp = send_signed(hh, upd("app.example.com.", adds=[GOOD_ADD, (RECORD2, 60, VALUE2)]))
    assert resp.rcode() == dns.rcode.NOTZONE
    assert audit.records[-1]["reason"] == "not_in_zone" and not audit.authenticated
    assert _confirmed(real, real.row_id) is None and _confirmed(real, other_id) is None
    assert real.AcmeDnsUpdateKey.query.get(real.key_id).last_used_at is None


@pytest.mark.parametrize("zone", ["app.other.org.", "www.example.org.", "x.com."])
def test_U16_zone_below_another_domain_is_notauth_neg(real, zone):
    audit = FakeAudit()
    hh = real_handler(real, audit)
    resp = send_signed(hh, upd(zone, adds=[GOOD_ADD]))
    assert resp.rcode() == dns.rcode.NOTAUTH
    assert audit.records[-1]["reason"] == "not_authoritative" and not audit.authenticated
    assert _confirmed(real, real.row_id) is None
    assert real.AcmeDnsUpdateKey.query.get(real.key_id).last_used_at is None


def _age_row(real, row_id, status, age):
    from utils.datetime_utils import utc_now

    row = real.AcmeProxyDnsChallenge.query.get(row_id)
    row.status = status
    row.expires_at = utc_now() - age
    real.db.session.commit()
    real.cache.invalidate()


def test_Q8_real_snapshot_closed_row_is_seen_inside_the_grace_pos(real):
    hh = real_handler(real, FakeAudit())
    _age_row(real, real.row_id, "closed", timedelta(hours=23))
    assert len(parse(hh.send(plain(soa_query(ZONE)).wire, "tcp")).answer) == 1
    assert len(parse(hh.send(plain(soa_query(RECORD1)).wire, "tcp")).authority) == 1
    # An add is still refused: the row is not active.
    resp = send_signed(hh, good_update())
    assert resp.rcode() == dns.rcode.REFUSED
    assert _confirmed(real, real.row_id) is None


def test_Q8_real_snapshot_row_past_the_grace_is_refused_neg(real):
    audit = FakeAudit()
    hh = real_handler(real, audit)
    _age_row(real, real.row_id, "closed", timedelta(hours=25))
    for name in (ZONE, RECORD1):
        assert parse(hh.send(plain(soa_query(name)).wire, "tcp")).rcode() == dns.rcode.REFUSED
    assert not audit.authenticated and _confirmed(real, real.row_id) is None


# =============================================================================
# N11: this must stay the last test of the module
# =============================================================================

def test_N11_logs_of_the_whole_module_hold_no_secret_mac_or_value():
    text = "\n".join(LOGGED)
    assert text  # the DEBUG log was captured
    assert "DNS UPDATE listener" in text
    assert MACS_SEEN  # the MACs were collected
    for item in SECRETS_SEEN | VALUES_SEEN | MACS_SEEN:
        assert item not in text, "sensitive item in a log line"


# --- RFC 8945 §4.3.2: the message is read as it was signed -------------------------

def _update_with_name_in_header(ident=0):
    """UPDATE whose record name is "_acme-challenge" + a compression pointer to offset 0
    (the header ID). RFC 1035 §4.1.4 allows pointers only to prior names."""
    hdr = struct.pack("!HHHHHH", ident, 5 << 11, 1, 0, 1, 0)
    zone = b"\x07example\x03com\x00" + struct.pack("!HH", 6, 1)
    txt = b"\x2b" + b"A" * 43
    rr = b"\x0f_acme-challenge\xc0\x00" + struct.pack("!HHIH", 16, 1, 60, len(txt)) + txt
    return hdr + zone + rr


def test_S1_header_id_changed_and_name_in_header_is_formerr_pos(h):
    # Signed with header ID 0 (= original ID); a forwarder or attacker changes the header
    # ID, which the MAC does not cover. The name pointing into the header now reads
    # differently: refuse, before the TSIG check and without side effects.
    req = sign_wire(_update_with_name_in_header(0))
    changed = struct.pack("!H", 0x0261) + req.wire[2:]
    # Header ID 0x0261 still parses, but the name becomes "_acme-challenge.a\(." instead of
    # "_acme-challenge.", and the MAC still verifies.
    assert [r.name.to_text() for r in parse(changed).update] != \
        [r.name.to_text() for r in parse(req.wire).update]
    raw = h.send(changed)
    assert raw is not None and parse(raw).rcode() == dns.rcode.FORMERR
    assert parse(raw).tsig is None
    assert h.quiet()


def test_S1_header_id_changed_on_a_normal_message_is_processed_neg(h):
    # A normal signed message with another header ID (as a forwarder may send it) reads
    # the same in its signed form and is processed.
    req = sign(good_update())
    other = (struct.unpack("!H", req.wire[:2])[0] + 7) & 0xFFFF
    raw = h.send(struct.pack("!H", other) + req.wire[2:])
    resp = verified(raw, req)
    assert resp.rcode() == dns.rcode.NOERROR and resp.id == other
    assert len(h.marks) == 1


def test_S1_name_in_header_with_unchanged_id_is_not_formerr_neg(h):
    # Same message without a header change: the signed form is the received form, so the
    # check does not apply (the record name is then simply not an accepted one).
    req = sign_wire(_update_with_name_in_header(0))
    raw = h.send(req.wire)
    assert parse(raw).rcode() != dns.rcode.FORMERR
