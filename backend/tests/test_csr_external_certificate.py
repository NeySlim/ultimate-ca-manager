"""
A CSR generated in UCM, signed by an external CA, then imported (#341).

The imported certificate must complete the pending CSR record, which keeps
its private key, instead of becoming a separate keyless record.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CSRS = '/api/v2/csrs'
CERTS = '/api/v2/certificates'


def _json(r):
    return json.loads(r.data)


def _create_csr(auth_client, cn, sans=None):
    r = auth_client.post(CSRS,
                         data=json.dumps({
                             'cn': cn, 'organization': 'Requester Org', 'country': 'US',
                             'key_type': 'RSA 2048',
                             'sans': sans if sans is not None else [f'DNS:{cn}'],
                         }),
                         content_type='application/json')
    assert r.status_code in (200, 201), r.data
    return _json(r)['data']


def _csr_pem(auth_client, csr_id):
    r = auth_client.get(f'{CSRS}/{csr_id}/export')
    assert r.status_code == 200
    return r.data


def _external_ca(cn='External Test Root'):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, cn),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'External CA Org'),
    ])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .sign(key, hashes.SHA256())
    )
    return key, cert


def _sign_externally(ca_key, ca_cert, csr_pem, days=90, public_key=None, subject=None):
    """What a public CA does with the CSR: its own serial, its own validity,
    the CSR's subject and SANs, the CSR's key (or another one, to build a
    certificate that must NOT match)."""
    csr = x509.load_pem_x509_csr(csr_pem)
    now = datetime.now(timezone.utc)
    pub = public_key or csr.public_key()
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject or csr.subject).issuer_name(ca_cert.subject)
        .public_key(pub)
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=days))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(pub), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
    )
    try:
        san = csr.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        builder = builder.add_extension(san, critical=False)
    except x509.ExtensionNotFound:
        pass
    return builder.sign(ca_key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM)


def _import(auth_client, pem, **form):
    data = {'pem_content': pem.decode() if isinstance(pem, bytes) else pem}
    data.update(form)
    return auth_client.post(f'{CERTS}/import', data=data, content_type='multipart/form-data')


def _pending_ids(auth_client):
    r = auth_client.get(f'{CSRS}?per_page=100')
    assert r.status_code == 200
    return {c['id'] for c in _json(r)['data']}


@pytest.fixture(scope='module')
def external_ca():
    return _external_ca()


class TestExternalCertificateCompletesCSR:

    def test_import_attaches_certificate_to_pending_csr(self, auth_client, external_ca):
        ca_key, ca_cert = external_ca
        csr = _create_csr(auth_client, 'ext-signed.example.com')
        assert csr['has_private_key'] is True
        leaf_pem = _sign_externally(ca_key, ca_cert, _csr_pem(auth_client, csr['id']))

        r = _import(auth_client, leaf_pem)
        assert r.status_code == 200, r.data
        body = _json(r)
        assert 'pending CSR' in body['message']
        data = body['data']
        assert data['id'] == csr['id']
        assert data['has_private_key'] is True
        assert data['descr'] == 'ext-signed.example.com'
        assert data['common_name'] == 'ext-signed.example.com'
        assert 'External Test Root' in data['issuer']
        assert data['serial_number'] and data['valid_to']
        assert data['status'] == 'valid'
        assert json.loads(data['san_dns']) == ['ext-signed.example.com']
        assert data['caref'] is None  # the issuer is not a CA UCM holds

        # Moved from the pending tab to the certificates
        assert csr['id'] not in _pending_ids(auth_client)
        r = auth_client.get(f'{CERTS}/{csr["id"]}')
        assert r.status_code == 200
        assert _json(r)['data']['pem'].startswith('-----BEGIN CERTIFICATE-----')
        r = auth_client.get(f'{CSRS}/history?per_page=100')
        assert csr['id'] in {c['id'] for c in _json(r)['data']}

        # The key stayed with the certificate: exportable with it
        r = auth_client.get(f'{CERTS}/{csr["id"]}/export?format=key')
        assert r.status_code == 200
        assert b'PRIVATE KEY' in r.data
        r = auth_client.post(f'{CERTS}/{csr["id"]}/export',
                             data=json.dumps({'format': 'pkcs12', 'password': 'p12pass'}),
                             content_type='application/json')
        assert r.status_code == 200, r.data

    def test_reimport_of_completed_certificate_updates_it(self, auth_client, external_ca):
        ca_key, ca_cert = external_ca
        csr = _create_csr(auth_client, 'ext-reimport.example.com')
        leaf_pem = _sign_externally(ca_key, ca_cert, _csr_pem(auth_client, csr['id']))
        assert _import(auth_client, leaf_pem).status_code == 200
        # Same subject + issuer now: the existing-certificate path, no new record
        r = _import(auth_client, leaf_pem)
        assert r.status_code == 200, r.data
        assert _json(r)['data']['id'] == csr['id']
        assert _json(r)['data']['has_private_key'] is True

    def test_name_overrides_descr(self, auth_client, external_ca):
        ca_key, ca_cert = external_ca
        csr = _create_csr(auth_client, 'ext-named.example.com')
        leaf_pem = _sign_externally(ca_key, ca_cert, _csr_pem(auth_client, csr['id']))
        r = _import(auth_client, leaf_pem, name='Public web server')
        assert r.status_code == 200, r.data
        assert _json(r)['data']['id'] == csr['id']
        assert _json(r)['data']['descr'] == 'Public web server'

    def test_subject_rewritten_by_the_ca_still_matches(self, auth_client, external_ca):
        """Public CAs often strip O/C or keep only the CN: the key is the link."""
        ca_key, ca_cert = external_ca
        csr = _create_csr(auth_client, 'ext-subject.example.com')
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'ext-subject.example.com')])
        leaf_pem = _sign_externally(ca_key, ca_cert, _csr_pem(auth_client, csr['id']), subject=subject)
        r = _import(auth_client, leaf_pem)
        assert r.status_code == 200, r.data
        data = _json(r)['data']
        assert data['id'] == csr['id']
        assert data['subject'] == 'CN=ext-subject.example.com'
        assert data['has_private_key'] is True

    def test_unrelated_key_creates_a_new_record(self, auth_client, external_ca):
        ca_key, ca_cert = external_ca
        csr = _create_csr(auth_client, 'ext-other-key.example.com')
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        leaf_pem = _sign_externally(ca_key, ca_cert, _csr_pem(auth_client, csr['id']),
                                    public_key=other.public_key())
        r = _import(auth_client, leaf_pem)
        assert r.status_code == 201, r.data
        data = _json(r)['data']
        assert data['id'] != csr['id']
        assert data['has_private_key'] is False
        assert csr['id'] in _pending_ids(auth_client)

    def test_bundle_key_attaches_to_keyless_uploaded_csr(self, auth_client, external_ca):
        """A CSR uploaded without its key, then imported with cert + key."""
        ca_key, ca_cert = external_ca
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        csr = (
            x509.CertificateSigningRequestBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'ext-uploaded.example.com')]))
            .sign(key, hashes.SHA256())
        )
        csr_pem = csr.public_bytes(serialization.Encoding.PEM)
        r = auth_client.post(f'{CSRS}/upload',
                             data=json.dumps({'pem': csr_pem.decode()}),
                             content_type='application/json')
        assert r.status_code in (200, 201), r.data
        csr_id = _json(r)['data']['id']
        assert _json(r)['data']['has_private_key'] is False

        leaf_pem = _sign_externally(ca_key, ca_cert, csr_pem)
        key_pem = key.private_bytes(serialization.Encoding.PEM,
                                    serialization.PrivateFormat.TraditionalOpenSSL,
                                    serialization.NoEncryption())
        r = _import(auth_client, leaf_pem + key_pem)
        assert r.status_code == 200, r.data
        assert _json(r)['data']['id'] == csr_id
        assert _json(r)['data']['has_private_key'] is True

    def test_smart_import_completes_pending_csr(self, auth_client, external_ca):
        ca_key, ca_cert = external_ca
        csr = _create_csr(auth_client, 'ext-smart.example.com')
        leaf_pem = _sign_externally(ca_key, ca_cert, _csr_pem(auth_client, csr['id']))

        r = auth_client.post('/api/v2/import/execute',
                             data=json.dumps({'content': leaf_pem.decode()}),
                             content_type='application/json')
        assert r.status_code == 200, r.data
        result = _json(r)['data']
        assert result['success'] is True, result
        assert result['certificates_imported'] == 1
        assert result['keys_matched'] == 1
        assert result['imported_ids']['certificates'] == [csr['id']]
        assert any('pending CSR' in w for w in result['warnings'])

        assert csr['id'] not in _pending_ids(auth_client)
        r = auth_client.get(f'{CERTS}/{csr["id"]}')
        assert r.status_code == 200
        data = _json(r)['data']
        assert data['has_private_key'] is True
        assert 'External Test Root' in data['issuer']

    def test_smart_import_unrelated_key_still_creates_record(self, auth_client, external_ca):
        ca_key, ca_cert = external_ca
        csr = _create_csr(auth_client, 'ext-smart-other.example.com')
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        leaf_pem = _sign_externally(ca_key, ca_cert, _csr_pem(auth_client, csr['id']),
                                    public_key=other.public_key())
        r = auth_client.post('/api/v2/import/execute',
                             data=json.dumps({'content': leaf_pem.decode()}),
                             content_type='application/json')
        assert r.status_code == 200, r.data
        result = _json(r)['data']
        assert result['certificates_imported'] == 1
        assert result['keys_matched'] == 0
        assert result['imported_ids']['certificates'] != [csr['id']]
        assert csr['id'] in _pending_ids(auth_client)
