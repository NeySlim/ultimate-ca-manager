"""Fixed values for the DNS UPDATE listener.

RFC 8945 §7 lets the server set its own algorithm policy. Policy here: nothing
weaker than SHA-256. MD5, SHA-1, SHA-224, the truncated variants and GSS-TSIG
are not allowed.
"""

import dns.tsig

ALLOWED_TSIG_ALGORITHMS = frozenset({
    dns.tsig.HMAC_SHA256,
    dns.tsig.HMAC_SHA384,
    dns.tsig.HMAC_SHA512,
})

# RFC 8945 §8: a secret is at least as long as the hash output, in bytes.
SECRET_LENGTHS = {
    dns.tsig.HMAC_SHA256: 32,
    dns.tsig.HMAC_SHA384: 48,
    dns.tsig.HMAC_SHA512: 64,
}

# Upper limit, in seconds, for the Fudge value taken from a request (RFC 8945 §10).
MAX_FUDGE = 300

# Fudge value, in seconds, that the server puts in its own responses.
RESPONSE_FUDGE = 300

# Limits for the message handler (plan 3, steps 2 and 6).
MAX_MESSAGE_SIZE = 4096
MAX_QDCOUNT = 16
MAX_ANCOUNT = 16
MAX_NSCOUNT = 16
MAX_ARCOUNT = 4

# Replay cache (RFC 8945 §10, S15): bounded size and time to live in seconds.
REPLAY_CACHE_SIZE = 4096
# A request passes the time check for 2 * fudge, so a replay may come that long after the first copy.
REPLAY_TTL_S = 2 * MAX_FUDGE

# SOA RDATA that the listener announces: serial, refresh, retry, expire, minimum.
SOA_TIMERS = (1, 3600, 600, 86400, 0)

# First label of every owner name that a client may change (RFC 8555 §8.4).
CHALLENGE_LABEL = b'_acme-challenge'
