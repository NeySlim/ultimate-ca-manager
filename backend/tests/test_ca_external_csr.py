"""
Tests for the external-CSR CA lifecycle (#298):
create pending CA -> download CSR -> install externally signed certificate
-> renew via CSR, plus the pending-state guards.
"""
import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtensionOID, NameOID

from tests.conftest import assert_error, assert_success, get_json

BASE = '/api/v2/cas'

_seq = [0]


def _next_cn(prefix='ExtCSR'):
    _seq[0] += 1
    return f'{prefix} {_seq[0]}'


def post_json(client, url, payload):
    return client.post(url, data=json.dumps(payload), content_type='application/json')


def _make_external_root(cn='Offline Test Root'):
    """Self-signed root built with cryptography only — simulates the offline CA."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048,
                                   backend=default_backend())
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, cn),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Offline Org'),
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
        .add_extension(x509.KeyUsage(
            digital_signature=False, content_commitment=False,
            key_encipherment=False, data_encipherment=False, key_agreement=False,
            key_cert_sign=True, crl_sign=True, encipher_only=False,
            decipher_only=False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
                       critical=False)
        .sign(key, hashes.SHA256(), default_backend())
    )
    return key, cert


def _sign_csr_as_external_root(csr_pem, root_key, root_cert, days=365,
                               pathlen=0, ca_true=True, ku_certsign=True,
                               with_ku=True, expired=False):
    """Reproduce what an offline root does with the CSR."""
    csr = x509.load_pem_x509_csr(
        csr_pem.encode() if isinstance(csr_pem, str) else csr_pem, default_backend()
    )
    now = datetime.now(timezone.utc)
    not_before = now - timedelta(days=730 if expired else 1)
    not_after = (now - timedelta(days=365)) if expired else (now + timedelta(days=days))
    builder = (
        x509.CertificateBuilder()
        .subject_name(csr.subject).issuer_name(root_cert.subject)
        .public_key(csr.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before).not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=ca_true, path_length=pathlen if ca_true else None),
                       critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(csr.public_key()),
                       critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()),
            critical=False)
    )
    if with_ku:
        builder = builder.add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False,
            key_encipherment=False, data_encipherment=False, key_agreement=False,
            key_cert_sign=ku_certsign, crl_sign=True, encipher_only=False,
            decipher_only=False), critical=True)
    cert = builder.sign(root_key, hashes.SHA256(), default_backend())
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def _create_external(auth_client, cn=None, **overrides):
    payload = {
        'type': 'external',
        'commonName': cn or _next_cn(),
        'organization': 'Ext Org',
        'country': 'US',
        'keyAlgo': 'RSA',
        'keySize': 2048,
    }
    payload.update(overrides)
    r = post_json(auth_client, BASE, payload)
    return assert_success(r, status=201)


def _import_root_cert_only(auth_client, root_cert, name='Offline Root Import'):
    pem = root_cert.public_bytes(serialization.Encoding.PEM).decode()
    r = auth_client.post(f'{BASE}/import', data={
        'pem_content': pem, 'name': name, 'import_key': 'false',
    })
    assert r.status_code in (200, 201), r.data[:400]
    return get_json(r).get('data', {})


class TestCreateExternalCA:
    def test_create_pending(self, auth_client):
        data = _create_external(auth_client)
        assert data['pending'] is True
        assert data['has_csr'] is True
        assert data['status'] == 'Pending'
        assert data['type'] == 'intermediate'
        assert data['is_root'] is False
        assert data['has_private_key'] is True
        assert data['valid_to'] is None
        assert data['csr_pem'] and 'BEGIN CERTIFICATE REQUEST' in data['csr_pem']
        assert data['key_type'] == 'RSA 2048'

    def test_csr_content(self, auth_client):
        data = _create_external(auth_client, pathLength=1)
        csr = x509.load_pem_x509_csr(data['csr_pem'].encode(), default_backend())
        bc = csr.extensions.get_extension_for_oid(ExtensionOID.BASIC_CONSTRAINTS)
        assert bc.critical and bc.value.ca and bc.value.path_length == 1
        ku = csr.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE)
        assert ku.critical and ku.value.key_cert_sign and ku.value.crl_sign
        with pytest.raises(x509.ExtensionNotFound):
            csr.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_KEY_IDENTIFIER)

    def test_ecdsa_key(self, auth_client):
        data = _create_external(auth_client, keyAlgo='ECDSA', keySize='secp384r1')
        assert data['key_type'] == 'EC secp384r1'

    def test_validity_and_parent_ignored(self, auth_client, create_ca):
        root = create_ca(cn=_next_cn('IgnoredParent'))
        data = _create_external(auth_client, validityYears=5, parentCAId=root['id'])
        assert data['pending'] is True
        assert data['parent_id'] is None

    def test_incomplete_hsm_params_rejected(self, auth_client):
        r = post_json(auth_client, BASE, {
            'type': 'external', 'commonName': _next_cn(),
            'hsmProviderId': 1,
        })
        assert_error(r, 400)


class TestDownloadCaCsr:
    def test_download(self, auth_client):
        data = _create_external(auth_client)
        r = auth_client.get(f"{BASE}/{data['id']}/csr")
        assert r.status_code == 200
        assert r.mimetype == 'application/x-pem-file'
        assert 'attachment' in r.headers.get('Content-Disposition', '')
        assert b'BEGIN CERTIFICATE REQUEST' in r.data

    def test_regular_ca_has_no_csr(self, auth_client, create_ca):
        root = create_ca(cn=_next_cn('NoCsr'))
        r = auth_client.get(f"{BASE}/{root['id']}/csr")
        assert_error(r, 404)

    def test_unauthenticated(self, client, auth_client):
        data = _create_external(auth_client)
        r = client.get(f"{BASE}/{data['id']}/csr")
        assert r.status_code in (401, 403)


class TestCompleteExternalCA:
    def test_nominal_with_imported_root(self, auth_client):
        root_key, root_cert = _make_external_root(cn=_next_cn('NomRoot'))
        imported = _import_root_cert_only(auth_client, root_cert,
                                          name=_next_cn('NomRootImport'))
        data = _create_external(auth_client)
        signed = _sign_csr_as_external_root(data['csr_pem'], root_key, root_cert)

        r = post_json(auth_client, f"{BASE}/{data['id']}/certificate",
                      {'pem_content': signed})
        out = assert_success(r)
        assert out['pending'] is False
        assert out['status'] == 'Active'
        assert out['has_csr'] is False
        assert out['caref'] == imported['refid']
        assert out['ski'] and out['ski'] == out['ski'].upper()
        assert out['path_length'] == 0
        # cert issuance must now work through the activated CA
        r2 = post_json(auth_client, '/api/v2/certificates', {
            'cn': _next_cn('leaf-ext') + '.example.com', 'ca_id': out['id'],
            'validity_days': 30,
        })
        assert r2.status_code in (200, 201), r2.data[:400]

    def test_without_root_warns_and_unchained(self, auth_client):
        root_key, root_cert = _make_external_root(cn=_next_cn('AbsentRoot'))
        data = _create_external(auth_client)
        signed = _sign_csr_as_external_root(data['csr_pem'], root_key, root_cert)
        r = post_json(auth_client, f"{BASE}/{data['id']}/certificate",
                      {'pem_content': signed})
        out = assert_success(r)
        assert out['pending'] is False
        assert out['caref'] is None
        assert any('Issuing CA not found' in w for w in out['warnings'])

    def test_wrong_key_rejected(self, auth_client):
        root_key, root_cert = _make_external_root(cn=_next_cn('WrongKeyRoot'))
        victim = _create_external(auth_client)
        other = _create_external(auth_client)
        signed_for_other = _sign_csr_as_external_root(
            other['csr_pem'], root_key, root_cert)
        r = post_json(auth_client, f"{BASE}/{victim['id']}/certificate",
                      {'pem_content': signed_for_other})
        assert_error(r, 400)
        assert b'does not match' in r.data

    def test_not_a_ca_cert_rejected(self, auth_client):
        root_key, root_cert = _make_external_root(cn=_next_cn('LeafRoot'))
        data = _create_external(auth_client)
        signed = _sign_csr_as_external_root(data['csr_pem'], root_key, root_cert,
                                            ca_true=False)
        r = post_json(auth_client, f"{BASE}/{data['id']}/certificate",
                      {'pem_content': signed})
        assert_error(r, 400)

    def test_ku_without_certsign_rejected(self, auth_client):
        root_key, root_cert = _make_external_root(cn=_next_cn('KuRoot'))
        data = _create_external(auth_client)
        signed = _sign_csr_as_external_root(data['csr_pem'], root_key, root_cert,
                                            ku_certsign=False)
        r = post_json(auth_client, f"{BASE}/{data['id']}/certificate",
                      {'pem_content': signed})
        assert_error(r, 400)

    def test_expired_rejected(self, auth_client):
        root_key, root_cert = _make_external_root(cn=_next_cn('ExpRoot'))
        data = _create_external(auth_client)
        signed = _sign_csr_as_external_root(data['csr_pem'], root_key, root_cert,
                                            expired=True)
        r = post_json(auth_client, f"{BASE}/{data['id']}/certificate",
                      {'pem_content': signed})
        assert_error(r, 400)

    def test_garbage_rejected(self, auth_client):
        data = _create_external(auth_client)
        r = post_json(auth_client, f"{BASE}/{data['id']}/certificate",
                      {'pem_content': 'not a certificate'})
        assert_error(r, 400)

    def test_der_multipart(self, auth_client):
        import io
        root_key, root_cert = _make_external_root(cn=_next_cn('DerRoot'))
        data = _create_external(auth_client)
        signed_pem = _sign_csr_as_external_root(data['csr_pem'], root_key, root_cert)
        der = x509.load_pem_x509_certificate(
            signed_pem.encode(), default_backend()
        ).public_bytes(serialization.Encoding.DER)
        r = auth_client.post(
            f"{BASE}/{data['id']}/certificate",
            data={'file': (io.BytesIO(der), 'signed.der')},
            content_type='multipart/form-data',
        )
        out = assert_success(r)
        assert out['pending'] is False


class TestRenewExternalCA:
    def test_renew_cycle(self, auth_client):
        root_key, root_cert = _make_external_root(cn=_next_cn('RenewRoot'))
        data = _create_external(auth_client)
        signed = _sign_csr_as_external_root(data['csr_pem'], root_key, root_cert,
                                            days=90)
        out = assert_success(post_json(
            auth_client, f"{BASE}/{data['id']}/certificate", {'pem_content': signed}))
        old_valid_to = out['valid_to']
        old_ski = out['ski']
        # First activation replaces nothing — no revoke-at-root reminder
        assert 'superseded_serial' not in out

        r = post_json(auth_client, f"{BASE}/{data['id']}/renew-csr", {})
        renewed = assert_success(r)
        assert renewed['has_csr'] is True
        assert renewed['pending'] is False
        csr = x509.load_pem_x509_csr(renewed['csr_pem'].encode(), default_backend())
        assert csr.subject.rfc4514_string() == out['subject']

        signed2 = _sign_csr_as_external_root(renewed['csr_pem'], root_key, root_cert,
                                             days=730)
        out2 = assert_success(post_json(
            auth_client, f"{BASE}/{data['id']}/certificate", {'pem_content': signed2}))
        assert out2['valid_to'] > old_valid_to
        assert out2['ski'] == old_ski
        assert out2['has_csr'] is False

        # Renewal surfaces the replaced certificate so the operator can
        # revoke it at the external root (#298)
        first_cert = x509.load_pem_x509_certificate(
            signed.encode(), default_backend())
        assert out2['superseded_serial'] == format(first_cert.serial_number, 'x')
        assert out2['superseded_valid_to'][:10] == old_valid_to[:10]

    def test_renew_offline_refused(self, auth_client):
        root_key, root_cert = _make_external_root(cn=_next_cn('OffRenewRoot'))
        data = _create_external(auth_client)
        signed = _sign_csr_as_external_root(data['csr_pem'], root_key, root_cert)
        assert_success(post_json(
            auth_client, f"{BASE}/{data['id']}/certificate", {'pem_content': signed}))
        r = auth_client.post(f"{BASE}/{data['id']}/offline",
                             data=json.dumps({'mode': 'password_protected',
                                              'password': 'Str0ngPass!x'}),
                             content_type='application/json')
        assert r.status_code in (200, 201), r.data[:400]
        r2 = post_json(auth_client, f"{BASE}/{data['id']}/renew-csr", {})
        assert_error(r2, 409)


class TestPendingGuards:
    def test_pending_cannot_be_parent(self, auth_client):
        data = _create_external(auth_client)
        r = post_json(auth_client, BASE, {
            'type': 'intermediate', 'commonName': _next_cn('ChildOfPending'),
            'parentCAId': data['id'], 'keyAlgo': 'RSA', 'keySize': 2048,
        })
        assert_error(r, 400)

    def test_pending_cannot_go_offline(self, auth_client):
        data = _create_external(auth_client)
        r = auth_client.post(f"{BASE}/{data['id']}/offline",
                             data=json.dumps({'mode': 'password_protected',
                                              'password': 'Str0ngPass!x'}),
                             content_type='application/json')
        assert r.status_code in (400, 409), r.data[:400]

    def test_pending_export_refused(self, auth_client):
        data = _create_external(auth_client)
        r = auth_client.get(f"{BASE}/{data['id']}/export?format=pem")
        assert r.status_code in (400, 404, 409), r.data[:400]

    def test_export_all_excludes_pending(self, auth_client, create_ca):
        # One CA with a certificate, so the export has something to return on any worker
        create_ca(cn=_next_cn('ExpAllIssued'))
        cn = _next_cn('ExpAllPending')
        _create_external(auth_client, cn)
        r = auth_client.get(f'{BASE}/export?format=pem')
        assert r.status_code == 200
        assert cn.encode() not in r.data

    def test_pending_issuance_refused(self, auth_client):
        data = _create_external(auth_client)
        r = post_json(auth_client, '/api/v2/certificates', {
            'cn': _next_cn('leaf-pending') + '.example.com', 'ca_id': data['id'],
            'validity_days': 30,
        })
        assert r.status_code in (400, 404), r.data[:400]

    def test_pending_crl_regen_is_clean_error(self, auth_client):
        data = _create_external(auth_client)
        r = auth_client.post(f"/api/v2/cas/{data['id']}/crl/generate",
                             data=json.dumps({}), content_type='application/json')
        # 4xx expected — never a 500 traceback
        assert 400 <= r.status_code < 500, r.data[:400]

    def test_delete_pending(self, auth_client):
        data = _create_external(auth_client)
        r = auth_client.delete(f"{BASE}/{data['id']}")
        assert r.status_code in (200, 204), r.data[:400]
