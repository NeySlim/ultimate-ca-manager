"""Tests for the server-side TSIG module of the DNS UPDATE listener (RFC 8945).

Clients are built with dnspython; the server side is the module under test.
The MAC of every signed response is also recomputed here with Python's hmac
module over the RFC 8945 §4.3 digest components. Test names follow the
invariant IDs of the design plan (section 4.2): test_<ID>_<what>_pos/_neg.
"""
import base64
import hashlib
import hmac
import io
import struct
from unittest import mock

import pytest

import dns.flags
import dns.message
import dns.name
import dns.rcode
import dns.rdata
import dns.rdataclass
import dns.rdatatype
import dns.rdtypes.ANY.TSIG
import dns.rrset
import dns.tsig
import dns.update

from services.acme.dns_update.constants import (
    ALLOWED_TSIG_ALGORITHMS,
    MAX_FUDGE,
    RESPONSE_FUDGE,
    SECRET_LENGTHS,
)
from services.acme.dns_update.tsig import (
    TimeWatermark,
    TsigKeyMaterial,
    TsigOutcome,
    TsigResult,
    generate_secret,
    render_badtime,
    render_badtrunc,
    render_signed,
    render_unsigned_tsig_error,
    tsig_start_offset,
    verify_request,
)

NOW = 1_700_000_000
KEYNAME = dns.name.from_text("k1.example.")
SHA256, SHA384, SHA512 = dns.tsig.HMAC_SHA256, dns.tsig.HMAC_SHA384, dns.tsig.HMAC_SHA512
HASHES = {SHA256: hashlib.sha256, SHA384: hashlib.sha384, SHA512: hashlib.sha512}
ALGS = [SHA256, SHA384, SHA512]
SECRETS = {alg: bytes([i + 1]) * SECRET_LENGTHS[alg] for i, alg in enumerate(ALGS)}


# --- helpers -----------------------------------------------------------------

def material(alg=SHA256, name=KEYNAME, key_id=1, secret=None):
    return TsigKeyMaterial(key_id=key_id, name=name, algorithm=alg,
                           secret=SECRETS.get(alg, b"\x07" * 32) if secret is None else secret)


def lookup_for(*keys):
    table = {k.name: k for k in keys}
    return lambda name: table.get(name)


def at(t):
    """Make dnspython think that it is time t, for the client side."""
    return mock.patch.object(dns.message.time, "time", lambda: t)


def client_update(t=NOW, alg=SHA256, secret=None, name=KEYNAME, fudge=300, txt='"abc"',
                  tsig_error=0, signing_alg=None):
    """A signed DNS UPDATE as an independent dnspython client sends it."""
    signing_alg = signing_alg or alg
    secret = secret if secret is not None else SECRETS.get(signing_alg, b"\x07" * 32)
    key = dns.tsig.Key(name, secret, signing_alg)
    u = dns.update.UpdateMessage("example.com.", keyring={key.name: key}, keyname=key.name,
                                 keyalgorithm=signing_alg)
    u.add("_acme-challenge.host.example.com.", 60, "TXT", txt)
    u.use_tsig(key, fudge=fudge, tsig_error=tsig_error)
    with at(t):
        return u.to_wire()


def parse(wire):
    return dns.message.from_wire(wire, keyring=False)


def run(wire, keys, now=NOW, wm=None):
    msg = parse(wire)
    wm = wm or TimeWatermark()
    return verify_request(wire, msg, lookup_for(*keys), now, wm), msg


def flip_mac(wire):
    mac = parse(wire).tsig[0].mac
    i = wire.rfind(mac)
    out = bytearray(wire)
    out[i + len(mac) // 2] ^= 0x01
    return bytes(out)


def with_mac(wire, mac):
    """Replace the MAC of the TSIG RR (the last RR) by `mac`."""
    msg = parse(wire)
    start = tsig_start_offset(wire)
    rr = dns.rrset.from_rdata(msg.tsig.name, 0, msg.tsig[0].replace(mac=mac))
    f = io.BytesIO()
    rr.to_wire(f)
    return wire[:start] + f.getvalue()


def truncated(wire, n, wrong=False):
    mac = parse(wire).tsig[0].mac[:n]
    if wrong:
        mac = bytes([mac[0] ^ 1]) + mac[1:]
    return with_mac(wire, mac)


def skeleton(msg):
    return dns.message.make_response(msg, pad=0)


def digest_mac(resp_wire, request_mac, secret, alg):
    """Recompute the response MAC from RFC 8945 §4.3 with the hmac module only."""
    msg = parse(resp_wire)
    rd = msg.tsig[0]
    rr_io = io.BytesIO()
    msg.tsig.to_wire(rr_io)
    start = len(resp_wire) - len(rr_io.getvalue())
    arcount = struct.unpack("!H", resp_wire[10:12])[0] - 1
    body = resp_wire[:10] + struct.pack("!H", arcount) + resp_wire[12:start]
    h = hmac.new(secret, digestmod=HASHES[alg])
    if request_mac:
        h.update(struct.pack("!H", len(request_mac)) + request_mac)
    h.update(body)
    h.update(msg.tsig.name.canonicalize().to_wire())
    h.update(struct.pack("!HI", dns.rdataclass.ANY, 0))
    h.update(rd.algorithm.canonicalize().to_wire())
    h.update(struct.pack("!HIH", (rd.time_signed >> 32) & 0xFFFF, rd.time_signed & 0xFFFFFFFF,
                         rd.fudge))
    h.update(struct.pack("!HH", rd.error, len(rd.other)) + rd.other)
    return h.digest(), rd


def client_verify(resp_wire, request_mac, key, t=NOW):
    keyobj = dns.tsig.Key(key.name, key.secret, key.algorithm)
    with at(t):
        return dns.message.from_wire(resp_wire, keyring={key.name: keyobj},
                                     request_mac=request_mac)


def ok_case(alg=SHA256, **kw):
    key = material(alg)
    wire = client_update(alg=alg, **kw)
    res, msg = run(wire, [key])
    assert res.outcome is TsigOutcome.OK
    return key, wire, res, msg


# --- UNSIGNED, constants -------------------------------------------------------

def test_unsigned_request_pos():
    u = dns.update.UpdateMessage("example.com.")
    u.add("a.example.com.", 60, "TXT", '"x"')
    wire = u.to_wire()
    res, _ = run(wire, [material()])
    assert res.outcome is TsigOutcome.UNSIGNED and res.key is None


def test_unsigned_request_neg():
    res, _ = run(client_update(), [material()])
    assert res.outcome is not TsigOutcome.UNSIGNED


def test_constants_only_sha2_pos():
    assert ALLOWED_TSIG_ALGORITHMS == {SHA256, SHA384, SHA512}
    assert MAX_FUDGE == 300 and RESPONSE_FUDGE == 300


def test_constants_only_sha2_neg():
    for weak in (dns.tsig.HMAC_MD5, dns.tsig.HMAC_SHA1, dns.tsig.HMAC_SHA224,
                 dns.tsig.HMAC_SHA256_128, dns.tsig.HMAC_SHA384_192,
                 dns.tsig.HMAC_SHA512_256, dns.tsig.GSS_TSIG):
        assert weak not in ALLOWED_TSIG_ALGORITHMS


# --- S2 unknown key ------------------------------------------------------------

def test_S2_known_key_pos():
    res, _ = run(client_update(), [material()])
    assert res.outcome is TsigOutcome.OK
    assert res.key == material() and res.keyname == KEYNAME


def test_S2_unknown_key_neg():
    res, _ = run(client_update(name=dns.name.from_text("other.example.")), [material()])
    assert res.outcome is TsigOutcome.BADKEY
    assert res.key is None and res.keyname == dns.name.from_text("other.example.")


def test_S2_empty_secret_key_neg():
    res, _ = run(client_update(), [material(secret=b"")])
    assert res.outcome is TsigOutcome.BADKEY


# --- S3 algorithm ----------------------------------------------------------------

@pytest.mark.parametrize("alg", ALGS)
def test_S3_allowed_algorithm_pos(alg):
    res, _ = run(client_update(alg=alg), [material(alg)])
    assert res.outcome is TsigOutcome.OK


def test_S3_algorithm_mismatch_neg():
    wire = client_update(signing_alg=dns.tsig.HMAC_SHA1)
    res, _ = run(wire, [material(SHA256)])
    assert res.outcome is TsigOutcome.BADKEY


def test_S3_algorithm_mismatch_sha384_vs_sha256_neg():
    res, _ = run(client_update(alg=SHA384), [material(SHA256)])
    assert res.outcome is TsigOutcome.BADKEY


@pytest.mark.parametrize("weak", [dns.tsig.HMAC_MD5, dns.tsig.HMAC_SHA224])
def test_S3_disallowed_algorithm_neg(weak):
    # The key is stored with a weak algorithm and the request uses the same one.
    wire = client_update(signing_alg=weak)
    res, _ = run(wire, [material(weak, secret=b"\x09" * 32)])
    assert res.outcome is TsigOutcome.BADKEY


# --- S4 MAC ----------------------------------------------------------------------

def test_S4_untouched_message_pos():
    res, _ = run(client_update(), [material()])
    assert res.outcome is TsigOutcome.OK


def test_S4_flipped_mac_byte_neg():
    res, _ = run(flip_mac(client_update()), [material()])
    assert res.outcome is TsigOutcome.BADSIG and res.key is None


def test_S4_wrong_secret_neg():
    res, _ = run(client_update(secret=b"\x55" * 32), [material()])
    assert res.outcome is TsigOutcome.BADSIG


def test_S4_body_changed_neg():
    wire = client_update(txt='"abc"')
    assert b"abc" in wire
    res, _ = run(wire.replace(b"abc", b"abd"), [material()])
    assert res.outcome is TsigOutcome.BADSIG


# --- S5 order --------------------------------------------------------------------

def test_S5_good_mac_bad_time_pos():
    res, _ = run(client_update(t=NOW - 1000), [material()])
    assert res.outcome is TsigOutcome.BADTIME


def test_S5_bad_mac_and_bad_time_gives_badsig_neg():
    res, _ = run(flip_mac(client_update(t=NOW - 1000)), [material()])
    assert res.outcome is TsigOutcome.BADSIG


def test_S5_unknown_key_and_bad_time_gives_badkey_neg():
    wire = client_update(t=NOW - 1000, name=dns.name.from_text("other.example."))
    res, _ = run(wire, [material()])
    assert res.outcome is TsigOutcome.BADKEY


def test_S5_bad_mac_never_has_key_neg():
    # F5: a BADSIG result never carries a key, so no signed response can follow.
    res, _ = run(flip_mac(client_update(t=NOW - 1000)), [material()])
    assert res.key is None


# --- S6 time ---------------------------------------------------------------------

@pytest.mark.parametrize("skew", [300, -300, 0])
def test_S6_skew_at_window_pos(skew):
    res, _ = run(client_update(t=NOW - skew), [material()])
    assert res.outcome is TsigOutcome.OK


@pytest.mark.parametrize("skew", [301, -301])
def test_S6_skew_over_window_neg(skew):
    res, _ = run(client_update(t=NOW - skew), [material()])
    assert res.outcome is TsigOutcome.BADTIME


def test_S6_small_request_fudge_is_used_pos():
    res, _ = run(client_update(t=NOW - 10, fudge=10), [material()])
    assert res.outcome is TsigOutcome.OK


def test_S6_small_request_fudge_is_used_neg():
    res, _ = run(client_update(t=NOW - 11, fudge=10), [material()])
    assert res.outcome is TsigOutcome.BADTIME


def test_S6_badtime_response_pos():
    t = NOW - 1000
    wire = client_update(t=t, fudge=200)
    res, msg = run(wire, [material()])
    assert res.outcome is TsigOutcome.BADTIME and res.key is not None
    out = render_badtime(skeleton(msg), res, NOW)
    parsed = parse(out)
    rd = parsed.tsig[0]
    assert parsed.rcode() == dns.rcode.NOTAUTH
    assert rd.error == dns.rcode.BADTIME
    assert rd.time_signed == t and rd.fudge == 200
    assert len(rd.other) == 6 and int.from_bytes(rd.other, "big") == NOW
    assert parsed.tsig.name == KEYNAME and parsed.id == msg.id and rd.original_id == msg.id
    mac, _ = digest_mac(out, parse(wire).tsig[0].mac, SECRETS[SHA256], SHA256)
    assert hmac.compare_digest(mac, rd.mac)


def test_S6_badtime_response_wrong_request_mac_neg():
    wire = client_update(t=NOW - 1000)
    res, msg = run(wire, [material()])
    out = render_badtime(skeleton(msg), res, NOW)
    mac, rd = digest_mac(out, b"", SECRETS[SHA256], SHA256)
    assert not hmac.compare_digest(mac, rd.mac)


def test_S6_badtime_without_key_neg():
    res = TsigResult(TsigOutcome.BADSIG)
    msg = parse(client_update())
    with pytest.raises(ValueError):
        render_badtime(skeleton(msg), res, NOW)


# --- S7 watermark ----------------------------------------------------------------

def test_S7_same_and_later_time_pos():
    wm, key = TimeWatermark(), material()
    for t in (NOW, NOW, NOW + 5):
        res, _ = run(client_update(t=t), [key], now=NOW + 5, wm=wm)
        assert res.outcome is TsigOutcome.OK


def test_S7_earlier_than_recorded_neg():
    wm, key = TimeWatermark(), material()
    run(client_update(t=NOW + 5), [key], now=NOW + 5, wm=wm)
    res, _ = run(client_update(t=NOW + 4), [key], now=NOW + 5, wm=wm)
    assert res.outcome is TsigOutcome.BADTIME


def test_S7_watermark_is_per_key_pos():
    wm = TimeWatermark()
    k1, k2 = material(key_id=1), material(SHA384, name=dns.name.from_text("k2.example."), key_id=2)
    run(client_update(t=NOW + 5), [k1], now=NOW + 5, wm=wm)
    res, _ = run(client_update(t=NOW, alg=SHA384, name=k2.name), [k2], now=NOW, wm=wm)
    assert res.outcome is TsigOutcome.OK


def test_S7_valid_request_updates_watermark_pos():
    wm = TimeWatermark()
    run(client_update(t=NOW + 5), [material()], now=NOW + 5, wm=wm)
    assert wm.is_older(1, NOW + 4)


def test_S7_bad_mac_does_not_update_watermark_neg():
    wm, key = TimeWatermark(), material()
    res, _ = run(flip_mac(client_update(t=NOW + 100)), [key], now=NOW + 100, wm=wm)
    assert res.outcome is TsigOutcome.BADSIG
    assert not wm.is_older(1, 0)
    res, _ = run(client_update(t=NOW), [key], now=NOW, wm=wm)
    assert res.outcome is TsigOutcome.OK


def test_S7_bad_time_does_not_update_watermark_neg():
    wm, key = TimeWatermark(), material()
    res, _ = run(client_update(t=NOW + 1000), [key], now=NOW, wm=wm)
    assert res.outcome is TsigOutcome.BADTIME
    assert not wm.is_older(1, 0)
    res, _ = run(client_update(t=NOW), [key], now=NOW, wm=wm)
    assert res.outcome is TsigOutcome.OK


def test_S7_truncated_request_does_not_update_watermark_neg():
    wm = TimeWatermark()
    res, _ = run(truncated(client_update(t=NOW + 50), 16), [material()], now=NOW + 50, wm=wm)
    assert res.outcome is TsigOutcome.BADTRUNC
    assert not wm.is_older(1, 0)


# --- S15 replay before time (plan step 6e before 6f) ------------------------------

def _run_replay(wire, key, now, wm, seen):
    calls = []

    def is_replay():
        calls.append(1)
        return seen(wire)

    res = verify_request(wire, parse(wire), lookup_for(key), now, wm, is_replay=is_replay)
    return res, calls


def test_S15_replay_older_than_watermark_is_ok_without_time_check_pos():
    wm, key = TimeWatermark(), material()
    a = client_update(t=NOW - 1)
    b = client_update(t=NOW)
    assert run(a, [key], now=NOW, wm=wm)[0].outcome is TsigOutcome.OK
    assert run(b, [key], now=NOW, wm=wm)[0].outcome is TsigOutcome.OK
    assert run(a, [key], now=NOW, wm=wm)[0].outcome is TsigOutcome.BADTIME  # without is_replay
    res, calls = _run_replay(a, key, NOW, wm, lambda w: w == a)
    assert res.outcome is TsigOutcome.OK and res.replayed and res.key == key
    assert calls == [1]
    assert wm.is_older(1, NOW - 1) and not wm.is_older(1, NOW)  # watermark unchanged


def test_S15_replay_outside_time_window_is_ok_pos():
    wm, key = TimeWatermark(), material()
    a = client_update(t=NOW)
    res, _ = _run_replay(a, key, NOW + 10_000, wm, lambda w: True)
    assert res.outcome is TsigOutcome.OK and res.replayed
    assert not wm.is_older(1, 0)  # nothing recorded for a replay


def test_S15_new_request_older_than_watermark_is_badtime_neg():
    wm, key = TimeWatermark(), material()
    run(client_update(t=NOW), [key], now=NOW, wm=wm)
    old = client_update(t=NOW - 1)
    res, calls = _run_replay(old, key, NOW, wm, lambda w: False)
    assert res.outcome is TsigOutcome.BADTIME and not res.replayed
    assert calls == [1]
    assert not wm.is_older(1, NOW)


def test_S15_replay_with_bad_mac_is_badsig_and_cache_not_asked_neg():
    wm, key = TimeWatermark(), material()
    res, calls = _run_replay(flip_mac(client_update(t=NOW)), key, NOW, wm, lambda w: True)
    assert res.outcome is TsigOutcome.BADSIG and not res.replayed
    assert calls == []
    assert not wm.is_older(1, 0)


def test_S15_replay_with_unknown_key_cache_not_asked_neg():
    res, calls = _run_replay(client_update(t=NOW), material(name=dns.name.from_text("x.example.")),
                             NOW, TimeWatermark(), lambda w: True)
    assert res.outcome is TsigOutcome.BADKEY and calls == []


def test_S15_not_a_replay_outside_window_is_badtime_neg():
    wm, key = TimeWatermark(), material()
    res, _ = _run_replay(client_update(t=NOW), key, NOW + 10_000, wm, lambda w: False)
    assert res.outcome is TsigOutcome.BADTIME and not res.replayed


def test_S15_truncated_non_replay_is_still_badtrunc_neg():
    wm, key = TimeWatermark(), material()
    res, _ = _run_replay(truncated(client_update(t=NOW), 16), key, NOW, wm, lambda w: False)
    assert res.outcome is TsigOutcome.BADTRUNC and not res.replayed
    assert not wm.is_older(1, 0)


def test_S7_watermark_class_pos():
    wm = TimeWatermark()
    assert not wm.is_older(1, 10)
    wm.record(1, 10)
    wm.record(1, 5)  # keeps the maximum
    assert wm.is_older(1, 9) and not wm.is_older(1, 10) and not wm.is_older(1, 11)


def test_S7_watermark_bounded_neg():
    wm = TimeWatermark(max_keys=2)
    wm.record(1, 100)
    wm.record(2, 100)
    wm.record(1, 100)  # key 1 is now the most recently used
    wm.record(3, 100)  # evicts key 2
    assert wm.is_older(1, 99) and wm.is_older(3, 99)
    assert not wm.is_older(2, 99)
    assert len(wm._times) == 2


# --- S8 MAC size -------------------------------------------------------------------

def test_S8_full_mac_pos():
    res, _ = run(client_update(), [material()])
    assert res.outcome is TsigOutcome.OK and len(res.request_mac) == 32


@pytest.mark.parametrize("size", [33, 9, 0, 15])
def test_S8_bad_mac_size_neg(size):
    wire = client_update()
    mac = parse(wire).tsig[0].mac
    res, _ = run(with_mac(wire, (mac + b"\x00" * 8)[:size]), [material()])
    assert res.outcome is TsigOutcome.FORMERR and res.key is None


@pytest.mark.parametrize("alg,size", [(SHA384, 24), (SHA512, 32)])
def test_S8_minimum_truncation_per_algorithm_pos(alg, size):
    wire = client_update(alg=alg)
    res, _ = run(truncated(wire, size), [material(alg)])
    assert res.outcome is TsigOutcome.BADTRUNC


@pytest.mark.parametrize("alg,size", [(SHA384, 23), (SHA512, 31)])
def test_S8_below_minimum_per_algorithm_neg(alg, size):
    res, _ = run(truncated(client_update(alg=alg), size), [material(alg)])
    assert res.outcome is TsigOutcome.FORMERR


def test_S8_correct_truncated_mac_gives_badtrunc_pos():
    wire = client_update()
    t = truncated(wire, 16)
    res, msg = run(t, [material()])
    assert res.outcome is TsigOutcome.BADTRUNC and res.key is not None
    assert res.request_mac == parse(wire).tsig[0].mac[:16]
    out = render_badtrunc(skeleton(msg), res, NOW)
    parsed = parse(out)
    rd = parsed.tsig[0]
    assert parsed.rcode() == dns.rcode.NOTAUTH and rd.error == dns.rcode.BADTRUNC
    assert rd.time_signed == NOW and rd.fudge == RESPONSE_FUDGE
    assert len(rd.mac) == 32
    mac, _ = digest_mac(out, res.request_mac, SECRETS[SHA256], SHA256)
    assert hmac.compare_digest(mac, rd.mac)


def test_S8_wrong_truncated_mac_gives_badsig_neg():
    res, _ = run(truncated(client_update(), 16, wrong=True), [material()])
    assert res.outcome is TsigOutcome.BADSIG and res.key is None


def test_S8_truncated_mac_with_bad_time_neg():
    # The MAC is checked first (§5.2), then the time, then the truncation.
    res, _ = run(truncated(client_update(t=NOW - 1000), 16), [material()])
    assert res.outcome is TsigOutcome.BADTIME
    res, _ = run(truncated(client_update(t=NOW - 1000), 16, wrong=True), [material()])
    assert res.outcome is TsigOutcome.BADSIG


def test_S8_badtrunc_without_key_neg():
    msg = parse(client_update())
    with pytest.raises(ValueError):
        render_badtrunc(skeleton(msg), TsigResult(TsigOutcome.BADSIG), NOW)


# --- S9 request error field --------------------------------------------------------

def test_S9_error_zero_pos():
    res, _ = run(client_update(tsig_error=0), [material()])
    assert res.outcome is TsigOutcome.OK


def test_S9_error_set_in_request_neg():
    res, _ = run(client_update(tsig_error=dns.rcode.BADSIG), [material()])
    assert res.outcome is TsigOutcome.FORMERR and res.key is None


# --- S10 / S11 signed response -----------------------------------------------------

def test_S10_signed_response_verifies_pos():
    key, wire, res, msg = ok_case()
    out = render_signed(skeleton(msg), res, NOW)
    parsed = client_verify(out, parse(wire).tsig[0].mac, key)
    assert parsed.rcode() == dns.rcode.NOERROR and parsed.id == msg.id
    mac, rd = digest_mac(out, res.request_mac, key.secret, SHA256)
    assert hmac.compare_digest(mac, rd.mac)
    assert rd.time_signed == NOW and rd.fudge == RESPONSE_FUDGE and rd.error == 0
    assert rd.other == b"" and rd.original_id == msg.id and parse(out).tsig.name == KEYNAME


def test_S10_flipped_response_mac_neg():
    key, wire, res, msg = ok_case()
    out = render_signed(skeleton(msg), res, NOW)
    with pytest.raises(dns.tsig.BadSignature):
        client_verify(flip_mac(out), parse(wire).tsig[0].mac, key)


def test_S10_wrong_request_mac_neg():
    key, wire, res, msg = ok_case()
    out = render_signed(skeleton(msg), res, NOW)
    with pytest.raises(dns.tsig.BadSignature):
        client_verify(out, b"\x00" * 32, key)


def test_S10_response_to_truncated_request_uses_truncated_mac_pos():
    wire = truncated(client_update(), 16)
    res, msg = run(wire, [material()], now=NOW)
    assert res.outcome is TsigOutcome.BADTRUNC
    out = render_signed(skeleton(msg), res, NOW)
    mac, rd = digest_mac(out, parse(wire).tsig[0].mac, SECRETS[SHA256], SHA256)
    assert len(parse(wire).tsig[0].mac) == 16 and hmac.compare_digest(mac, rd.mac)


def test_S10_response_without_validated_key_neg():
    msg = parse(client_update())
    with pytest.raises(ValueError):
        render_signed(skeleton(msg), TsigResult(TsigOutcome.BADSIG), NOW)


@pytest.mark.parametrize("alg", ALGS)
def test_S11_response_mac_is_full_length_pos(alg):
    key, wire, res, msg = ok_case(alg)
    out = render_signed(skeleton(msg), res, NOW)
    rd = parse(out).tsig[0]
    assert len(rd.mac) == dns.tsig.mac_sizes[alg] >= len(res.request_mac)
    mac, _ = digest_mac(out, res.request_mac, key.secret, alg)
    assert hmac.compare_digest(mac, rd.mac)
    client_verify(out, res.request_mac, key)


def test_S11_response_to_truncated_request_is_not_shorter_neg():
    wire = truncated(client_update(), 16)
    res, msg = run(wire, [material()])
    out = render_signed(skeleton(msg), res, NOW)
    assert len(parse(out).tsig[0].mac) == 32 > len(res.request_mac)


# --- S12 truncation ----------------------------------------------------------------

def query_case():
    key = material()
    k = dns.tsig.Key(key.name, key.secret, key.algorithm)
    q = dns.message.make_query("big.example.", "TXT", use_edns=0, payload=1232)
    q.use_tsig(k)
    with at(NOW):
        wire = q.to_wire()
    res, msg = run(wire, [key])
    assert res.outcome is TsigOutcome.OK
    resp = skeleton(msg)
    rrset = resp.find_rrset(resp.answer, dns.name.from_text("big.example."),
                            dns.rdataclass.IN, dns.rdatatype.TXT, create=True)
    for i in range(20):
        rrset.add(dns.rdata.from_text(dns.rdataclass.IN, dns.rdatatype.TXT, '"%s"' % (str(i) * 100)))
    return key, wire, res, msg, resp


def test_S12_oversize_response_is_truncated_pos():
    key, wire, res, msg, resp = query_case()
    full = render_signed(resp, res, NOW)
    out = render_signed(resp, res, NOW, max_size=512)
    assert len(full) > 512 and len(out) < len(full)
    parsed = client_verify(out, res.request_mac, key)
    assert parsed.flags & dns.flags.TC
    assert parsed.rcode() == dns.rcode.NOERROR
    assert parsed.answer == [] and parsed.authority == []
    assert len(parsed.question) == 1 and parsed.opt is not None
    mac, rd = digest_mac(out, res.request_mac, key.secret, SHA256)
    assert hmac.compare_digest(mac, rd.mac)


def test_F1_truncated_form_above_max_size_gives_none_pos():
    long_name = dns.name.from_text(".".join(["a" * 60] * 4) + ".net.")
    key = material(name=dns.name.from_text(".".join(["k" * 60] * 4) + ".org."))
    k = dns.tsig.Key(key.name, key.secret, key.algorithm)
    q = dns.message.make_query(long_name, "SOA")
    q.use_tsig(k)
    with at(NOW):
        wire = q.to_wire()
    res, msg = run(wire, [key])
    assert res.outcome is TsigOutcome.OK
    resp = skeleton(msg)
    assert render_signed(resp, res, NOW, max_size=512) is None
    assert len(render_signed(resp, res, NOW)) > 512  # no limit: bytes as before


def test_F1_truncated_form_within_max_size_is_returned_neg():
    key, wire, res, msg, resp = query_case()
    out = render_signed(resp, res, NOW, max_size=512)
    assert out is not None and len(out) <= 512
    assert client_verify(out, res.request_mac, key).flags & dns.flags.TC


def test_S12_large_max_size_gives_full_answer_neg():
    key, wire, res, msg, resp = query_case()
    out = render_signed(resp, res, NOW, max_size=65535)
    parsed = client_verify(out, res.request_mac, key)
    assert not parsed.flags & dns.flags.TC and len(parsed.answer) == 1
    assert len(out) > 2000  # full 20-string answer (RRset order is random, so no byte compare)


def test_S12_truncation_keeps_skeleton_intact_neg():
    key, wire, res, msg, resp = query_case()
    render_signed(resp, res, NOW, max_size=512)
    assert not resp.flags & dns.flags.TC and len(resp.answer) == 1
    assert resp.opt is not None and resp.rcode() == dns.rcode.NOERROR


def test_S12_truncated_without_opt_pos():
    key, wire, res, msg = ok_case()
    resp = skeleton(msg)
    rrset = resp.find_rrset(resp.answer, dns.name.from_text("big.example."),
                            dns.rdataclass.IN, dns.rdatatype.TXT, create=True)
    rrset.add(dns.rdata.from_text(dns.rdataclass.IN, dns.rdatatype.TXT, '"%s"' % ("x" * 200)))
    out = render_signed(resp, res, NOW, max_size=300)  # the full answer is above 300
    parsed = client_verify(out, res.request_mac, key)
    assert parsed.flags & dns.flags.TC and parsed.opt is None
    assert len(parsed.question) == 1


# --- S13 key name case -------------------------------------------------------------

def test_S13_key_name_case_insensitive_pos():
    wire = client_update(name=dns.name.from_text("K1.Example."))
    res, _ = run(wire, [material(name=dns.name.from_text("k1.example."))])
    assert res.outcome is TsigOutcome.OK


def test_S13_other_name_neg():
    wire = client_update(name=dns.name.from_text("k2.example."))
    res, _ = run(wire, [material()])
    assert res.outcome is TsigOutcome.BADKEY


def test_S13_response_mac_with_mixed_case_name_pos():
    key = material(name=dns.name.from_text("k1.example."))
    wire = client_update(name=dns.name.from_text("K1.Example."))
    res, msg = run(wire, [key])
    out = render_signed(skeleton(msg), res, NOW)
    mac, rd = digest_mac(out, res.request_mac, key.secret, SHA256)
    assert hmac.compare_digest(mac, rd.mac)


# --- S14 fudge cap -----------------------------------------------------------------

def test_S14_fudge_300_skew_300_pos():
    res, _ = run(client_update(t=NOW - 300, fudge=300), [material()])
    assert res.outcome is TsigOutcome.OK


def test_S14_huge_fudge_is_capped_neg():
    wire = client_update(t=NOW - 301, fudge=65535)
    res, msg = run(wire, [material()])
    assert res.outcome is TsigOutcome.BADTIME
    out = render_badtime(skeleton(msg), res, NOW)
    rd = parse(out).tsig[0]
    assert rd.fudge == 65535
    mac, _ = digest_mac(out, res.request_mac, SECRETS[SHA256], SHA256)
    assert hmac.compare_digest(mac, rd.mac)


def test_S14_huge_fudge_at_cap_pos():
    res, _ = run(client_update(t=NOW - 300, fudge=65535), [material()])
    assert res.outcome is TsigOutcome.OK


# --- unsigned error responses -------------------------------------------------------

@pytest.mark.parametrize("error", [dns.rcode.BADKEY, dns.rcode.BADSIG])
def test_unsigned_error_response_pos(error):
    t = NOW - 5
    wire = client_update(t=t, fudge=77)
    res, msg = run(wire, [])
    assert res.outcome is TsigOutcome.BADKEY
    out = render_unsigned_tsig_error(skeleton(msg), res, error)
    parsed = parse(out)
    rd = parsed.tsig[0]
    assert parsed.rcode() == dns.rcode.NOTAUTH
    assert rd.error == error and len(rd.mac) == 0
    assert parsed.tsig.name == KEYNAME and rd.algorithm == SHA256
    assert rd.time_signed == t and rd.fudge == 77 and rd.other == b""
    assert rd.original_id == msg.id and parsed.id == msg.id


def test_unsigned_error_response_has_no_mac_neg():
    for bad, error in ((client_update(name=dns.name.from_text("x.example.")), dns.rcode.BADKEY),
                       (flip_mac(client_update()), dns.rcode.BADSIG)):
        res, msg = run(bad, [material()])
        out = render_unsigned_tsig_error(skeleton(msg), res, error)
        assert parse(out).tsig[0].mac == b""
        assert res.request_mac not in out


def test_unsigned_error_other_code_neg():
    res, msg = run(client_update(), [material()])
    with pytest.raises(ValueError):
        render_unsigned_tsig_error(skeleton(msg), res, dns.rcode.BADTIME)


def test_unsigned_error_does_not_change_skeleton_pos():
    res, msg = run(client_update(name=dns.name.from_text("x.example.")), [material()])
    resp = skeleton(msg)
    render_unsigned_tsig_error(resp, res, dns.rcode.BADKEY)
    assert resp.rcode() == dns.rcode.NOERROR and resp.tsig is None


# --- F11 repr ----------------------------------------------------------------------

def test_F11_key_repr_hides_secret_pos():
    key = material()
    text = repr(key)
    assert "TsigKeyMaterial" in text and "k1.example" in text
    assert repr(key.secret) not in text and key.secret.hex() not in text
    assert base64.b64encode(key.secret).decode() not in text
    assert str(key.secret) not in text


def test_F11_result_repr_hides_mac_and_secret_neg():
    key, wire, res, msg = ok_case()
    text = repr(res)
    mac = res.request_mac
    assert len(mac) == 32 and res.rdata is not None
    for secret_form in (repr(key.secret), key.secret.hex(), base64.b64encode(key.secret).decode()):
        assert secret_form not in text
    for mac_form in (repr(mac), mac.hex(), base64.b64encode(mac).decode(), mac.hex().upper()):
        assert mac_form not in text
    assert "OK" in text


# --- generate_secret ---------------------------------------------------------------

@pytest.mark.parametrize("alg,length", [(SHA256, 32), (SHA384, 48), (SHA512, 64)])
def test_generate_secret_length_pos(alg, length):
    assert len(generate_secret(alg)) == length


@pytest.mark.parametrize("alg", [dns.tsig.HMAC_SHA1, dns.tsig.HMAC_MD5, dns.tsig.HMAC_SHA224])
def test_generate_secret_disallowed_algorithm_neg(alg):
    with pytest.raises(ValueError):
        generate_secret(alg)


def test_generate_secret_unique_pos():
    assert len({generate_secret(SHA256) for _ in range(1000)}) == 1000


# --- tsig_start_offset -------------------------------------------------------------

def tsig_rr_wire(wire_msg):
    f = io.BytesIO()
    wire_msg.tsig.to_wire(f)
    return f.getvalue()


def test_tsig_start_offset_pos():
    wire = client_update()
    assert tsig_start_offset(wire) == len(wire) - len(tsig_rr_wire(parse(wire)))


def test_tsig_start_offset_with_compression_pos():
    u = dns.update.UpdateMessage("example.com.")
    for i in range(5):
        u.add("_acme-challenge.host%d.example.com." % i, 60, "TXT", '"v%d"' % i)
    plain = u.to_wire()
    assert plain.count(b"\x07example") == 1  # the names are compressed
    key = dns.tsig.Key(KEYNAME, SECRETS[SHA256], SHA256)
    u.use_tsig(key)
    with at(NOW):
        signed = u.to_wire()
    assert tsig_start_offset(signed) == len(plain)
    # also with a TSIG that is appended by hand
    trd = dns.rdtypes.ANY.TSIG.TSIG(dns.rdataclass.ANY, dns.rdatatype.TSIG, SHA256, NOW, 300,
                                    b"\x00" * 32, u.id, 0, b"")
    rr = io.BytesIO()
    dns.rrset.from_rdata(KEYNAME, 0, trd).to_wire(rr)
    manual = plain[:10] + struct.pack("!H", struct.unpack("!H", plain[10:12])[0] + 1) \
        + plain[12:] + rr.getvalue()
    assert tsig_start_offset(manual) == len(plain)


def test_tsig_start_offset_after_opt_pos():
    q = dns.message.make_query("big.example.", "TXT", use_edns=0)
    q.use_tsig(dns.tsig.Key(KEYNAME, SECRETS[SHA256], SHA256))
    plain = dns.message.make_query("big.example.", "TXT", use_edns=0)
    plain.id = q.id
    with at(NOW):
        wire = q.to_wire()
    assert tsig_start_offset(wire) == len(plain.to_wire())


def test_tsig_start_offset_no_rr_neg():
    with pytest.raises(dns.exception.FormError):
        tsig_start_offset(dns.message.make_query("a.example.", "A").to_wire()[:12]
                          + b"\x01a\x07example\x00\x00\x01\x00\x01")


def test_tsig_not_last_rr_neg():
    # A TSIG that is followed by another RR is not valid: FORMERR, not an accepted request.
    wire = client_update()
    msg = parse(wire)
    start = tsig_start_offset(wire)
    extra = io.BytesIO()
    dns.rrset.from_text("x.example.", 0, "IN", "A", "192.0.2.1").to_wire(extra)
    arcount = struct.unpack("!H", wire[10:12])[0] + 1
    bad = wire[:10] + struct.pack("!H", arcount) + wire[12:] + extra.getvalue()
    res = verify_request(bad, msg, lookup_for(material()), NOW, TimeWatermark())
    assert res.outcome is TsigOutcome.FORMERR
    assert start == tsig_start_offset(wire)


# --- §4.2: TTL of the TSIG RR ----------------------------------------------------

def _with_tsig_ttl(wire, ttl):
    """Set the TTL of the TSIG RR (the MAC does not cover it)."""
    start = tsig_start_offset(wire)
    p = dns.wire.Parser(wire, start)
    p.get_name()
    off = p.current + 4  # after TYPE and CLASS
    return wire[:off] + struct.pack("!I", ttl) + wire[off + 4:]


def test_S1_tsig_ttl_zero_is_accepted_pos():
    result, _ = run(_with_tsig_ttl(client_update(), 0), [material()])
    assert result.outcome == TsigOutcome.OK


def test_S1_tsig_ttl_not_zero_is_formerr_neg():
    # RFC 8945 §4.2: "TTL: This MUST be 0." The MAC still verifies, so only this check stops it.
    wire = _with_tsig_ttl(client_update(), 60)
    from services.acme.dns_update.tsig import _last_rr_header
    assert _last_rr_header(wire)[2] == 60  # on the wire; dnspython keeps no TSIG TTL
    result, _ = run(wire, [material()])
    assert result.outcome == TsigOutcome.FORMERR
    assert result.key is None
