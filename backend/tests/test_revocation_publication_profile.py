"""OCSP HTTP profile (RFC 5019 §6.2, RFC 9110 §8.3.1), OCSP statistics, a hold
revoked for good, and the delta CRL that follows its base (RFC 5280 §5.2.4)."""
import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509 import ocsp
from cryptography.x509.oid import NameOID
from flask import Response

from models import db, CA, Certificate
from models.crl import CRLMetadata

from tests.test_ocsp_service import _ca_model, _cert_model, _load_x509


def _post(client, url, body):
    return client.post(url, data=json.dumps(body), content_type='application/json')


def _ocsp_request(cert, issuer, nonce=False):
    builder = ocsp.OCSPRequestBuilder().add_certificate(cert, issuer, hashes.SHA256())
    if nonce:
        builder = builder.add_extension(x509.OCSPNonce(b'\x01' * 16), critical=False)
    return builder.build().public_bytes(serialization.Encoding.DER)


def _ocsp_ca(create_ca, create_cert, cn):
    ca = create_ca(cn=cn)
    row = _ca_model(ca)
    row.ocsp_enabled = True
    row.cdp_enabled = True
    db.session.commit()
    leaf = create_cert(cn=f'leaf.{cn.lower().replace(" ", "-")}.example.com', ca_id=ca['id'])
    return ca, leaf, _load_x509(row), _load_x509(_cert_model(leaf))


def _ask(client, cert, issuer, nonce=False, content_type='application/ocsp-request'):
    r = client.post('/ocsp', data=_ocsp_request(cert, issuer, nonce), content_type=content_type)
    assert r.status_code == 200
    return r, ocsp.load_der_ocsp_response(r.data)


# --------------------------------------------------------------------------
# HTTP profile
# --------------------------------------------------------------------------

def test_the_request_media_type_ignores_case(app, client, create_ca, create_cert):
    with app.app_context():
        _ca, _leaf, issuer, cert = _ocsp_ca(create_ca, create_cert, 'Media Type Case CA')
        _r, parsed = _ask(client, cert, issuer, content_type='Application/OCSP-Request')
        assert parsed.response_status == ocsp.OCSPResponseStatus.SUCCESSFUL


def test_an_authoritative_answer_is_cacheable_until_next_update(app, client, create_ca, create_cert):
    with app.app_context():
        _ca, _leaf, issuer, cert = _ocsp_ca(create_ca, create_cert, 'Cache Header CA')
        for _ in range(2):  # generated, then served from the cache
            r, parsed = _ask(client, cert, issuer)
            control = r.headers['Cache-Control']
            assert 'no-cache' not in control and 'no-store' not in control
            assert 'public' in control and 'must-revalidate' in control
            max_age = int(control.split('max-age=')[1].split(',')[0])
            remaining = (parsed.next_update_utc - datetime.now(timezone.utc)).total_seconds()
            assert 0 < max_age <= min(3600, remaining + 1)
            assert parsedate_to_datetime(r.headers['Expires']) == parsed.next_update_utc.replace(microsecond=0)
            assert parsedate_to_datetime(r.headers['Last-Modified']) == parsed.this_update_utc.replace(microsecond=0)
            assert r.headers['ETag'] == f'"{hashlib.sha1(r.data, usedforsecurity=False).hexdigest()}"'


def test_a_nonce_answer_is_never_marked_no_store(app, client, create_ca, create_cert):
    with app.app_context():
        _ca, _leaf, issuer, cert = _ocsp_ca(create_ca, create_cert, 'Nonce Header CA')
        r, parsed = _ask(client, cert, issuer, nonce=True)
        assert parsed.response_status == ocsp.OCSPResponseStatus.SUCCESSFUL
        control = r.headers.get('Cache-Control', '')
        assert 'no-store' not in control and 'no-cache' not in control
        assert 'Pragma' not in r.headers


def test_max_age_never_passes_next_update():
    from api.ocsp_routes import _add_cache_headers

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Header Unit CA')])
    now = datetime.now(timezone.utc)
    issuer = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
              .public_key(key.public_key()).serial_number(1)
              .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=1))
              .sign(key, hashes.SHA256()))
    response = (ocsp.OCSPResponseBuilder()
                .add_response(cert=issuer, issuer=issuer, algorithm=hashes.SHA256(),
                              cert_status=ocsp.OCSPCertStatus.GOOD,
                              this_update=now - timedelta(minutes=50),
                              next_update=now + timedelta(minutes=10),
                              revocation_time=None, revocation_reason=None)
                .responder_id(ocsp.OCSPResponderEncoding.HASH, issuer)
                .sign(key, hashes.SHA256())
                .public_bytes(serialization.Encoding.DER))
    resp = Response(response)
    _add_cache_headers(resp, None, response)
    max_age = int(resp.headers['Cache-Control'].split('max-age=')[1].split(',')[0])
    assert 0 < max_age <= 600


def test_statistics_count_requests_and_cache_hits(app, client, auth_client, create_ca, create_cert):
    with app.app_context():
        _ca, _leaf, issuer, cert = _ocsp_ca(create_ca, create_cert, 'Stats CA')

        def stats():
            return json.loads(auth_client.get('/api/v2/ocsp/stats').data)['data']

        before = stats()
        _ask(client, cert, issuer)               # generated and cached
        _ask(client, cert, issuer)               # from the cache
        _ask(client, cert, issuer, nonce=True)   # never from the cache
        encoded = base64.b64encode(_ocsp_request(cert, issuer)).decode()
        assert client.get(f'/ocsp/{quote(encoded, safe="")}').status_code == 200  # cached, by GET
        after = stats()
        assert after['total_requests'] - before['total_requests'] == 4
        assert after['cache_hits'] - before['cache_hits'] == 2


# --------------------------------------------------------------------------
# A hold revoked for good
# --------------------------------------------------------------------------

def _crl_entry(ca_id, serial):
    row = CRLMetadata.query.filter_by(ca_id=ca_id, is_delta=False).order_by(
        CRLMetadata.crl_number.desc()).first()
    return x509.load_der_x509_crl(row.crl_der).get_revoked_certificate_by_serial_number(serial)


def test_a_certificate_on_hold_can_be_revoked_for_good(app, client, auth_client, create_ca, create_cert):
    with app.app_context():
        ca, leaf, issuer, cert = _ocsp_ca(create_ca, create_cert, 'Hold Final CA')
        url = f"/api/v2/certificates/{leaf['id']}/revoke"
        assert _post(auth_client, url, {'reason': 'certificateHold'}).status_code == 200
        held_at = db.session.get(Certificate, leaf['id']).revoked_at
        assert _post(auth_client, url, {'reason': 'certificateHold'}).status_code == 400

        r = _post(auth_client, url, {'reason': 'keyCompromise'})
        assert r.status_code == 200, r.data
        db.session.expire_all()
        row = db.session.get(Certificate, leaf['id'])
        assert row.revoke_reason == 'keyCompromise'
        assert row.invalidity_at == held_at
        entry = _crl_entry(ca['id'], cert.serial_number)
        assert entry.extensions.get_extension_for_class(x509.CRLReason).value.reason \
            == x509.ReasonFlags.key_compromise
        _r, parsed = _ask(client, cert, issuer)
        assert parsed.certificate_status == ocsp.OCSPCertStatus.REVOKED
        assert parsed.revocation_reason == x509.ReasonFlags.key_compromise
        assert _post(auth_client, url, {'reason': 'superseded'}).status_code == 400


def test_bulk_revocation_finalises_a_hold(app, auth_client, create_ca, create_cert):
    with app.app_context():
        _ca, leaf, _issuer, _cert = _ocsp_ca(create_ca, create_cert, 'Bulk Hold CA')
        assert _post(auth_client, f"/api/v2/certificates/{leaf['id']}/revoke",
                     {'reason': 'certificateHold'}).status_code == 200
        r = _post(auth_client, '/api/v2/certificates/bulk/revoke',
                  {'ids': [leaf['id']], 'reason': 'cessationOfOperation'})
        assert r.status_code == 200, r.data
        assert leaf['id'] in json.loads(r.data)['data']['success']
        db.session.expire_all()
        assert db.session.get(Certificate, leaf['id']).revoke_reason == 'cessationOfOperation'


# --------------------------------------------------------------------------
# The delta follows its base
# --------------------------------------------------------------------------

def test_the_delta_served_after_a_revocation_is_on_the_new_base(app, auth_client, create_ca, create_cert):
    from services.crl_service import CRLService

    with app.app_context():
        ca, leaf, _issuer, _cert = _ocsp_ca(create_ca, create_cert, 'Delta Follows CA')
        row = db.session.get(CA, ca['id'])
        row.delta_crl_enabled = True
        db.session.commit()
        CRLService.generate_crl(ca['id'])
        assert _post(auth_client, f"/api/v2/certificates/{leaf['id']}/revoke",
                     {'reason': 'keyCompromise'}).status_code == 200
        base = CRLService.get_latest_base_crl(ca['id'])
        delta = CRLService.get_latest_delta_crl(ca['id'])
        assert delta.base_crl_number == base.crl_number
        assert delta.crl_number > base.crl_number
