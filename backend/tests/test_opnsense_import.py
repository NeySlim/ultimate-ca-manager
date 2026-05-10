import base64
import datetime
import json

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

    def get(self, url, auth=None, timeout=None):
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
    monkeypatch.setattr(import_opnsense, "create_session", lambda verify_ssl=False: _Session(ca_rows, cert_rows))

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
