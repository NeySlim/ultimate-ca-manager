"""FIPS mode and the two legacy digests. MD5 is outside the module: the display
fingerprint becomes None and TSIG hmac-md5 is refused by UCM (hashlib and hmac
fall back to CPython's own MD5, so nothing below UCM would stop it). SHA-1 as
a non-signature digest stays: an OCSP CertID hashed with it is still answered."""
import base64
import json

import pytest
from cryptography import x509
from cryptography.exceptions import InternalError
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509 import ocsp

import fips_mode
from models import db, CA, Certificate, DnsProvider
from services.acme.dns_providers.rfc2136 import Rfc2136DnsProvider
from services.trust_store import TrustStoreService

TSIG_REFUSAL = 'TSIG hmac-md5 not available in FIPS mode'


@pytest.fixture
def fips_on(monkeypatch):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: True)


@pytest.fixture
def fips_off(monkeypatch):
    monkeypatch.setattr(fips_mode, 'enabled', lambda: False)


@pytest.fixture
def module_md5(monkeypatch):
    """pyca's MD5 as the FIPS module answers it."""
    def unsupported(*a, **k):
        raise InternalError('MD5 unsupported', [])
    monkeypatch.setattr(hashes, 'MD5', unsupported)


def _post(client, url, body):
    return client.post(url, data=json.dumps(body), content_type='application/json')


def _pem(app, create_cert, cn):
    cert = create_cert(cn=cn)
    with app.app_context():
        return base64.b64decode(db.session.get(Certificate, cert['id']).crt)


# ── MD5 fingerprint ────────────────────────────────────────────

def test_md5_fingerprint_is_none_in_fips_mode(fips_on, module_md5, app, create_cert):
    fps = TrustStoreService.get_certificate_fingerprints(_pem(app, create_cert, 'fp-fips.test'))
    assert fps['md5'] is None
    assert len(fps['sha1'].split(':')) == 20 and len(fps['sha256'].split(':')) == 32


def test_md5_fingerprint_unchanged_outside_fips_mode(fips_off, app, create_cert):
    fps = TrustStoreService.get_certificate_fingerprints(_pem(app, create_cert, 'fp-std.test'))
    assert len(fps['md5'].split(':')) == 16


# ── TSIG hmac-md5 ──────────────────────────────────────────────

def _tsig_options():
    field = next(f for f in Rfc2136DnsProvider.get_credential_schema() if f['name'] == 'tsig_algorithm')
    return [o['value'] for o in field['options']]


def _rfc2136(algorithm, name):
    return {'name': name, 'provider_type': 'rfc2136',
            'credentials': {'server': '192.0.2.53', 'tsig_key_name': 'acme.example.test',
                            'tsig_key_secret': base64.b64encode(b'k' * 32).decode(),
                            'tsig_algorithm': algorithm}}


def _assert_refused(r, message):
    body = r.get_json()
    assert r.status_code == 400, (r.status_code, r.data[:300])
    assert body['type'] == fips_mode.PROBLEM_TYPE, body
    assert body['message'] == message, body


def test_hmac_md5_not_offered_in_fips_mode(fips_on):
    assert 'hmac-md5' not in _tsig_options()
    assert 'hmac-sha256' in _tsig_options()


def test_hmac_md5_still_offered_outside_fips_mode(fips_off):
    assert 'hmac-md5' in _tsig_options()


def test_creating_hmac_md5_provider_is_refused_in_fips_mode(fips_on, auth_client):
    _assert_refused(_post(auth_client, '/api/v2/dns-providers', _rfc2136('HMAC-MD5', 'tsig-md5-fips')),
                    TSIG_REFUSAL)


def test_switching_a_provider_to_hmac_md5_is_refused_in_fips_mode(fips_on, auth_client, app):
    r = _post(auth_client, '/api/v2/dns-providers', _rfc2136('hmac-sha256', 'tsig-switch-fips'))
    assert r.status_code == 201, r.data
    pid = r.get_json()['data']['id']
    r = auth_client.patch(f'/api/v2/dns-providers/{pid}', data=json.dumps(
        {'name': 'tsig-switch-renamed', 'credentials': {'tsig_algorithm': 'hmac-md5'}}),
        content_type='application/json')
    _assert_refused(r, TSIG_REFUSAL)
    assert _post(auth_client, '/api/v2/dns-providers', _rfc2136('hmac-sha256', 'tsig-after')).status_code == 201
    with app.app_context():
        row = db.session.get(DnsProvider, pid)
        assert row.name == 'tsig-switch-fips'
        assert json.loads(row.credentials)['tsig_algorithm'] == 'hmac-sha256'


def test_hmac_md5_provider_still_created_outside_fips_mode(fips_off, auth_client):
    r = _post(auth_client, '/api/v2/dns-providers', _rfc2136('hmac-md5', 'tsig-md5-std'))
    assert r.status_code == 201, r.data


def test_existing_hmac_md5_provider_sends_nothing_in_fips_mode(fips_on, monkeypatch):
    """A provider saved before the switch fails with the reason, before any packet."""
    import dns.query
    sent = []
    monkeypatch.setattr(dns.query, 'tcp', lambda *a, **k: sent.append(a))
    provider = Rfc2136DnsProvider(_rfc2136('hmac-md5', 'x')['credentials'])
    monkeypatch.setattr(provider, '_find_zone', lambda domain: 'example.test')
    assert provider.create_txt_record('example.test', '_acme-challenge.example.test', 'v') == (False, TSIG_REFUSAL)
    assert provider.delete_txt_record('example.test', '_acme-challenge.example.test') == (False, TSIG_REFUSAL)
    ok, message = provider.test_connection()
    assert not ok and TSIG_REFUSAL in message
    assert sent == []


# ── SHA-1 CertID (lock: nothing may refuse it in FIPS mode) ────

def test_ocsp_sha1_certid_is_answered_in_fips_mode(fips_on, app, client, create_ca, create_cert):
    ca = create_ca(cn='FIPS OCSP SHA1 CA')
    cert = create_cert(cn='fips-ocsp-sha1.test', ca_id=ca['id'])
    with app.app_context():
        ca_row = db.session.get(CA, ca['id'])
        ca_row.ocsp_enabled = True
        db.session.commit()
        issuer = x509.load_pem_x509_certificate(base64.b64decode(ca_row.crt))
        leaf = x509.load_pem_x509_certificate(base64.b64decode(db.session.get(Certificate, cert['id']).crt))
    req = ocsp.OCSPRequestBuilder().add_certificate(leaf, issuer, hashes.SHA1()).build()
    r = client.post('/ocsp', data=req.public_bytes(serialization.Encoding.DER),
                    content_type='application/ocsp-request')
    assert r.status_code == 200
    resp = ocsp.load_der_ocsp_response(r.data)
    assert resp.response_status == ocsp.OCSPResponseStatus.SUCCESSFUL
    single = next(iter(resp.responses))
    assert isinstance(single.hash_algorithm, hashes.SHA1)
    assert single.serial_number == leaf.serial_number
    assert single.certificate_status == ocsp.OCSPCertStatus.GOOD
