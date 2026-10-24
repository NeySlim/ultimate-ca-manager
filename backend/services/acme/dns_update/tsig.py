"""Server-side TSIG (RFC 8945) for the DNS UPDATE listener.

dnspython validates a TSIG in the wrong order for a server: it checks the time
before the MAC, and it signs error responses with the server time and the
wrong request MAC. This module therefore parses with ``keyring=False`` (no
validation by dnspython) and does the checks itself in the order of
RFC 8945 §5.2: key, MAC size, MAC, replay, time, truncation policy. It uses only the
public dnspython API (``dns.tsig.sign``, ``dns.tsig.validate``).

The module never logs and never puts a secret or a MAC in a ``repr``.
"""

import collections
import copy
import enum
import hmac
import io
import secrets
import struct
import threading
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

import dns.exception
import dns.flags
import dns.message
import dns.name
import dns.rcode
import dns.rdataclass
import dns.rdatatype
import dns.rdtypes.ANY.TSIG
import dns.rrset
import dns.tsig
import dns.wire

from .constants import (
    ALLOWED_TSIG_ALGORITHMS,
    MAX_FUDGE,
    RESPONSE_FUDGE,
    SECRET_LENGTHS,
)

_HEADER = struct.Struct("!HHHHHH")
_MIN_MAC = 10  # RFC 8945 §5.2.2.1: at least 10 octets
_WIRE_LIMIT = 65535
_TSIG_RESERVE = 400  # room for the TSIG RR: key name (up to 255), algorithm, MAC


@dataclass(frozen=True, repr=False)
class TsigKeyMaterial:
    """A TSIG key that the lookup function returns to the verifier."""

    key_id: int
    name: dns.name.Name
    algorithm: dns.name.Name
    secret: bytes

    def __repr__(self) -> str:
        return (f"TsigKeyMaterial(key_id={self.key_id!r}, name={self.name.to_text()!r}, "
                f"algorithm={self.algorithm.to_text()!r})")


class TsigOutcome(enum.Enum):
    UNSIGNED = "unsigned"
    OK = "ok"
    FORMERR = "formerr"
    BADKEY = "badkey"
    BADSIG = "badsig"
    BADTIME = "badtime"
    BADTRUNC = "badtrunc"


@dataclass(repr=False)
class TsigResult:
    """Outcome of ``verify_request`` and the data that the render functions need."""

    outcome: TsigOutcome
    key: Optional[TsigKeyMaterial] = None
    keyname: Optional[dns.name.Name] = None
    rdata: Optional[dns.rdtypes.ANY.TSIG.TSIG] = None
    request_mac: bytes = b""
    replayed: bool = False

    def __repr__(self) -> str:
        return (f"TsigResult(outcome={self.outcome.name}, key={self.key!r}, "
                f"keyname={self.keyname.to_text() if self.keyname is not None else None!r})")


class TimeWatermark:
    """The most recent Time Signed for each key (RFC 8945 §5.2.3, SHOULD).

    Bounded: the least recently used key is dropped when the table is full.
    """

    def __init__(self, max_keys: int = 4096):
        if max_keys < 1:
            raise ValueError("max_keys must be positive")
        self._max_keys = max_keys
        self._times: "collections.OrderedDict[int, int]" = collections.OrderedDict()
        self._lock = threading.Lock()

    def is_older(self, key_id: int, time_signed: int) -> bool:
        """True if time_signed is strictly earlier than the stored value."""
        with self._lock:
            stored = self._times.get(key_id)
            return stored is not None and time_signed < stored

    def record(self, key_id: int, time_signed: int) -> None:
        with self._lock:
            stored = self._times.get(key_id)
            if stored is not None and stored > time_signed:
                time_signed = stored
            self._times[key_id] = time_signed
            self._times.move_to_end(key_id)
            while len(self._times) > self._max_keys:
                self._times.popitem(last=False)


def _last_rr(wire: bytes) -> Tuple[int, int]:
    """Return (offset, type) of the last RR of the message."""
    last, last_type, _ttl = _last_rr_header(wire)
    return last, last_type


def _last_rr_header(wire: bytes) -> Tuple[int, int, int]:
    """Return (offset, type, TTL) of the last RR of the message.

    dnspython stores the TTL of a TSIG RR as 0 whatever the wire says, and the MAC
    does not cover it, so the TTL check of RFC 8945 §4.2 reads the wire."""
    p = dns.wire.Parser(wire)
    _id, _flags, qd, an, ns, ar = _HEADER.unpack(p.get_bytes(12))
    for _ in range(qd):
        p.get_name()
        p.get_bytes(4)
    last = -1
    last_type = -1
    last_ttl = -1
    for _ in range(an + ns + ar):
        last = p.current
        p.get_name()
        last_type, _cls, last_ttl, rdlen = struct.unpack("!HHIH", p.get_bytes(10))
        p.get_bytes(rdlen)
    if last < 0:
        raise dns.exception.FormError("message has no resource record")
    return last, last_type, last_ttl


def tsig_start_offset(wire: bytes) -> int:
    """Offset of the last RR of the additional section (where a TSIG RR starts)."""
    return _last_rr(wire)[0]


def _dns_key(key: TsigKeyMaterial) -> dns.tsig.Key:
    return dns.tsig.Key(key.name, key.secret, key.algorithm)


def verify_request(wire: bytes, msg: dns.message.Message,
                   lookup_key: Callable[[dns.name.Name], Optional[TsigKeyMaterial]],
                   now: int, watermark: TimeWatermark,
                   is_replay: Optional[Callable[[], bool]] = None) -> TsigResult:
    """Check the TSIG of a request in the order of RFC 8945 §5.2.

    ``msg`` is ``dns.message.from_wire(wire, keyring=False)``: dnspython does
    not validate anything then and keeps the TSIG in ``msg.tsig``.

    Order: key, MAC size, MAC, replay, time, truncation policy. ``is_replay``
    is called only after the MAC verified. When it returns True the result is
    OK with ``replayed=True``: no time check, no truncation check, and the
    watermark is not changed. The replay key is the key name and the request MAC;
    the header ID is not part of it. Security: only a message whose MAC verified
    and that was already answered within REPLAY_TTL_S can skip the time check.
    On the same transport the caller sends the stored response with the header
    ID of the new request. On the other transport the caller processes the
    request again against the current snapshot, with the side effects
    suppressed (no mark_confirmed, no touch of the key, no audit event).
    """
    if msg.tsig is None or len(msg.tsig) == 0:
        return TsigResult(TsigOutcome.UNSIGNED)
    owner = msg.tsig.name
    rdata = msg.tsig[0]
    result = TsigResult(TsigOutcome.FORMERR, keyname=owner, rdata=rdata,
                        request_mac=bytes(rdata.mac))

    # §4.2: the Error field of a request must be zero, and the TTL of the TSIG RR
    # must be 0 (the MAC does not cover the TTL; dnspython does not keep it).
    if rdata.error != 0:
        return result
    try:
        if _last_rr_header(wire)[2] != 0:
            return result
    except (dns.exception.DNSException, struct.error, ValueError, IndexError):
        return result

    # §5.2.1: key and algorithm.
    key = lookup_key(owner)
    if key is None:
        result.outcome = TsigOutcome.BADKEY
        return result
    if (rdata.algorithm != key.algorithm
            or key.algorithm not in ALLOWED_TSIG_ALGORITHMS
            or not key.secret):
        result.outcome = TsigOutcome.BADKEY
        return result

    # §5.2.2.1: MAC size.
    full = dns.tsig.mac_sizes[key.algorithm]
    m = len(rdata.mac)
    if m > full or m < max(_MIN_MAC, full // 2):
        return result

    # §5.2.2: MAC, before the time (the order of §5.2).
    try:
        start, last_type = _last_rr(wire)
    except Exception:
        return result
    if last_type != dns.rdatatype.TSIG:
        return result
    dkey = _dns_key(key)
    if m == full:
        try:
            # now=time_signed switches off the time check of dnspython.
            dns.tsig.validate(wire, dkey, owner, rdata, rdata.time_signed, b"", start)
        except dns.tsig.BadSignature:
            result.outcome = TsigOutcome.BADSIG
            return result
        except (dns.tsig.BadKey, dns.tsig.BadAlgorithm):
            result.outcome = TsigOutcome.BADKEY
            return result
        except Exception:
            return result
    else:
        try:
            arcount = struct.unpack("!H", wire[10:12])[0]
            if arcount == 0:
                return result
            new_wire = wire[0:10] + struct.pack("!H", arcount - 1) + wire[12:start]
            signed, _ctx = dns.tsig.sign(new_wire, dkey, rdata,
                                         time=rdata.time_signed, request_mac=b"")
        except Exception:
            return result
        if not hmac.compare_digest(signed.mac[:m], bytes(rdata.mac)):
            result.outcome = TsigOutcome.BADSIG
            return result

    # The MAC is valid: the key is known to be the one that signed.
    result.key = key

    # A request that was already answered (same key name and request MAC): no time
    # check. The caller sends the stored response (same transport) or processes the
    # request again without side effects (other transport).
    if is_replay is not None and is_replay():
        result.replayed = True
        result.outcome = TsigOutcome.OK
        return result

    # §5.2.3, §10: time.
    window = min(rdata.fudge, MAX_FUDGE)
    if abs(now - rdata.time_signed) > window:
        result.outcome = TsigOutcome.BADTIME
        return result
    if watermark.is_older(key.key_id, rdata.time_signed):
        result.outcome = TsigOutcome.BADTIME
        return result

    # §5.2.4: local policy needs the full MAC.
    if m < full:
        result.outcome = TsigOutcome.BADTRUNC
        return result

    watermark.record(key.key_id, rdata.time_signed)
    result.outcome = TsigOutcome.OK
    return result


def generate_secret(algorithm: dns.name.Name) -> bytes:
    """A random secret as long as the hash output of the algorithm."""
    try:
        length = SECRET_LENGTHS[algorithm]
    except KeyError:
        raise ValueError("TSIG algorithm is not allowed") from None
    return secrets.token_bytes(length)


# --- rendering ---------------------------------------------------------------

def _tsig_rdata(algorithm: dns.name.Name, time_signed: int, fudge: int, mac: bytes,
                original_id: int, error: int, other: bytes = b""):
    return dns.rdtypes.ANY.TSIG.TSIG(dns.rdataclass.ANY, dns.rdatatype.TSIG, algorithm,
                                     time_signed, fudge, mac, original_id, error, other)


def _append_tsig(body: bytes, owner: dns.name.Name, rdata) -> bytes:
    rrset = dns.rrset.from_rdata(owner, 0, rdata)
    f = io.BytesIO()
    count = rrset.to_wire(f)
    arcount = struct.unpack("!H", body[10:12])[0] + count
    return body[:10] + struct.pack("!H", arcount) + body[12:] + f.getvalue()


def _sign_and_append(body: bytes, key: TsigKeyMaterial, template, time: int,
                     request_mac: bytes) -> bytes:
    signed, _ctx = dns.tsig.sign(body, _dns_key(key), template, time=time,
                                 request_mac=request_mac)
    return _append_tsig(body, key.name, signed)


def _copy(response: dns.message.Message) -> dns.message.Message:
    """A copy that shares no mutable state (sections, OPT) with the caller's skeleton."""
    out = copy.copy(response)
    out.sections = [list(section) for section in response.sections]
    if response.opt is not None:
        out.opt = response.opt.copy()
    return out


def _with_rcode(response: dns.message.Message, rcode: int) -> dns.message.Message:
    """A copy of the skeleton with a new RCODE; the caller's object stays as is."""
    out = _copy(response)
    out.set_rcode(rcode)
    return out


def _require_key(result: TsigResult) -> TsigKeyMaterial:
    if result.key is None or result.rdata is None:
        raise ValueError("a validated key is required to sign a response")
    return result.key


def _truncated_form(response: dns.message.Message) -> dns.message.Message:
    """RFC 8945 §5.3: question and OPT only, TC set, RCODE NOERROR."""
    out = _copy(response)
    out.answer = []
    out.authority = []
    out.additional = []
    out.flags |= dns.flags.TC
    out.set_rcode(dns.rcode.NOERROR)
    return out


def render_signed(response: dns.message.Message, result: TsigResult, now: int,
                  max_size: Optional[int] = None) -> Optional[bytes]:
    """Render a response and sign it with the key of the request.

    An oversize response becomes the truncated form of RFC 8945 §5.3. When even
    that form is larger than ``max_size``, the result is None (no response)."""
    key = _require_key(result)
    template = _tsig_rdata(key.algorithm, now, RESPONSE_FUDGE, b"", response.id, 0)
    # The size limit is the caller's max_size, not the EDNS payload that dnspython
    # would take from the request: an oversize response becomes the §5.3 form.
    out = None
    try:
        body = response.to_wire(max_size=_WIRE_LIMIT - _TSIG_RESERVE)
        out = _sign_and_append(body, key, template, now, result.request_mac)
    except dns.exception.TooBig:
        pass
    if out is None or (max_size is not None and len(out) > max_size):
        out = _sign_and_append(_truncated_form(response).to_wire(max_size=_WIRE_LIMIT), key,
                               template, now, result.request_mac)
        if max_size is not None and len(out) > max_size:
            return None
    return out


def render_unsigned_tsig_error(response: dns.message.Message, result: TsigResult,
                               error: int) -> bytes:
    """BADKEY or BADSIG answer: NOTAUTH and a TSIG RR without a MAC (RFC 8945 §5.3.1)."""
    if error not in (dns.rcode.BADKEY, dns.rcode.BADSIG):
        raise ValueError("only BADKEY and BADSIG can be sent unsigned")
    if result.rdata is None or result.keyname is None:
        raise ValueError("the request has no TSIG")
    rd = result.rdata
    body = _with_rcode(response, dns.rcode.NOTAUTH).to_wire()
    trd = _tsig_rdata(rd.algorithm, rd.time_signed, rd.fudge, b"", response.id, error)
    return _append_tsig(body, result.keyname, trd)


def render_badtime(response: dns.message.Message, result: TsigResult, now: int) -> bytes:
    """BADTIME answer, signed (RFC 8945 §5.3.2): the client time, the server time in Other."""
    key = _require_key(result)
    rd = result.rdata
    other = struct.pack("!HI", (now >> 32) & 0xFFFF, now & 0xFFFFFFFF)
    template = _tsig_rdata(key.algorithm, rd.time_signed, rd.fudge, b"", response.id,
                           dns.rcode.BADTIME, other)
    body = _with_rcode(response, dns.rcode.NOTAUTH).to_wire()
    return _sign_and_append(body, key, template, rd.time_signed, result.request_mac)


def render_badtrunc(response: dns.message.Message, result: TsigResult, now: int) -> bytes:
    """BADTRUNC answer, signed over the truncated request MAC (RFC 8945 §5.3.2)."""
    key = _require_key(result)
    template = _tsig_rdata(key.algorithm, now, RESPONSE_FUDGE, b"", response.id,
                           dns.rcode.BADTRUNC)
    body = _with_rcode(response, dns.rcode.NOTAUTH).to_wire()
    return _sign_and_append(body, key, template, now, result.request_mac)
