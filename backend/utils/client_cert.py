"""The TLS client certificate of the current request, when it can be trusted."""
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from flask import request


# A native client certificate the listener let through on a former CA alone: WSTEP renewal reads it
FORMER_PEERCERT = 'ucm.former_ca_peercert'
# Explanatory text before the PEM blocks of the trust bundle (ignored by OpenSSL): its former CAs
FORMER_CAS_HEADER = 'UCM-Former-CAs: '
# What this worker's TLS context loaded, pinned once when it is built: never a later rewrite
_listener = {'armed': False, 'refids': frozenset()}


def former_cas_header(refids):
    """The bundle's first line naming the former CAs it trusts beside the anchor."""
    import json
    return FORMER_CAS_HEADER + json.dumps(sorted(refids)) + '\n'


def _bundle_trust(bundle):
    """``(armed, refids)`` of one bundle read: armed when it trusts more than its anchor, or is unreadable."""
    import json
    if bundle is None:
        return True, frozenset()
    text = bundle.decode('ascii', 'replace') if isinstance(bundle, (bytes, bytearray)) else bundle
    refids = set()
    for line in text.splitlines():
        if line.startswith(FORMER_CAS_HEADER):
            try:
                value = json.loads(line[len(FORMER_CAS_HEADER):])
            except ValueError:
                return True, frozenset()
            if isinstance(value, list):
                refids.update(r for r in value if isinstance(r, str))
    return bool(refids) or text.count('-----BEGIN CERTIFICATE-----') > 1, frozenset(refids)


def pin_listener_trust(bundles, settled=True):
    """Pin the former CAs of the bundle(s) this worker's TLS context loaded. Several reads, or an
    unsettled one (rewritten while loading): their union, guard armed."""
    armed, refids = not settled, set()
    for bundle in bundles:
        bundle_armed, bundle_refids = _bundle_trust(bundle)
        armed, refids = armed or bundle_armed, refids | bundle_refids
    _listener.update(armed=armed, refids=frozenset(refids))


def pin_listener_trust_file(path, build, attempts=3):
    """Build the TLS context with *build* (it loads *path*) and pin what it loaded: the bundle read
    before and after must match, otherwise both count and the guard is armed."""
    def read():
        try:
            with open(path, 'rb') as handle:
                return handle.read()
        except OSError:
            return None
    for _ in range(attempts):
        before = read()
        ctx = build()
        after = read()
        if before is not None and before == after:
            pin_listener_trust([before])
            return ctx
    pin_listener_trust([before, after], settled=False)
    return ctx


def listener_former_refids():
    """The refids of the former CAs this worker's listener trusts beside its mTLS anchor."""
    return _listener['refids']


def listener_guard_armed():
    """Whether this worker's listener trusts anything beyond its mTLS anchor (or may, in doubt)."""
    return _listener['armed']


def set_aside_former_ca_peercert():
    """Before any other hook: while the listener trusts former CAs, a native client certificate
    passes on as ``peercert`` only when a CA of UCM under the mTLS anchor signed it. Any other
    (a former CA's, or an issuer UCM does not hold) moves to ``FORMER_PEERCERT``, out of reach of
    every route but WSTEP renewal: TLS trust of a former CA grants nothing else."""
    peercert = request.environ.get('peercert')
    if not peercert or not listener_guard_armed():
        return None
    try:
        if isinstance(peercert, (bytes, bytearray)) and not bytes(peercert).lstrip().startswith(b'-----'):
            cert = x509.load_der_x509_certificate(bytes(peercert))
        else:
            cert = x509.load_pem_x509_certificate(peercert.encode() if isinstance(peercert, str) else peercert)
        from utils.cert_issuer import signing_ca_for
        signer = signing_ca_for(cert)
        anchored = signer is not None and native_tls_admits(signer)
    except Exception:
        anchored = False
    if not anchored:
        request.environ[FORMER_PEERCERT] = request.environ.pop('peercert')
    return None


def _pem_of(peercert):
    if isinstance(peercert, (bytes, bytearray)) and not bytes(peercert).lstrip().startswith(b'-----'):
        return x509.load_der_x509_certificate(bytes(peercert)).public_bytes(Encoding.PEM).decode('ascii')
    return peercert


def native_client_cert():
    """Whether the request came with a native TLS client certificate, set aside or not."""
    return bool(request.environ.get('peercert') or request.environ.get(FORMER_PEERCERT))


def trusted_client_cert(log, label, former_ca=False):
    """PEM of the client certificate, or None.

    Native TLS (``environ['peercert']``) was verified by gunicorn against the
    mTLS CA. Proxy-forwarded SSL_CLIENT_CERT counts only from a trusted proxy
    that also reports SSL_CLIENT_VERIFY=SUCCESS: anyone else can forge it.
    ``former_ca``: WSTEP renewal, which also reads a certificate set aside
    by ``set_aside_former_ca_peercert``.
    """
    if former_ca and request.environ.get(FORMER_PEERCERT):
        return _pem_of(request.environ[FORMER_PEERCERT])
    peercert = request.environ.get('peercert')
    if peercert:
        return _pem_of(peercert)

    from utils.trusted_proxy import immediate_peer_addr, is_request_from_trusted_proxy
    if not is_request_from_trusted_proxy():
        if request.environ.get('SSL_CLIENT_CERT') or request.headers.get('X-SSL-Client-Cert'):
            log.warning("%s: ignoring SSL_CLIENT_CERT from untrusted peer %s", label, immediate_peer_addr())
        return None

    verify = (
        request.environ.get('SSL_CLIENT_VERIFY')
        or request.headers.get('X-SSL-Client-Verify')
        or ''
    ).upper()
    presented = request.environ.get('SSL_CLIENT_CERT') or request.headers.get('X-SSL-Client-Cert')
    # Fail closed on a missing verify result, but warn only when a certificate
    # was presented: a proxied Basic-auth request carries none.
    if verify != 'SUCCESS':
        if presented:
            log.warning("%s: SSL_CLIENT_VERIFY=%r, refusing client cert", label, verify or '<missing>')
        else:
            log.debug("%s: no client certificate presented (SSL_CLIENT_VERIFY=%r); "
                      "falling through to other authentication", label, verify or '<missing>')
        return None

    from services.certificate_parser import decode_forwarded_pem
    return decode_forwarded_pem(presented)


def native_tls_admits(ca):
    """Whether the native TLS listener lets a client certificate of *ca* through: its one anchor is
    the mTLS trusted CA (A5), so *ca* must be that CA or a CA under it. A record sharing a step's
    subject and key (cross-certificate) is that same issuer to the listener."""
    from models import CA, SystemConfig
    from utils.cert_issuer import same_key_refids
    settings = {row.key: row.value for row in SystemConfig.query.filter(
        SystemConfig.key.in_(('mtls_enabled', 'mtls_trusted_ca_id')))}
    anchor = settings.get('mtls_trusted_ca_id')
    if settings.get('mtls_enabled') != 'true' or not anchor:
        return False
    seen = set()
    while ca is not None and ca.refid not in seen:
        if anchor in same_key_refids(ca):
            return True
        seen.add(ca.refid)
        ca = CA.query.filter_by(refid=ca.caref).first() if ca.caref else None
    return False
