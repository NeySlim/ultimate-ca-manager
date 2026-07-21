"""RFC 7030 interoperability tests for the EST protocol endpoints."""
import base64
import builtins
from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser

import pytest
from asn1crypto import cms
from cryptography import x509
from cryptography.hazmat.primitives import hashes, padding, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding, rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.name import _ASN1Type
from cryptography.x509.oid import NameOID
from pyasn1.codec.der import decoder as der_decoder

from models import CA, db
from models.system_config import SystemConfig


EST_BASE = '/.well-known/est'
EST_USER = 'est-test'
EST_PASSWORD = 'est-password'


def _set_config(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if row is None:
        db.session.add(SystemConfig(key=key, value=value))
    else:
        row.value = value
    db.session.commit()


@pytest.fixture(scope='module')
def est_config(app, create_ca):
    ca_data = create_ca(cn='EST RFC 7030 CA')
    keys = ('est_enabled', 'est_ca_refid', 'est_username', 'est_password', 'est_validity_days')
    with app.app_context():
        previous = {
            key: (SystemConfig.query.filter_by(key=key).first().value
                  if SystemConfig.query.filter_by(key=key).first() else None)
            for key in keys
        }
        ca = db.session.get(CA, ca_data['id'])
        _set_config('est_enabled', 'true')
        _set_config('est_ca_refid', ca.refid)
        _set_config('est_username', EST_USER)
        _set_config('est_password', EST_PASSWORD)
        _set_config('est_validity_days', '30')

    yield ca_data

    with app.app_context():
        for key, value in previous.items():
            row = SystemConfig.query.filter_by(key=key).first()
            if value is None:
                if row is not None:
                    db.session.delete(row)
            elif row is None:
                db.session.add(SystemConfig(key=key, value=value))
            else:
                row.value = value
        db.session.commit()


def _basic_auth():
    token = base64.b64encode(f'{EST_USER}:{EST_PASSWORD}'.encode()).decode()
    return {'Authorization': f'Basic {token}'}


def _make_csr(common_name='device.example.test', san_names=(), extra_attributes=()):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    builder = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    )
    if san_names:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.DNSName(name) for name in san_names]),
            critical=False,
        )
    for oid, value in extra_attributes:
        builder = builder.add_attribute(
            x509.ObjectIdentifier(oid), value, _tag=_ASN1Type.OctetString
        )
    return builder.sign(key, hashes.SHA256()), key


def _make_client_certificate(common_name='device.example.test', san_names=()):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=30))
    )
    if san_names:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.DNSName(name) for name in san_names]),
            critical=False,
        )
    cert = builder.sign(key, hashes.SHA256())
    pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    return cert, key, pem


def _post_csr(client, path, csr, *, headers=None, client_cert_pem=None,
              content_type='application/pkcs10'):
    request_headers = dict(headers or {})
    body = base64.b64encode(csr.public_bytes(serialization.Encoding.DER))
    kwargs = {}
    if client_cert_pem is not None:
        kwargs['environ_overrides'] = {'peercert': client_cert_pem}
    return client.post(
        f'{EST_BASE}/{path}', data=body, headers=request_headers,
        content_type=content_type, **kwargs,
    )


def _multipart_parts(response):
    message = BytesParser(policy=policy.default).parsebytes(
        b'MIME-Version: 1.0\r\nContent-Type: '
        + response.headers['Content-Type'].encode()
        + b'\r\n\r\n'
        + response.data
    )
    assert message.is_multipart()
    return list(message.iter_parts())


def _unpad_aes_cbc(ciphertext, key, iv):
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


class TestSimpleEnroll:
    def test_rejects_non_pkcs10_content_type(self, client, est_config):
        csr, _ = _make_csr()
        response = _post_csr(
            client, 'simpleenroll', csr, headers=_basic_auth(),
            content_type='application/octet-stream',
        )
        assert response.status_code == 415

    def test_accepts_charset_and_returns_only_issued_certificate(self, client, est_config):
        csr, _ = _make_csr(san_names=('device.example.test',))
        response = _post_csr(
            client, 'simpleenroll', csr, headers=_basic_auth(),
            content_type='application/pkcs10; charset=us-ascii',
        )
        assert response.status_code == 200
        assert response.headers['Content-Type'] == (
            'application/pkcs7-mime; smime-type=certs-only'
        )
        assert response.headers['Content-Transfer-Encoding'] == 'base64'
        certs = pkcs7.load_der_pkcs7_certificates(base64.b64decode(response.data))
        assert len(certs) == 1
        assert certs[0].subject == csr.subject


class TestSimpleReenroll:
    def test_rejects_any_subject_alt_name_difference(self, client, est_config):
        _, _, client_pem = _make_client_certificate(
            san_names=('old.example.test', 'shared.example.test')
        )
        csr, _ = _make_csr(
            san_names=('new.example.test', 'shared.example.test')
        )
        response = _post_csr(
            client, 'simplereenroll', csr, client_cert_pem=client_pem,
        )
        assert response.status_code == 403
        assert b'subjectaltname' in response.data.lower()

    def test_matching_subject_and_san_returns_only_issued_certificate(self, client, est_config):
        names = ('device.example.test', 'alias.example.test')
        _, _, client_pem = _make_client_certificate(san_names=names)
        csr, _ = _make_csr(san_names=names)
        response = _post_csr(
            client, 'simplereenroll', csr, client_cert_pem=client_pem,
        )
        assert response.status_code == 200
        assert response.headers['Content-Type'] == (
            'application/pkcs7-mime; smime-type=certs-only'
        )
        certs = pkcs7.load_der_pkcs7_certificates(base64.b64decode(response.data))
        assert len(certs) == 1


class TestCsrAttrs:
    @pytest.mark.parametrize('without_pyasn1', [False, True])
    def test_is_public_and_returns_valid_csrattrs(self, client, est_config, monkeypatch,
                                                  without_pyasn1):
        if without_pyasn1:
            original_import = builtins.__import__

            def import_without_pyasn1(name, *args, **kwargs):
                if name == 'pyasn1' or name.startswith('pyasn1.'):
                    raise ImportError('pyasn1 deliberately unavailable')
                return original_import(name, *args, **kwargs)

            monkeypatch.setattr(builtins, '__import__', import_without_pyasn1)

        response = client.get(f'{EST_BASE}/csrattrs')
        assert response.status_code == 200
        assert response.headers['Content-Type'].startswith('application/csrattrs')

        der = base64.b64decode(response.data)
        attrs, trailing = der_decoder.decode(der)
        assert trailing == b''
        assert str(attrs[0]) == '1.2.840.113549.1.9.7'
        assert str(attrs[1][0]) == '1.2.840.113549.1.9.14'
        assert {str(oid) for oid in attrs[1][1]} == {
            '2.5.29.15', '2.5.29.17', '2.5.29.37'
        }


class TestCaCerts:
    def test_content_type_declares_certs_only(self, client, est_config):
        response = client.get(f'{EST_BASE}/cacerts')
        assert response.status_code == 200
        assert response.headers['Content-Type'] == (
            'application/pkcs7-mime; smime-type=certs-only'
        )


class TestServerKeygen:
    def test_basic_returns_encrypted_pkcs8_and_single_certificate(self, client, est_config):
        csr, _ = _make_csr(san_names=('basic.example.test',))
        response = _post_csr(
            client, 'serverkeygen', csr, headers=_basic_auth(),
        )
        assert response.status_code == 200
        parts = _multipart_parts(response)
        assert [part.get_content_type() for part in parts] == [
            'application/pkcs7-mime', 'application/pkcs8'
        ]
        assert parts[0].get_param('smime-type') == 'certs-only'
        certs = pkcs7.load_der_pkcs7_certificates(parts[0].get_payload(decode=True))
        assert len(certs) == 1
        generated_key = serialization.load_der_private_key(
            parts[1].get_payload(decode=True), password=EST_PASSWORD.encode()
        )
        assert generated_key.public_key().public_numbers() == certs[0].public_key().public_numbers()

    def test_mtls_ignores_invalid_csr_pop_preserves_san_and_returns_cms(self, client,
                                                                       est_config):
        client_cert, client_key, client_pem = _make_client_certificate('transport.example.test')
        key_identifier = x509.SubjectKeyIdentifier.from_public_key(
            client_cert.public_key()
        ).digest
        csr, _ = _make_csr(
            common_name='generated.example.test',
            san_names=('generated.example.test', 'alias.example.test'),
            extra_attributes=((
                '1.2.840.113549.1.9.16.2.54', key_identifier
            ),),
        )
        invalid_der = bytearray(csr.public_bytes(serialization.Encoding.DER))
        invalid_der[-1] ^= 0x01
        invalid_csr = x509.load_der_x509_csr(bytes(invalid_der))
        assert not invalid_csr.is_signature_valid

        response = _post_csr(
            client, 'serverkeygen', invalid_csr, client_cert_pem=client_pem,
        )
        assert response.status_code == 200
        parts = _multipart_parts(response)
        assert [part.get_content_type() for part in parts] == [
            'application/pkcs7-mime', 'application/pkcs7-mime'
        ]
        assert parts[0].get_param('smime-type') == 'certs-only'
        assert parts[1].get_param('smime-type') == 'server-generated-key'

        certs = pkcs7.load_der_pkcs7_certificates(parts[0].get_payload(decode=True))
        assert len(certs) == 1
        issued_san = certs[0].extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value
        assert issued_san == csr.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value

        enveloped = cms.ContentInfo.load(parts[1].get_payload(decode=True))
        assert enveloped['content_type'].native == 'enveloped_data'
        recipient_info = enveloped['content']['recipient_infos'][0]
        assert recipient_info.name == 'ktri'
        recipient = recipient_info.chosen
        encrypted_cek = recipient['encrypted_key'].native
        algorithm = recipient['key_encryption_algorithm']['algorithm'].native
        if algorithm == 'rsaes_oaep':
            cek = client_key.decrypt(
                encrypted_cek,
                asym_padding.OAEP(
                    mgf=asym_padding.MGF1(hashes.SHA256()),
                    algorithm=hashes.SHA256(), label=None,
                ),
            )
        else:
            cek = client_key.decrypt(encrypted_cek, asym_padding.PKCS1v15())

        encrypted_info = enveloped['content']['encrypted_content_info']
        assert encrypted_info['content_encryption_algorithm']['algorithm'].native == 'aes256_cbc'
        iv = encrypted_info['content_encryption_algorithm']['parameters'].native
        signed_der = _unpad_aes_cbc(encrypted_info['encrypted_content'].native, cek, iv)
        signed_data = cms.SignedData.load(signed_der)
        assert signed_data['encap_content_info']['content_type'].native == 'data'
        assert len(signed_data['signer_infos']) == 1
        private_key_der = signed_data['encap_content_info']['content'].native
        signer_info = signed_data['signer_infos'][0]
        certs[0].public_key().verify(
            signer_info['signature'].native,
            private_key_der,
            asym_padding.PKCS1v15(),
            hashes.SHA256(),
        )
        generated_key = serialization.load_der_private_key(
            private_key_der, password=None
        )
        assert generated_key.public_key().public_numbers() == certs[0].public_key().public_numbers()
