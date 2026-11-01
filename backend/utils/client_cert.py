"""The TLS client certificate of the current request, when it can be trusted."""
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from flask import request


def trusted_client_cert(log, label):
    """PEM of the client certificate, or None.

    Native TLS (``environ['peercert']``) was verified by gunicorn against the
    mTLS CA. Proxy-forwarded SSL_CLIENT_CERT counts only from a trusted proxy
    that also reports SSL_CLIENT_VERIFY=SUCCESS: anyone else can forge it.
    """
    peercert = request.environ.get('peercert')
    if peercert:
        if isinstance(peercert, (bytes, bytearray)) and not bytes(peercert).lstrip().startswith(b'-----'):
            return x509.load_der_x509_certificate(bytes(peercert)).public_bytes(Encoding.PEM).decode('ascii')
        return peercert

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
