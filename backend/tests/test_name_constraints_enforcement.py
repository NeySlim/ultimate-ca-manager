"""Regression tests for RFC 5280 constraint enforcement during issuance."""
import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtensionOID, NameOID

from models import CA, db
from services.hsm.ca_key_loader import get_ca_signing_key
from services.trust_store import TrustStoreService
from tests.conftest import get_json


def _ca_with_name_constraints(app, ca_id):
    """Replace a fixture CA certificate with one using the same key plus constraints."""
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        key = get_ca_signing_key(ca)
        current = x509.load_pem_x509_certificate(base64.b64decode(ca.crt))
        now = datetime.now(timezone.utc)
        constrained = (
            x509.CertificateBuilder()
            .subject_name(current.subject)
            .issuer_name(current.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=3650))
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=None), critical=True
            )
            .add_extension(
                x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
                critical=False,
            )
            .add_extension(
                x509.NameConstraints(
                    permitted_subtrees=None,
                    excluded_subtrees=[x509.DNSName('.blocked.example')],
                ),
                critical=True,
            )
            .sign(key, hashes.SHA256())
        )
        ca.crt = base64.b64encode(
            constrained.public_bytes(serialization.Encoding.PEM)
        ).decode()
        db.session.commit()


def _csr(*extensions):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    builder = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'leaf.example.com')])
    )
    for value, critical in extensions:
        builder = builder.add_extension(value, critical=critical)
    return builder.sign(key, hashes.SHA256())


def _test_ca():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Constraint Test CA')])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    return cert, key


def _sign(csr, cert_type):
    ca_cert, ca_key = _test_ca()
    pem = TrustStoreService.sign_csr(
        csr_pem=csr.public_bytes(serialization.Encoding.PEM),
        ca_cert=ca_cert,
        ca_private_key=ca_key,
        validity_days=30,
        cert_type=cert_type,
    )
    return x509.load_pem_x509_certificate(pem)


class TestDirectCertificateNameConstraints:
    def test_create_rejects_and_lists_excluded_san_names(
        self, app, auth_client, create_ca
    ):
        ca = create_ca(cn='Direct Constraint CA')
        _ca_with_name_constraints(app, ca['id'])

        response = auth_client.post(
            '/api/v2/certificates',
            data=json.dumps({
                'cn': 'allowed.example.com',
                'ca_id': ca['id'],
                'validity_days': 30,
                'san_dns': [
                    'first.blocked.example',
                    'second.blocked.example',
                ],
            }),
            content_type='application/json',
        )

        assert response.status_code == 400
        message = get_json(response).get('message', '')
        assert 'NameConstraints' in message
        assert 'first.blocked.example' in message
        assert 'second.blocked.example' in message


class TestCsrConstraintExtensionPolicy:
    def test_leaf_filters_ca_only_constraint_extensions(self):
        csr = _csr(
            (x509.BasicConstraints(ca=True, path_length=1), True),
            (
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=True,
                    encipher_only=False,
                    decipher_only=False,
                ),
                True,
            ),
            (
                x509.NameConstraints(
                    permitted_subtrees=[x509.DNSName('.example.com')],
                    excluded_subtrees=None,
                ),
                True,
            ),
            (x509.PolicyConstraints(require_explicit_policy=0, inhibit_policy_mapping=0), True),
            (x509.InhibitAnyPolicy(skip_certs=0), True),
        )

        cert = _sign(csr, 'server_cert')
        basic = cert.extensions.get_extension_for_oid(
            ExtensionOID.BASIC_CONSTRAINTS
        ).value
        usage = cert.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE).value

        assert basic.ca is False
        assert usage.key_cert_sign is False
        assert usage.crl_sign is False
        for oid in (
            ExtensionOID.NAME_CONSTRAINTS,
            ExtensionOID.POLICY_CONSTRAINTS,
            ExtensionOID.INHIBIT_ANY_POLICY,
        ):
            with pytest.raises(x509.ExtensionNotFound):
                cert.extensions.get_extension_for_oid(oid)

    def test_intermediate_rejects_basic_constraints_ca_false(self):
        csr = _csr((x509.BasicConstraints(ca=False, path_length=None), True))

        with pytest.raises(ValueError, match='BasicConstraints.*ca=True'):
            _sign(csr, 'intermediate_ca')

    def test_intermediate_imposes_ca_signing_key_usage(self):
        csr = _csr(
            (x509.BasicConstraints(ca=True, path_length=0), True),
            (
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                True,
            ),
        )

        cert = _sign(csr, 'intermediate_ca')
        basic = cert.extensions.get_extension_for_oid(
            ExtensionOID.BASIC_CONSTRAINTS
        ).value
        usage = cert.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE).value

        assert basic.ca is True
        assert usage.key_cert_sign is True
        assert usage.crl_sign is True
