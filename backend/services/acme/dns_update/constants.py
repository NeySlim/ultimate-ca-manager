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
