import base64
import datetime
import json

import requests
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def _key_pem(key):
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )


def _cert_pem(subject_cn, issuer_cn, key, issuer_key=None, serial=1):
    issuer_key = issuer_key or key
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject_cn)])
    issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_cn)])
    now = datetime.datetime.utcnow()
    return (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(serial)
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .sign(issuer_key, hashes.SHA256())
        .public_bytes(serialization.Encoding.PEM)
    )


class _Response:
    def __init__(self, rows):
        self.status_code = 200
        self._rows = rows

    def json(self):
        return {"rows": self._rows}


class _Session:
    def __init__(self, ca_rows, cert_rows):
        self.ca_rows = ca_rows
        self.cert_rows = cert_rows

    def get(self, url, auth=None, timeout=None, allow_redirects=None):
        if "/api/trust/ca/search" in url:
            return _Response(self.ca_rows)
        if "/api/trust/cert/search" in url:
            return _Response(self.cert_rows)
        raise AssertionError(f"unexpected URL {url}")


def test_opnsense_import_uses_refid_and_links_cert_caref(app, auth_client, monkeypatch):
    from api.v2 import import_opnsense
    from models import CA, Certificate
    from utils.key_codec import load_pem_bytes

    ca_key = rsa.generate_private_key(65537, 2048)
    cert_key = rsa.generate_private_key(65537, 2048)
    ca_refid = "opn-ca-refid"
    cert_refid = "opn-cert-refid"
    ca_uuid = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    cert_uuid = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    ca_pem = _cert_pem("OPN Root", "OPN Root", ca_key, serial=100)
    cert_pem = _cert_pem("opn.example.test", "OPN Root", cert_key, issuer_key=ca_key, serial=200)
    cert_key_pem = _key_pem(cert_key)

    ca_rows = [{
        "uuid": ca_uuid,
        "refid": ca_refid,
        "descr": "OPN Root",
        "crt": base64.b64encode(ca_pem).decode("ascii"),
        "serial": "1",
    }]
    cert_rows = [{
        "uuid": cert_uuid,
        "refid": cert_refid,
        "caref": ca_refid,
        "descr": "OPN Cert",
        "crt_payload": cert_pem.decode("ascii"),
        "prv_payload": cert_key_pem.decode("ascii"),
        "cert_type": "server_cert",
    }]
    monkeypatch.setattr(import_opnsense, "create_session", lambda verify_ssl=True: _Session(ca_rows, cert_rows))

    r = auth_client.post('/api/v2/import/opnsense/import',
                         data=json.dumps({
                             "host": "192.168.1.254",
                             "port": 443,
                             "api_key": "key",
                             "api_secret": "secret",
                             "verify_ssl": False,
                             "items": [],
                         }),
                         content_type='application/json')

    assert r.status_code == 200, r.data
    body = json.loads(r.data)["data"]
    assert body["imported"] == {"cas": 1, "certificates": 1}

    with app.app_context():
        ca = CA.query.filter_by(refid=ca_refid).first()
        cert = Certificate.query.filter_by(refid=cert_refid).first()
        assert ca is not None
        assert CA.query.filter_by(refid=ca_uuid).first() is None
        assert cert is not None
        assert cert.caref == ca_refid
        assert cert.crt == base64.b64encode(cert_pem).decode("ascii")
        assert load_pem_bytes(cert.prv, context="opnsense cert") == cert_key_pem


def test_opnsense_ca_import_requires_write_cas(app, auth_client, monkeypatch):
    """OPNsense CA import must require write:cas, not only write:certificates."""
    from api.v2 import import_opnsense

    ca_rows = [{
        "uuid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "refid": "opn-ca-only",
        "descr": "OPN Root",
        "crt": "Zm9v",
        "serial": "1",
    }]
    monkeypatch.setattr(
        import_opnsense,
        "create_session",
        lambda verify_ssl=True: _Session(ca_rows, []),
    )

    r_key = auth_client.post(
        '/api/v2/account/apikeys',
        data=json.dumps({
            'name': 'opn-cert-only',
            'permissions': ['read:certificates', 'write:certificates'],
        }),
        content_type='application/json',
    )
    assert r_key.status_code == 201, r_key.data
    api_key = json.loads(r_key.data)['data']['key']

    client = app.test_client()
    r = client.post(
        '/api/v2/import/opnsense/import',
        data=json.dumps({
            "host": "192.168.1.254",
            "port": 443,
            "api_key": "key",
            "api_secret": "secret",
            "verify_ssl": False,
            "items": ["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"],
        }),
        content_type='application/json',
        headers={'X-API-Key': api_key},
    )
    assert r.status_code == 403


def _capturing_session_factory(captured):
    """create_session stand-in that records the verify_ssl it was called with.

    The default mirrors the REAL create_session signature (verify_ssl=True) so
    the capture reflects what the route passed, not what the stub assumed —
    the pre-#248 fixtures here used `lambda verify_ssl=False`, which would
    have stayed green even if the backend default regressed.
    """
    def _factory(verify_ssl=True):
        captured['verify_ssl'] = verify_ssl
        return _Session([], [])
    return _factory


def test_opnsense_test_defaults_to_verify_ssl_true(app, auth_client, monkeypatch):
    """#248 flipped the backend default to verify TLS; a body that omits
    verify_ssl must reach create_session with True. Regression guard for the
    default itself — no pre-existing test exercised the omitted-key case."""
    from api.v2 import import_opnsense

    captured = {}
    monkeypatch.setattr(import_opnsense, "create_session", _capturing_session_factory(captured))

    r = auth_client.post(
        '/api/v2/import/opnsense/test',
        data=json.dumps({
            "host": "192.168.1.254",
            "port": 443,
            "api_key": "key",
            "api_secret": "secret",
        }),
        content_type='application/json',
    )
    assert r.status_code == 200, r.data
    assert captured['verify_ssl'] is True


def test_opnsense_import_defaults_to_verify_ssl_true(app, auth_client, monkeypatch):
    from api.v2 import import_opnsense

    captured = {}
    monkeypatch.setattr(import_opnsense, "create_session", _capturing_session_factory(captured))

    r = auth_client.post(
        '/api/v2/import/opnsense/import',
        data=json.dumps({
            "host": "192.168.1.254",
            "port": 443,
            "api_key": "key",
            "api_secret": "secret",
            "items": [],
        }),
        content_type='application/json',
    )
    assert r.status_code == 200, r.data
    assert captured['verify_ssl'] is True


class _SSLFailingSession:
    """Session whose every request fails TLS verification, the way requests
    surfaces it: SSLError — which is a ConnectionError SUBCLASS, so without
    a dedicated handler it wears the generic host/port message."""

    def get(self, url, auth=None, timeout=None, allow_redirects=None):
        raise requests.exceptions.SSLError(
            "certificate verify failed: self-signed certificate")


def test_opnsense_test_tls_failure_names_the_certificate(app, auth_client, monkeypatch):
    """verify-by-default (#248/#255) makes a stock self-signed OPNsense GUI
    fail TLS verification on the DEFAULT interactive request; the operator
    must be told it is the certificate, not 'Check host and port.'"""
    from api.v2 import import_opnsense

    monkeypatch.setattr(import_opnsense, "create_session",
                        lambda verify_ssl=True: _SSLFailingSession())

    r = auth_client.post(
        '/api/v2/import/opnsense/test',
        data=json.dumps({
            "host": "192.168.1.254",
            "port": 443,
            "api_key": "key",
            "api_secret": "secret",
        }),
        content_type='application/json',
    )
    assert r.status_code == 400, r.data
    body = r.get_data(as_text=True)
    assert 'certificate' in body
    assert 'host and port' not in body


def test_opnsense_import_tls_failure_names_the_certificate(app, auth_client, monkeypatch):
    """Same for the import endpoint, whose generic handler said only
    'Import failed' (500)."""
    from api.v2 import import_opnsense

    monkeypatch.setattr(import_opnsense, "create_session",
                        lambda verify_ssl=True: _SSLFailingSession())

    r = auth_client.post(
        '/api/v2/import/opnsense/import',
        data=json.dumps({
            "host": "192.168.1.254",
            "port": 443,
            "api_key": "key",
            "api_secret": "secret",
            "items": [],
        }),
        content_type='application/json',
    )
    assert r.status_code == 400, r.data
    body = r.get_data(as_text=True)
    assert 'certificate' in body
    assert 'Import failed' not in body


def test_opnsense_explicit_verify_ssl_false_is_honored(app, auth_client, monkeypatch):
    """The opt-out must keep working: an explicit false reaches create_session."""
    from api.v2 import import_opnsense

    captured = {}
    monkeypatch.setattr(import_opnsense, "create_session", _capturing_session_factory(captured))

    r = auth_client.post(
        '/api/v2/import/opnsense/test',
        data=json.dumps({
            "host": "192.168.1.254",
            "port": 443,
            "api_key": "key",
            "api_secret": "secret",
            "verify_ssl": False,
        }),
        content_type='application/json',
    )
    assert r.status_code == 200, r.data
    assert captured['verify_ssl'] is False
