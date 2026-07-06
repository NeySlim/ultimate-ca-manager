"""
Issuer signature vs end-entity key type — regression and security tests.

X.509: signature_algorithm on a certificate is how the *issuing CA* signed it,
not the EE public key algorithm. EC EE certs issued by an RSA CA must show
SHA256-RSA (or similar) while the public key remains EC.
"""
import json

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from tests.conftest import assert_success

CONTENT_JSON = 'application/json'
BASE = '/api/v2/certificates'
CAS = '/api/v2/cas'

RSA_SIG_OIDS = {
    '1.2.840.113549.1.1.11',  # sha256WithRSAEncryption
    '1.2.840.113549.1.1.12',
    '1.2.840.113549.1.1.13',
}
EC_SIG_OIDS = {
    '1.2.840.10045.4.3.2',  # ecdsa-with-SHA256
    '1.2.840.10045.4.3.3',
    '1.2.840.10045.4.3.4',
}


def post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type=CONTENT_JSON)


def _export_pem(auth_client, cert_id):
    r = auth_client.get(f'{BASE}/{cert_id}/export?format=pem')
    assert r.status_code == 200, r.data
    return r.data


def _load_x509(pem_bytes):
    return x509.load_pem_x509_certificate(pem_bytes, default_backend())


class TestIssuerSignatureIndependence:
    """Non-regression: EE key type must not dictate issuer signature algorithm."""

    def test_ec_p521_ee_with_rsa_ca_has_rsa_issuer_signature(self, auth_client, create_ca):
        ca = create_ca(cn='RSA CA EC EE Test', keyType='RSA', keySize=2048)
        ca_id = ca.get('id', ca.get('ca_id'))
        r = post_json(auth_client, BASE, {
            'cn': 'ec-ee-rsa-ca.example.com',
            'ca_id': ca_id,
            'validity_days': 90,
            'key_type': 'ecdsa',
            'key_size': '521',
        })
        created = assert_success(r, status=201)
        cert = _load_x509(_export_pem(auth_client, created['id']))
        pub = cert.public_key()
        assert isinstance(pub, ec.EllipticCurvePublicKey)
        assert pub.curve.name == 'secp521r1'
        assert cert.signature_algorithm_oid.dotted_string in RSA_SIG_OIDS

        detail = assert_success(auth_client.get(f'{BASE}/{created["id"]}'))
        assert 'EC' in (detail.get('key_type') or '').upper()
        assert 'RSA' in (detail.get('signature_algorithm') or '').upper()

    def test_rsa_ee_with_rsa_ca_still_sha256_rsa(self, auth_client, create_ca):
        ca = create_ca(cn='RSA CA RSA EE Test')
        ca_id = ca.get('id', ca.get('ca_id'))
        r = post_json(auth_client, BASE, {
            'cn': 'rsa-ee.example.com',
            'ca_id': ca_id,
            'validity_days': 90,
            'key_type': 'rsa',
            'key_size': '2048',
        })
        created = assert_success(r, status=201)
        cert = _load_x509(_export_pem(auth_client, created['id']))
        assert isinstance(cert.public_key(), rsa.RSAPublicKey)
        assert cert.signature_algorithm_oid.dotted_string in RSA_SIG_OIDS

    def test_ec_ee_with_ecdsa_ca_has_ecdsa_issuer_signature(self, auth_client):
        ca_r = post_json(auth_client, CAS, {
            'type': 'root',
            'commonName': 'ECDSA Issuer For EE Test',
            'organization': 'Test Org',
            'country': 'US',
            'state': 'CA',
            'locality': 'Test City',
            'keyAlgo': 'ECDSA',
            'keySize': 'prime256v1',
            'validityYears': 5,
            'hashAlgorithm': 'sha256',
        })
        ca = assert_success(ca_r, status=201)
        ca_id = ca['id']
        r = post_json(auth_client, BASE, {
            'cn': 'ec-under-ec-ca.example.com',
            'ca_id': ca_id,
            'validity_days': 90,
            'key_type': 'ecdsa',
            'key_size': '256',
        })
        created = assert_success(r, status=201)
        cert = _load_x509(_export_pem(auth_client, created['id']))
        assert isinstance(cert.public_key(), ec.EllipticCurvePublicKey)
        assert cert.signature_algorithm_oid.dotted_string in EC_SIG_OIDS


class TestIssuanceSecurityRegression:
    """Security: typed SAN and key validation cannot be bypassed on issuance."""

    def test_rejects_email_in_san_dns_bucket(self, auth_client, create_ca):
        ca = create_ca(cn='SAN DNS Email Reject CA')
        ca_id = ca.get('id', ca.get('ca_id'))
        r = post_json(auth_client, BASE, {
            'cn': 'sec-dns.example.com',
            'ca_id': ca_id,
            'validity_days': 90,
            'san_dns': ['user@example.com'],
        })
        assert r.status_code == 400
        body = json.loads(r.data)
        assert 'Email' in body.get('message', '')

    def test_rejects_invalid_ec_curve_size(self, auth_client, create_ca):
        ca = create_ca(cn='Invalid EC Curve CA')
        ca_id = ca.get('id', ca.get('ca_id'))
        r = post_json(auth_client, BASE, {
            'cn': 'bad-curve.example.com',
            'ca_id': ca_id,
            'validity_days': 90,
            'key_type': 'ecdsa',
            'key_size': '999',
        })
        assert r.status_code == 400

    def test_legacy_san_string_non_regression(self, auth_client, create_ca):
        ca = create_ca(cn='Legacy SAN String CA')
        ca_id = ca.get('id', ca.get('ca_id'))
        r = post_json(auth_client, BASE, {
            'cn': 'legacy-san.example.com',
            'ca_id': ca_id,
            'validity_days': 90,
            'san': 'DNS:legacy-san.example.com, IP:10.10.10.10',
            'key_type': 'rsa',
            'key_size': '2048',
        })
        created = assert_success(r, status=201)
        detail = assert_success(auth_client.get(f'{BASE}/{created["id"]}'))
        san_dns = detail.get('san_dns') or []
        if isinstance(san_dns, str) and san_dns.startswith('['):
            san_dns = json.loads(san_dns)
        assert 'legacy-san.example.com' in san_dns


class TestComplianceSignatureScoring:
    """Compliance score uses issuer signature hash, not EE key type."""

    def test_ec_ee_rsa_ca_signature_scores_sha256(self, auth_client, create_ca):
        from services.compliance_service import calculate_compliance_score

        ca = create_ca(cn='Compliance EC EE CA')
        ca_id = ca.get('id', ca.get('ca_id'))
        r = post_json(auth_client, BASE, {
            'cn': 'compliance-ec.example.com',
            'ca_id': ca_id,
            'validity_days': 90,
            'key_type': 'ecdsa',
            'key_size': '521',
        })
        created = assert_success(r, status=201)
        detail = assert_success(auth_client.get(f'{BASE}/{created["id"]}'))
        score = calculate_compliance_score(detail)
        assert score['breakdown']['key_strength']['score'] == 30
        assert 'ECDSA' in score['breakdown']['key_strength']['reason'].upper() or 'P-521' in score['breakdown']['key_strength']['reason']
        assert score['breakdown']['signature']['reason'] == 'SHA-256'
        assert score['breakdown']['signature']['score'] == 22
