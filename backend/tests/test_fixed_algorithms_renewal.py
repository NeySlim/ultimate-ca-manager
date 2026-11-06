"""A renewal keeps the original's signature hash while the CA key and the
policies allow it, else the issuance rule, with a log line (#397 follow-up)."""
import base64
import json
import logging

from cryptography import x509
from cryptography.hazmat.primitives import hashes

from models import Certificate, db
from models.certificate_template import CertificateTemplate
from models.policy import CertificatePolicy
from services.cert.renewal import renew_certificate_in_place
from tests.conftest import get_json
from tests.test_fixed_algorithms_digest import _template
from tests.test_policy_algorithms_397 import _drop, _policy


def _p384_ca(create_ca, cn):
    return create_ca(cn=cn, keyAlgo='EC-P384', keyType='EC-P384', keySize='secp384r1',
                     hashAlgorithm='sha384')


def _issue(auth_client, ca_id, cn, template_id, **extra):
    payload = {'cn': cn, 'ca_id': ca_id, 'key_type': 'rsa', 'key_size': 2048,
               'validity_days': 30, 'template_id': template_id, **extra}
    r = auth_client.post('/api/v2/certificates', data=json.dumps(payload),
                         content_type='application/json')
    assert r.status_code in (200, 201), r.data
    return get_json(r)['data']['id']


def _hash_of(app, cert_id):
    with app.app_context():
        row = db.session.get(Certificate, cert_id)
        return x509.load_pem_x509_certificate(base64.b64decode(row.crt)).signature_hash_algorithm


def _renew(app, cert_id):
    with app.app_context():
        renew_certificate_in_place(db.session.get(Certificate, cert_id), username='admin')


def test_renewal_keeps_a_sha256_original_under_a_p384_ca(app, auth_client, create_ca):
    ca = _p384_ca(create_ca, 'Renew keep P-384 CA')
    tid = _template(app, 'renew-keep-sha256', 'sha256')
    cid = _issue(auth_client, ca['id'], 'keep.renew.test', tid)
    try:
        assert isinstance(_hash_of(app, cid), hashes.SHA256)
        _renew(app, cid)
        assert isinstance(_hash_of(app, cid), hashes.SHA256)
    finally:
        _drop(app, Certificate, cid)
        _drop(app, CertificateTemplate, tid)


def test_a_policy_refusing_the_original_hash_takes_the_rule_and_logs(app, auth_client, create_ca, caplog):
    ca = create_ca(cn='Renew policy CA')
    tid = _template(app, 'renew-policy-sha256', 'sha256')
    cid = _issue(auth_client, ca['id'], 'policy.renew.test', tid)
    pid = _policy(app, 'renew-strong-only', ca['id'], {'allowed_digests': ['sha384', 'sha512']})
    try:
        with caplog.at_level(logging.INFO, logger='services.cert.renewal'):
            _renew(app, cid)
        assert isinstance(_hash_of(app, cid), hashes.SHA384)
        assert any('instead of the original SHA256' in r.getMessage() for r in caplog.records)
    finally:
        _drop(app, CertificatePolicy, pid)
        _drop(app, Certificate, cid)
        _drop(app, CertificateTemplate, tid)


def test_ocsp_responder_renewal_keeps_the_original_hash(app, auth_client, create_ca):
    from services.ocsp_responder_renewal import _renew_responder_cert
    from models import CA
    ca = create_ca(cn='Renew OCSP responder CA')
    tid = _template(app, 'renew-ocsp-sha512', 'sha512')
    cid = _issue(auth_client, ca['id'], 'ocsp.renew.test', tid, cert_type='custom',
                 extra_ekus=['OCSPSigning'])
    try:
        assert isinstance(_hash_of(app, cid), hashes.SHA512)
        with app.app_context():
            renewed = _renew_responder_cert(db.session.get(CA, ca['id']),
                                            db.session.get(Certificate, cid))
            signed = x509.load_pem_x509_certificate(base64.b64decode(renewed.crt))
            db.session.rollback()
        assert isinstance(signed.signature_hash_algorithm, hashes.SHA512)
    finally:
        _drop(app, Certificate, cid)
        _drop(app, CertificateTemplate, tid)
