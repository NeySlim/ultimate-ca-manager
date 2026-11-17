"""#389: names added when signing a request, and a signed request put back
in the pending list to be signed again."""
import base64
import ipaddress
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from models import Certificate, db
from services.trust_store.trust_store_service import TrustStoreService

CSRS = '/api/v2/csrs'


def _csr(cn, sans=()):
    key = ec.generate_private_key(ec.SECP256R1())
    builder = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
    if sans:
        builder = builder.add_extension(x509.SubjectAlternativeName(list(sans)), critical=False)
    return builder.sign(key, hashes.SHA256())


def _upload(auth_client, csr):
    pem = csr.public_bytes(serialization.Encoding.PEM).decode()
    r = auth_client.post(f'{CSRS}/upload', json={'pem': pem})
    assert r.status_code in (200, 201), r.get_json()
    return r.get_json()['data']['id']


def _sign(auth_client, csr_id, ca_id, **body):
    return auth_client.post(f'{CSRS}/{csr_id}/sign',
                            json={'ca_id': ca_id, 'validity_days': 30, **body})


def _sans(app, cert_id):
    with app.app_context():
        row = db.session.get(Certificate, cert_id)
        cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
    return list(cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value)


class TestNamesAddedWhenSigning:
    def test_an_email_added_to_a_request_naming_nothing(self, app, auth_client, create_ca):
        """A smart-card request carries only a CN: the email added replaces
        the DNS name otherwise guessed from it."""
        ca = create_ca(cn='Extra names CA')
        csr_id = _upload(auth_client, _csr('Jane Doe'))
        r = _sign(auth_client, csr_id, ca['id'], cert_type='email', san_email=['jane@example.com'])
        assert r.status_code == 200, r.get_json()
        assert _sans(app, csr_id) == [x509.RFC822Name('jane@example.com')]
        with app.app_context():
            assert json.loads(db.session.get(Certificate, csr_id).san_email) == ['jane@example.com']

    def test_names_join_the_request_s_own(self, app, auth_client, create_ca):
        ca = create_ca(cn='Extra names join CA')
        csr_id = _upload(auth_client, _csr('a.example.test', [x509.DNSName('a.example.test')]))
        r = _sign(auth_client, csr_id, ca['id'], san_dns=['b.example.test', 'a.example.test'],
                  san_ip=['192.0.2.7'])
        assert r.status_code == 200, r.get_json()
        assert _sans(app, csr_id) == [
            x509.DNSName('a.example.test'), x509.DNSName('b.example.test'),
            x509.IPAddress(ipaddress.ip_address('192.0.2.7')),
        ]

    def test_without_added_names_nothing_changes(self, app, auth_client, create_ca):
        ca = create_ca(cn='Extra names none CA')
        csr_id = _upload(auth_client, _csr('host.example.test'))
        assert _sign(auth_client, csr_id, ca['id']).status_code == 200
        assert _sans(app, csr_id) == [x509.DNSName('host.example.test')]

    @pytest.mark.parametrize('body', [
        {'san_email': ['not-an-email']},
        {'san_ip': ['999.1.1.1']},
        {'san_upn': ['user@example.com']},
        {'san_dns': {'a': 1}},
    ])
    def test_invalid_names_are_refused(self, auth_client, create_ca, body):
        ca = create_ca(cn='Extra names invalid CA')
        csr_id = _upload(auth_client, _csr('invalid.example.test'))
        assert _sign(auth_client, csr_id, ca['id'], **body).status_code == 400

    def test_no_names_on_a_ca_certificate(self, auth_client, create_ca):
        ca = create_ca(cn='Extra names subca CA')
        csr_id = _upload(auth_client, _csr('Sub CA'))
        r = _sign(auth_client, csr_id, ca['id'], cert_type='intermediate_ca', san_dns=['x.example.test'])
        assert r.status_code == 400


def test_added_names_are_held_to_the_name_constraints(app):
    """The constraint check sees the names added, not only the request's."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Constrained CA')])
    now = datetime.now(timezone.utc)
    ca_cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
               .public_key(key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=365))
               .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
               .add_extension(x509.NameConstraints(
                   permitted_subtrees=[x509.DNSName('example.test')], excluded_subtrees=None),
                   critical=True)
               .sign(key, hashes.SHA256()))
    csr = _csr('in.example.test', [x509.DNSName('in.example.test')])
    with app.app_context():
        with pytest.raises(ValueError):
            TrustStoreService.sign_csr(
                csr_pem=csr.public_bytes(serialization.Encoding.PEM), ca_cert=ca_cert,
                ca_private_key=key, validity_days=30, extra_san=[x509.DNSName('out.example.org')])


class TestSignAgain:
    def _signed(self, auth_client, create_ca, cn):
        ca = create_ca(cn=f'Sign again {cn} CA')
        csr_id = _upload(auth_client, _csr(cn))
        assert _sign(auth_client, csr_id, ca['id']).status_code == 200
        return csr_id

    def test_puts_the_request_back_and_keeps_the_certificate(self, app, auth_client, create_ca):
        signed_id = self._signed(auth_client, create_ca, 'again.example.test')
        r = auth_client.post(f'{CSRS}/{signed_id}/resubmit')
        assert r.status_code == 201, r.get_json()
        new_id = r.get_json()['data']['id']
        assert new_id != signed_id
        with app.app_context():
            signed, pending = db.session.get(Certificate, signed_id), db.session.get(Certificate, new_id)
            assert pending.csr == signed.csr and pending.crt is None and signed.crt
        pending_ids = [c['id'] for c in auth_client.get(f'{CSRS}?per_page=500').get_json()['data']]
        assert new_id in pending_ids

    def test_a_second_call_returns_the_same_pending_row(self, auth_client, create_ca):
        signed_id = self._signed(auth_client, create_ca, 'again-twice.example.test')
        first = auth_client.post(f'{CSRS}/{signed_id}/resubmit').get_json()['data']['id']
        r = auth_client.post(f'{CSRS}/{signed_id}/resubmit')
        assert r.status_code == 200 and r.get_json()['data']['id'] == first

    def test_a_request_not_yet_signed_is_refused(self, auth_client):
        csr_id = _upload(auth_client, _csr('not-signed.example.test'))
        assert auth_client.post(f'{CSRS}/{csr_id}/resubmit').status_code == 404

    def test_requires_write_permission(self, viewer_client, auth_client, create_ca):
        signed_id = self._signed(auth_client, create_ca, 'again-viewer.example.test')
        assert viewer_client.post(f'{CSRS}/{signed_id}/resubmit').status_code == 403

    def test_the_copy_does_not_inherit_a_protocol_source(self, app, auth_client, create_ca):
        """Signed again by an operator: an 'acme' label would hide it from
        expiry alerts and renewals."""
        signed_id = self._signed(auth_client, create_ca, 'again-source.example.test')
        with app.app_context():
            db.session.get(Certificate, signed_id).source = 'acme'
            db.session.commit()
        new_id = auth_client.post(f'{CSRS}/{signed_id}/resubmit').get_json()['data']['id']
        with app.app_context():
            assert db.session.get(Certificate, new_id).source == 'upload'

    def test_importing_the_first_certificate_again_leaves_the_copy_pending(self, app, auth_client, create_ca):
        """The copy shares the key of the certificate already issued: that
        certificate must not complete it."""
        signed_id = self._signed(auth_client, create_ca, 'again-import.example.test')
        new_id = auth_client.post(f'{CSRS}/{signed_id}/resubmit').get_json()['data']['id']
        with app.app_context():
            pem = base64.b64decode(db.session.get(Certificate, signed_id).crt).decode()
        r = auth_client.post('/api/v2/certificates/import', data={'pem_content': pem},
                             content_type='multipart/form-data')
        assert r.status_code in (200, 201, 409), r.get_json()
        with app.app_context():
            assert db.session.get(Certificate, new_id).crt is None


def test_a_hostname_cn_keeps_its_name_when_an_ip_is_added(app, auth_client, create_ca):
    ca = create_ca(cn='Extra names hostname CA')
    csr_id = _upload(auth_client, _csr('host-ip.example.test'))
    assert _sign(auth_client, csr_id, ca['id'], san_ip=['192.0.2.9']).status_code == 200
    assert _sans(app, csr_id) == [
        x509.DNSName('host-ip.example.test'), x509.IPAddress(ipaddress.ip_address('192.0.2.9'))]
