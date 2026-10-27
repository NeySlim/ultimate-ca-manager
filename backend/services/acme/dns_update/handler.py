"""Protocol handler of the DNS UPDATE (RFC 2136) listener: bytes in, bytes out.

``DnsUpdateHandler.handle`` is a pure function of the request bytes and of the
state that is injected into it. It opens no socket and makes no outgoing call.
The processing order of ``_handle`` is:

1. short message or QR set: no response (M1, M2)
2. size and header counts: no response (N9)
3. opcode other than QUERY and UPDATE: NOTIMP, header only (M3)
4. parse; any error: FORMERR, header only (M4, S1, E2)
5. TSIG (RFC 8945 §5.2); errors are answered here (S2 to S9)
6. replay cache for verified requests (S15)
7. EDNS version above 0: BADVERS (E3)
8. QUERY (only SOA discovery is answered, every other query is REFUSED) or UPDATE
   (checked and answered; nothing is written to DNS)
9. flags of the response (M6 to M8, E1, E4, E5)
10. rendering and size limits (T1, T2, S12)
11. side effects and audit, after the response is decided
12. any unexpected exception: SERVFAIL (N10), signed when the TSIG was verified
    (RFC 8945 §5.3), header only otherwise

The handler never logs packet bytes, MACs, TXT values or keys.
"""

import collections
import copy
import functools
import logging
import struct
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import dns.exception
import dns.flags
import dns.message
import dns.name
import dns.opcode
import dns.rcode
import dns.rdataclass
import dns.rdatatype
import dns.rdtypes.ANY.SOA
import dns.rrset
import dns.wire

from . import audit as audit_module
from . import keys, records, tsig, zones
from .constants import (
    CHALLENGE_LABEL,
    MAX_ANCOUNT,
    MAX_ARCOUNT,
    MAX_MESSAGE_SIZE,
    MAX_NSCOUNT,
    MAX_QDCOUNT,
    REPLAY_CACHE_SIZE,
    REPLAY_TTL_S,
    SOA_TIMERS,
)
from .tsig import TimeWatermark, TsigOutcome

logger = logging.getLogger(__name__)

_HEADER = struct.Struct("!HHHHHH")
_QR = 0x8000
_RD = 0x0100
_MIN_UDP = 512
_WIRE_LIMIT = 65535
_PARSE_ERRORS = (dns.exception.DNSException, ValueError, TypeError, IndexError,
                 struct.error, UnicodeError)
_IN = dns.rdataclass.IN
_ANY = dns.rdataclass.ANY
_NONE = dns.rdataclass.NONE
_MAX_AUDIT_NAMES = 8


# --- sampled application log ---------------------------------------------------

class LogSampler:
    """At most one log line per reason per interval, plus counters."""

    def __init__(self, interval_s: float = 10.0, clock=time.monotonic, log=logger):
        self._interval = interval_s
        self._clock = clock
        self._log = log
        self._lock = threading.Lock()
        self._counts: Dict[str, int] = {}
        self._last: Dict[str, float] = {}

    def note(self, reason: str, level: int = logging.INFO, peer_ip: Optional[str] = None,
             detail: Optional[str] = None) -> bool:
        """Count the event; log it when the interval for the reason has passed."""
        with self._lock:
            self._counts[reason] = self._counts.get(reason, 0) + 1
            now = self._clock()
            last = self._last.get(reason)
            if last is not None and now - last < self._interval:
                return False
            self._last[reason] = now
            total = self._counts[reason]
        try:
            self._log.log(level, "DNS UPDATE listener: %s (peer=%s, total=%d)%s", reason,
                          _safe_text(peer_ip), total, f" [{detail}]" if detail else "")
        except Exception:
            pass
        return True

    def counts(self) -> Dict[str, int]:
        with self._lock:
            return dict(self._counts)


def _safe_text(value) -> str:
    return audit_module.sanitize_text(value if value is not None else "-", 64)


# --- replay cache (S15) ----------------------------------------------------------

class ReplayCache:
    """Bounded LRU of final responses with a time to live. Thread safe.

    The key is (key name, request MAC) of a signed request. Per key it keeps one
    response per transport, and the set of keys that are being processed right now."""

    def __init__(self, size: int = REPLAY_CACHE_SIZE, ttl_s: float = REPLAY_TTL_S,
                 clock=time.time):
        if size < 1:
            raise ValueError("size must be positive")
        self._size = size
        self._ttl = ttl_s
        self._clock = clock
        self._lock = threading.Lock()
        self._items: "collections.OrderedDict[object, Tuple[float, Dict[str, bytes]]]" = (
            collections.OrderedDict())
        self._in_flight = set()

    def _live(self, key):
        """The entry of the key, or None. Drops an expired entry. Call under the lock."""
        item = self._items.get(key)
        if item is None:
            return None
        if self._clock() - item[0] >= self._ttl:
            del self._items[key]
            return None
        return item

    def get(self, key, transport: str = "") -> Optional[bytes]:
        """The response stored for this key and transport, or None."""
        with self._lock:
            item = self._live(key)
            if item is None:
                return None
            value = item[1].get(transport)
            if value is not None:
                self._items.move_to_end(key)
            return value

    def seen(self, key) -> bool:
        """True when a live entry exists for the key, for any transport."""
        with self._lock:
            return self._live(key) is not None

    def put(self, key, value: bytes, transport: str = "") -> None:
        with self._lock:
            item = self._live(key)
            if item is None:
                item = (self._clock(), {})
                self._items[key] = item
            item[1][transport] = value
            self._items.move_to_end(key)
            while len(self._items) > self._size:
                self._items.popitem(last=False)

    def begin(self, key) -> bool:
        """Mark the key as in flight. False when it already is."""
        with self._lock:
            if key in self._in_flight:
                return False
            self._in_flight.add(key)
            return True

    def end(self, key) -> None:
        with self._lock:
            self._in_flight.discard(key)

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


# --- helpers ----------------------------------------------------------------------

@dataclass
class _Event:
    """What happens after the response is decided (step 11 of `_handle`)."""

    kind: str = "none"  # none | accepted | refused
    reason: str = ""
    zone: str = ""
    names: List[str] = field(default_factory=list)
    adds: int = 0
    deletes: int = 0
    row_ids: List[int] = field(default_factory=list)


_NO_EVENT = _Event()


def _header_only(wire: bytes, rcode: int) -> bytes:
    """ID, opcode and RD of the request; QR=1; all counts 0."""
    ident, flags = struct.unpack_from("!HH", wire)
    opcode = (flags >> 11) & 0xF
    out = _QR | (opcode << 11) | (flags & _RD) | (rcode & 0xF)
    return _HEADER.pack(ident, out, 0, 0, 0, 0)


@functools.lru_cache(maxsize=4096)
def _name_of(text: str) -> dns.name.Name:
    """Parsed name of a database row (never of a packet), cached."""
    return dns.name.from_text(text)


def _soa_rrset(zone: dns.name.Name) -> dns.rrset.RRset:
    """The SOA record of a zone: MNAME = the zone, RNAME = hostmaster.<zone>, the fixed
    ``SOA_TIMERS``, TTL 0. No UCM host name and no time in it."""
    mname = zone
    rname = dns.name.Name((b"hostmaster",) + zone.labels)
    serial, refresh, retry, expire, minimum = SOA_TIMERS
    rdata = dns.rdtypes.ANY.SOA.SOA(_IN, dns.rdatatype.SOA, mname, rname, serial, refresh,
                                    retry, expire, minimum)
    return dns.rrset.from_rdata(zone, 0, rdata)


def _truncated(resp: dns.message.Message) -> dns.message.Message:
    """Question and OPT only, TC set, same RCODE (RFC 1035 §4.2.1)."""
    out = copy.copy(resp)
    out.sections = [list(s) for s in resp.sections]
    out.answer = []
    out.authority = []
    out.additional = []
    out.flags |= dns.flags.TC
    return out


def _update_rrs(wire: bytes) -> List[Tuple[dns.name.Name, int, int, int, int]]:
    """(name, type, class, ttl, rdlength) of each RR of the update section.

    dnspython keeps neither the TTL of a delete of class ANY nor the RDLENGTH, and
    RFC 2136 §3.4.1 needs both for the prescan."""
    p = dns.wire.Parser(wire)
    _id, _flags, zocount, prcount, upcount, _ar = _HEADER.unpack(p.get_bytes(12))
    for _ in range(zocount):
        p.get_name()
        p.get_bytes(4)
    for _ in range(prcount):
        p.get_name()
        _t, _c, _ttl, rdlen = p.get_struct("!HHIH")
        p.get_bytes(rdlen)
    out = []
    for _ in range(upcount):
        name = p.get_name()
        rtype, rclass, ttl, rdlen = p.get_struct("!HHIH")
        p.get_bytes(rdlen)
        out.append((name, rtype, rclass, ttl, rdlen))
    return out


def _same_in_signed_form(wire: bytes, msg: dns.message.Message) -> bool:
    """True unless the message reads differently with the original ID of its TSIG.

    Only a signed message whose header ID differs from that original ID is parsed
    again (a forwarder may change the header ID, RFC 8945 §4.3.2)."""
    if msg.tsig is None or len(msg.tsig) == 0 or msg.tsig[0].original_id == msg.id:
        return True
    signed_form = struct.pack("!H", msg.tsig[0].original_id) + wire[2:]
    try:
        again = dns.message.from_wire(signed_form, keyring=False)
    except _PARSE_ERRORS:
        return False
    return (again.sections == msg.sections and again.tsig == msg.tsig
            and again.edns == msg.edns and again.payload == msg.payload)


def _replay_key(msg: dns.message.Message) -> Optional[Tuple[str, bytes]]:
    """(key name, request MAC) of a signed message, or None (S15).

    The MAC covers the whole message and the original ID, but not the header ID
    (RFC 8945 §4.3.2), so a copy resent with another header ID is the same request.
    Two different requests with the same MAC would need an HMAC collision."""
    if msg.tsig is None or len(msg.tsig) == 0:
        return None
    return (msg.tsig.name.to_text().lower(), bytes(msg.tsig[0].mac))


def _with_request_id(cached: bytes, wire: bytes) -> bytes:
    """The stored response with the header ID of this request. The TSIG of the
    response keeps the original ID, so the MAC still verifies (RFC 8945 §4.3.2)."""
    return wire[:2] + cached[2:]


def _txt_value(rdata) -> Optional[str]:
    """TXT value as ASCII text (strings joined, RFC 1035 §3.3.14), or None."""
    try:
        return b"".join(rdata.strings).decode("ascii")
    except UnicodeDecodeError:
        return None


def _utc_naive(t: float) -> datetime:
    return datetime.fromtimestamp(t, tz=timezone.utc).replace(tzinfo=None)


class DnsUpdateHandler:
    def __init__(self, *, key_store=keys.key_store, zone_index=zones.zone_index,
                 audit=audit_module.audit_sink, snapshot_fn=records.get_active_snapshot,
                 mark_confirmed_fn=records.mark_confirmed, clock=time.time,
                 watermark: Optional[TimeWatermark] = None, replay_cache=None,
                 log_sampler=None):
        self._key_store = key_store
        self._zone_index = zone_index
        self._audit = audit
        self._snapshot_fn = snapshot_fn
        self._mark_confirmed = mark_confirmed_fn
        self._clock = clock
        self._watermark = watermark if watermark is not None else TimeWatermark()
        self._replay = replay_cache if replay_cache is not None else ReplayCache(clock=clock)
        self._log = log_sampler if log_sampler is not None else LogSampler()
        self._index_lock = threading.Lock()
        self._index_snapshot = None
        self._by_zone: Dict[str, tuple] = {}

    def _rows_by_zone(self, snapshot) -> Dict[str, tuple]:
        """SOA rows of the snapshot grouped by zone text, built once per snapshot object."""
        with self._index_lock:
            if snapshot is not self._index_snapshot:
                index: Dict[str, list] = {}
                for row in snapshot.soa_rows:
                    index.setdefault(row.zone_name, []).append(row)
                self._by_zone = {k: tuple(v) for k, v in index.items()}
                self._index_snapshot = snapshot
            return self._by_zone

    # -- entry point ---------------------------------------------------------------

    def handle(self, wire: bytes, peer_ip: str, transport: str) -> Optional[bytes]:
        """Response bytes for one request, or None for "no response". Never raises."""
        try:
            return self._handle(wire, peer_ip, transport)
        except Exception as exc:
            return self._servfail(wire, peer_ip, exc)

    def _servfail(self, wire, peer_ip, exc, signed_ctx=None) -> Optional[bytes]:
        """SERVFAIL for an unexpected exception. ``signed_ctx`` is (msg, result, now_int,
        limit) of a request whose TSIG verified: the answer is then signed (RFC 8945 §5.3)."""
        try:
            self._log.note("servfail", logging.ERROR, peer_ip, type(exc).__name__)
        except Exception:
            pass
        try:
            from models import db
            db.session.rollback()
        except Exception:
            pass
        if signed_ctx is not None:
            try:
                msg, result, now_int, limit = signed_ctx
                resp = self._skeleton(msg)
                resp.question = []
                resp.answer = []
                resp.authority = []
                resp.additional = []
                resp.set_rcode(dns.rcode.SERVFAIL)
                out = tsig.render_signed(resp, result, now_int, max_size=limit)
                if out is not None:
                    return out
            except Exception:
                pass
        try:
            if len(wire) >= 12:
                return _header_only(wire, dns.rcode.SERVFAIL)
        except Exception:
            pass
        return None

    # -- steps 1 to 12 -----------------------------------------------------------------

    def _handle(self, wire: bytes, peer_ip: str, transport: str) -> Optional[bytes]:
        now = self._clock()
        now_int = int(now)

        # 1. Short message, or a response (RFC 1035 §4.1.1).
        if len(wire) < 12:
            self._log.note("short", logging.DEBUG, peer_ip)
            return None
        _ident, flags, qd, an, ns, ar = _HEADER.unpack_from(wire)
        if flags & _QR:
            self._log.note("qr", logging.DEBUG, peer_ip)
            return None

        # 2. Size and counts, before the parser runs.
        if len(wire) > MAX_MESSAGE_SIZE:
            self._log.note("oversize", logging.INFO, peer_ip)
            return None
        # A QUERY has no answer RR; an UPDATE keeps MAX_ANCOUNT (its prerequisite section).
        if (flags >> 11) & 0xF == dns.opcode.QUERY and an != 0:
            self._log.note("counts", logging.INFO, peer_ip)
            return None
        if qd > MAX_QDCOUNT or an > MAX_ANCOUNT or ns > MAX_NSCOUNT or ar > MAX_ARCOUNT:
            self._log.note("counts", logging.INFO, peer_ip)
            return None

        # 3. Opcode: only QUERY and UPDATE are served. Any other opcode gets NOTIMP with
        # the header only; the body is not parsed and no TSIG is added.
        opcode = (flags >> 11) & 0xF
        if opcode not in (dns.opcode.QUERY, dns.opcode.UPDATE):
            self._log.note("notimp", logging.INFO, peer_ip)
            return _header_only(wire, dns.rcode.NOTIMP)

        # 4. Parse without any TSIG validation by dnspython.
        try:
            msg = dns.message.from_wire(wire, keyring=False)
        except _PARSE_ERRORS:
            self._log.note("formerr", logging.INFO, peer_ip)
            return _header_only(wire, dns.rcode.FORMERR)
        # The MAC covers the message with the original ID of the TSIG in place of the
        # header ID (RFC 8945 §4.3.2). A name compressed into the header ID would read
        # differently in the signed form: read that form too, and refuse a difference.
        if not _same_in_signed_form(wire, msg):
            self._log.note("formerr", logging.INFO, peer_ip)
            return _header_only(wire, dns.rcode.FORMERR)

        # 5. TSIG.
        # The replay check runs inside, after the MAC and before the time (RFC 8945 §5.2).
        replay_key = _replay_key(msg)
        result = tsig.verify_request(
            wire, msg, self._key_store.lookup, now_int, self._watermark,
            is_replay=lambda: replay_key is not None and self._replay.seen(replay_key))
        outcome = result.outcome
        if outcome == TsigOutcome.FORMERR:
            self._log.note("formerr", logging.INFO, peer_ip)
            return _header_only(wire, dns.rcode.FORMERR)
        skeleton = self._skeleton(msg)
        if outcome in (TsigOutcome.BADKEY, TsigOutcome.BADSIG, TsigOutcome.BADTIME,
                       TsigOutcome.BADTRUNC):
            return self._tsig_error(wire, msg, skeleton, result, peer_ip, transport, now_int)
        signed = outcome == TsigOutcome.OK

        # 6. Replay. The key is (key name, request MAC); the header ID is not part of it.
        # On the same transport the stored response is sent with the header ID of the new
        # request. On the other transport the request is processed again against the
        # current snapshot, with the side effects suppressed: no mark_confirmed, no
        # touch of the key and no audit event (step 11). A copy that is in flight now
        # gets no response.
        suppress = False
        if signed:
            cached = self._replay.get(replay_key, transport)
            if cached is not None:
                return _with_request_id(cached, wire)
            if not self._replay.begin(replay_key):
                self._log.note("replay_in_flight", logging.DEBUG, peer_ip)
                return None
            try:
                cached = self._replay.get(replay_key, transport)
                if cached is not None:
                    return _with_request_id(cached, wire)
                suppress = result.replayed or self._replay.seen(replay_key)
                return self._process(wire, msg, skeleton, result, opcode, peer_ip, transport,
                                     now, now_int, replay_key, suppress)
            finally:
                self._replay.end(replay_key)
        return self._process(wire, msg, skeleton, result, opcode, peer_ip, transport,
                             now, now_int, None, False)

    def _process(self, wire, msg, skeleton, result, opcode, peer_ip, transport, now, now_int,
                 replay_key, suppress) -> Optional[bytes]:
        signed = result.outcome == TsigOutcome.OK
        tcp = transport == "tcp"
        limit = None if tcp else max(_MIN_UDP, msg.payload if msg.edns >= 0 else _MIN_UDP)
        try:
            # 7. EDNS version.
            event = _NO_EVENT
            if msg.edns > 0:
                resp = skeleton
                resp.set_rcode(dns.rcode.BADVERS)
                self._log.note("badvers", logging.DEBUG, peer_ip)
            elif opcode == dns.opcode.QUERY:
                resp = self._query(msg, skeleton, result, peer_ip)
            else:
                resp, event = self._update(wire, msg, skeleton, result, peer_ip)

            # 9, 10. Flags are set by make_response; render and apply the size limit.
            if signed:
                out = tsig.render_signed(resp, result, now_int, max_size=limit)
                if out is None:
                    self._log.note("udp_drop", logging.INFO, peer_ip)
            else:
                out = self._render_unsigned(resp, self._unsigned_limit(wire, msg, tcp), peer_ip)
        except Exception as exc:
            if not signed:
                raise
            return self._servfail(wire, peer_ip, exc, (msg, result, now_int, limit))
        # Only real bytes are cached. After a udp_drop the side effects below still run
        # (the request was valid). A retransmission finds nothing in the cache and is
        # processed again; its side effects are idempotent (same confirmation, one more
        # audit row). The client can repeat the request over TCP, which has no limit.
        if signed and replay_key is not None and out is not None:
            self._replay.put(replay_key, out, transport)

        # 11. Side effects and audit; not for a copy that was already processed.
        if not suppress:
            self._after(event, result, peer_ip, transport, now)
        return out

    # -- responses ----------------------------------------------------------------------

    @staticmethod
    def _skeleton(msg: dns.message.Message) -> dns.message.Message:
        """QR=1, ID, opcode and RD copied, RA=0, no padding. An UPDATE response has
        no sections at all (RFC 2136 §3.8): the zone section is never echoed."""
        # Advertise the size the listener accepts (RFC 6891 §6.2.5), not dnspython's 8192.
        resp = dns.message.make_response(msg, pad=0, our_payload=MAX_MESSAGE_SIZE)
        if msg.opcode() == dns.opcode.UPDATE:
            resp.question = []
        return resp

    @staticmethod
    def _unsigned_limit(wire: bytes, msg: dns.message.Message, tcp: bool) -> Optional[int]:
        """T1: over UDP, no response is longer than the request (nor above the EDNS size)."""
        if tcp:
            return None
        payload = msg.payload if msg.edns >= 0 else _MIN_UDP
        return min(len(wire), max(_MIN_UDP, payload))

    def _render_unsigned(self, resp: dns.message.Message, limit: Optional[int],
                         peer_ip) -> Optional[bytes]:
        out = resp.to_wire(max_size=_WIRE_LIMIT)
        if limit is None or len(out) <= limit:
            return out
        out = _truncated(resp).to_wire(max_size=_WIRE_LIMIT)
        if len(out) <= limit:
            return out
        self._log.note("udp_drop", logging.INFO, peer_ip)
        return None

    def _tsig_error(self, wire, msg, skeleton, result, peer_ip, transport, now_int):
        outcome = result.outcome
        reason = outcome.value
        tcp = transport == "tcp"
        if outcome == TsigOutcome.BADKEY:
            def render(r):
                return tsig.render_unsigned_tsig_error(r, result, dns.rcode.BADKEY)
        elif outcome == TsigOutcome.BADSIG:
            def render(r):
                return tsig.render_unsigned_tsig_error(r, result, dns.rcode.BADSIG)
        elif outcome == TsigOutcome.BADTIME:
            def render(r):
                return tsig.render_badtime(r, result, now_int)
        else:
            def render(r):
                return tsig.render_badtrunc(r, result, now_int)
        if tcp:
            limit = None
        elif outcome in (TsigOutcome.BADTIME, TsigOutcome.BADTRUNC):
            limit = max(_MIN_UDP, msg.payload if msg.edns >= 0 else _MIN_UDP)
        else:
            limit = self._unsigned_limit(wire, msg, tcp)
        out = render(skeleton)
        if limit is not None and len(out) > limit:
            out = render(_truncated(skeleton))
            if len(out) > limit:
                out = None
                self._log.note("udp_drop", logging.INFO, peer_ip)
        self._log.note(reason, logging.INFO, peer_ip)
        try:
            self._audit.audit_limited(
                action="acme.dns_update.rejected", reason=reason, peer_ip=peer_ip,
                keyname=result.keyname.to_text() if result.keyname is not None else None,
                success=False, details={"transport": transport})
        except Exception:
            pass
        return out

    # -- QUERY -----------------------------------------------------------------

    def _query(self, msg, resp, result, peer_ip) -> dns.message.Message:
        if len(msg.question) != 1:
            # RFC 9619: exactly one question. The response is header only.
            resp.question = []
            resp.set_rcode(dns.rcode.FORMERR)
            self._log.note("formerr", logging.INFO, peer_ip)
            return resp
        self._log.note("query", logging.DEBUG, peer_ip)
        question = msg.question[0]
        if question.rdclass != _IN or question.rdtype != dns.rdatatype.SOA:
            resp.set_rcode(dns.rcode.REFUSED)
            return resp

        snapshot = self._snapshot_fn()
        qname = question.name
        # No zone at or above the name: REFUSED at once, without a loop over the rows.
        snap_zones = snapshot.zones
        by_zone = self._rows_by_zone(snapshot)
        rows = []
        found = False
        probe = qname
        while len(probe.labels) > 1:
            text = probe.to_text().lower()
            if text in snap_zones:
                rows.extend(by_zone.get(text, ()))
                found = True
            probe = probe.parent()
        if not found:
            resp.set_rcode(dns.rcode.REFUSED)
            return resp

        if result.outcome == TsigOutcome.OK:
            scope = self._key_store.scope(result.key.key_id)
            rows = [] if scope is None else [
                r for r in rows if scope.allows(r.acme_client_account_id, r.account_id)]

        # Q1: the apex of a row.
        for row in rows:
            zone = _name_of(row.zone_name)
            if qname == zone:
                resp.flags |= dns.flags.AA
                resp.answer.append(_soa_rrset(zone))
                return resp
        # Q7: a name between the apex and the record name: NODATA (RFC 2308 §2.2).
        for row in rows:
            zone = _name_of(row.zone_name)
            if (qname != zone and qname.is_subdomain(zone)
                    and _name_of(row.record_name).is_subdomain(qname)):
                resp.flags |= dns.flags.AA
                resp.authority.append(_soa_rrset(zone))
                return resp
        resp.set_rcode(dns.rcode.REFUSED)
        return resp

    # -- UPDATE ------------------------------------------------------------------

    def _refuse(self, resp, rcode, reason, zone="", names=()):
        resp.set_rcode(rcode)
        return resp, _Event("refused", reason, zone, list(names))

    def _update(self, wire, msg, resp, result, peer_ip) -> Tuple[dns.message.Message, _Event]:
        # 1. No TSIG: REFUSED at once, before any zone check and without a DB access (U4).
        if result.outcome != TsigOutcome.OK:
            resp.set_rcode(dns.rcode.REFUSED)
            self._log.note("unsigned_update", logging.INFO, peer_ip)
            return resp, _NO_EVENT

        # 2. Zone section (RFC 2136 §3.1.1).
        if len(msg.zone) != 1 or msg.zone[0].rdtype != dns.rdatatype.SOA:
            return self._refuse(resp, dns.rcode.FORMERR, "format")
        zrr = msg.zone[0]
        zone_text = zrr.name.to_text()
        if zrr.rdclass != _IN:
            return self._refuse(resp, dns.rcode.NOTAUTH, "not_authoritative", zone_text)
        if not self._zone_index.is_authoritative(zrr.name):
            return self._refuse(resp, dns.rcode.NOTAUTH, "not_authoritative", zone_text)

        # 3. Prerequisites: policy, nothing to evaluate them against.
        if msg.prerequisite:
            return self._refuse(resp, dns.rcode.REFUSED, "prerequisite", zone_text)

        names: List[str] = []
        for rrset in msg.update:
            text = rrset.name.to_text()
            if text not in names and len(names) < _MAX_AUDIT_NAMES:
                names.append(text)

        # 4. Permission of every RR, before anything is applied (RFC 2136 §3.3).
        reason, row_ids = self._authorize(msg, result)
        if reason is not None:
            return self._refuse(resp, dns.rcode.REFUSED, reason, zone_text, names)

        # 5. Prescan (RFC 2136 §3.4.1), in the order of the RRs.
        rrs = _update_rrs(wire)
        for name, _rtype, rclass, ttl, rdlen in rrs:
            if not name.is_subdomain(zrr.name):
                return self._refuse(resp, dns.rcode.NOTZONE, "not_in_zone", zone_text, names)
            if rclass == _IN:
                continue
            if rclass in (_ANY, _NONE):
                # RFC 2136 §3.4.1.2: class ANY and NONE have TTL 0, class ANY has
                # RDLENGTH 0 (dnspython already refuses RDLENGTH != 0 at parse time).
                if ttl != 0 or (rclass == _ANY and rdlen != 0):
                    return self._refuse(resp, dns.rcode.FORMERR, "format", zone_text, names)
                continue
            return self._refuse(resp, dns.rcode.FORMERR, "format", zone_text, names)

        # 6, 7. Nothing is applied to DNS. NOERROR and no section (U14).
        adds = sum(1 for rr in rrs if rr[2] == _IN)
        return resp, _Event("accepted", "", zone_text, names, adds, len(rrs) - adds,
                            sorted(set(row_ids)))

    def _authorize(self, msg, result) -> Tuple[Optional[str], List[int]]:
        """None and the matching row ids, or the reason code of the refusal."""
        scope = None
        scope_loaded = False
        snapshot = None
        row_ids: List[int] = []
        for rrset in msg.update:
            # "Delete all RRsets from a name" (RFC 2136 §2.5.3: class ANY, type ANY) is a
            # delete like the others. Type ANY with class NONE or IN is not: §3.4.1.2 asks
            # for FORMERR there, but this permission check (§3.3) runs before the prescan
            # (§3.4), so such an RR gets REFUSED.
            delete_all = rrset.rdtype == dns.rdatatype.ANY and rrset.deleting == _ANY
            if ((rrset.rdtype != dns.rdatatype.TXT and not delete_all)
                    or len(rrset.name.labels) < 2
                    or rrset.name.labels[0].lower() != CHALLENGE_LABEL):
                return "type_not_allowed", []
            if rrset.deleting is not None:
                # Deletes (class ANY or NONE) change nothing and are always allowed (U11).
                continue
            if not scope_loaded:
                scope = self._key_store.scope(result.key.key_id)
                snapshot = self._snapshot_fn()
                scope_loaded = True
            candidates = [
                r for r in snapshot.by_name.get(rrset.name.to_text().lower(), ())
                if scope is not None and scope.allows(r.acme_client_account_id, r.account_id)]
            if not candidates:
                return "no_pending_order", []
            for rdata in rrset:
                value = _txt_value(rdata)
                matched = [r.row_id for r in candidates
                           if value is not None and r.txt_value == value]
                if not matched:
                    return "value_mismatch", []
                row_ids.extend(matched)
        return None, row_ids

    # -- step 11 ---------------------------------------------------------------------------

    def _after(self, event: _Event, result, peer_ip, transport, now: float) -> None:
        if event.kind == "none":
            return
        try:
            keyname = result.key.name.to_text()
            if event.kind == "accepted":
                moment = _utc_naive(now)
                if event.row_ids:
                    self._mark_confirmed(event.row_ids, moment)
                self._key_store.touch(result.key.key_id, moment)
                self._audit.audit_authenticated(
                    action="acme.dns_update.accepted", peer_ip=peer_ip, keyname=keyname,
                    success=True, details=self._details(event, transport))
            else:
                self._audit.audit_limited(
                    action="acme.dns_update.refused", reason=event.reason, peer_ip=peer_ip,
                    keyname=keyname, success=False, details=self._details(event, transport))
        except Exception as exc:
            # The response is decided. A failure here must not change it.
            self._log.note("side_effect", logging.ERROR, peer_ip, type(exc).__name__)
            try:
                from models import db
                db.session.rollback()
            except Exception:
                pass

    @staticmethod
    def _details(event: _Event, transport: str) -> dict:
        details = {"zone": event.zone, "names": event.names, "transport": transport}
        if event.kind == "accepted":
            details["adds"] = event.adds
            details["deletes"] = event.deletes
        return details
