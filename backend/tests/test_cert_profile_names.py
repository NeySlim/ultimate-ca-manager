"""Names and subject a certificate carries (RFC 5280 §4.1.2.6, §4.2.1.6,
annex A; RFC 9549): the same rules for the issue form, the API and Sign CSR."""
import base64
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtensionOID, NameOID

from models import Certificate, db
from services.trust_store.trust_store_service import TrustStoreService
from utils.san_parse import (auto_san_buckets_from_cn, parse_cert_san_payload,
                             parse_csr_san_entries, validate_dns_san)

CSRS = '/api/v2/csrs'
CERTS = '/api/v2/certificates'


def _csr(attrs, sans=(), key_usage=None):
    key = ec.generate_private_key(ec.SECP256R1())
    builder = x509.CertificateSigningRequestBuilder().subject_name(x509.Name(attrs))
    if sans:
        builder = builder.add_extension(x509.SubjectAlternativeName(list(sans)), critical=False)
    if key_usage is not None:
        builder = builder.add_extension(key_usage, critical=True)
    return builder.sign(key, hashes.SHA256())


def _cn(value):
    return [x509.NameAttribute(NameOID.COMMON_NAME, value)]


def _upload(auth_client, csr):
    pem = csr.public_bytes(serialization.Encoding.PEM).decode()
    r = auth_client.post(f'{CSRS}/upload', json={'pem': pem})
    assert r.status_code in (200, 201), r.get_json()
    return r.get_json()['data']['id']


def _sign(auth_client, csr_id, ca_id, **body):
    return auth_client.post(f'{CSRS}/{csr_id}/sign',
                            json={'ca_id': ca_id, 'validity_days': 30, **body})


def _cert(app, cert_id):
    with app.app_context():
        row = db.session.get(Certificate, cert_id)
        return x509.load_pem_x509_certificate(base64.b64decode(row.crt))


def _san(cert):
    try:
        return list(cert.extensions.get_extension_for_oid(
            ExtensionOID.SUBJECT_ALTERNATIVE_NAME).value)
    except x509.ExtensionNotFound:
        return []


class TestDnsNameSyntax:
    @pytest.mark.parametrize('value', [
        'foo bar.example', 'host.example.', 'a.*.example', '*', '*.', '-a.example',
        'a-.example', 'a..example', '.example', 'w*.example', ' ',
        ('a' * 64) + '.example', '.'.join(['abcdefghi'] * 26),
        'under_score.example', 'host_.example', '_-x.example', '_.example',
    ])
    def test_refused(self, value):
        assert validate_dns_san(value) is not None

    @pytest.mark.parametrize('value', [
        'www.example.com', '*.example.com', 'localhost',
        '_sip._tcp.example.com', '_acme-challenge.example.com', '_25._tcp.mx.example', 'xn--bcher-kva.example', 'A-1.Example.COM',
    ])
    def test_accepted(self, value):
        assert validate_dns_san(value) is None

    def test_u_label_becomes_an_a_label(self):
        buckets, err = parse_cert_san_payload({'san_dns': ['bücher.example', '*.bücher.example']})
        assert err is None
        assert buckets['san_dns'] == ['xn--bcher-kva.example', '*.xn--bcher-kva.example']
        buckets, err = parse_csr_san_entries(['DNS:bücher.example'])
        assert err is None and buckets['san_dns'] == ['xn--bcher-kva.example']

    def test_form_refuses_a_malformed_name(self, auth_client, create_ca):
        ca = create_ca(cn='Profile DNS form CA')
        for bad in ('foo bar.example', 'host.example.', 'a.*.example', '*'):
            r = auth_client.post(CERTS, json={'ca_id': ca['id'], 'cn': 'ok.example.test',
                                              'san_dns': [bad]})
            assert r.status_code == 400, (bad, r.get_json())
            assert bad.strip() in r.get_json()['message']

    def test_form_issues_an_idn_as_an_a_label(self, app, auth_client, create_ca):
        ca = create_ca(cn='Profile IDN form CA')
        r = auth_client.post(CERTS, json={'ca_id': ca['id'], 'cn': 'idn.example.test',
                                          'san_dns': ['bücher.example']})
        assert r.status_code == 201, r.get_json()
        names = [n.value for n in _san(_cert(app, r.get_json()['data']['id']))
                 if isinstance(n, x509.DNSName)]
        assert 'xn--bcher-kva.example' in names

    def test_csr_generation_refuses_a_malformed_name(self, auth_client):
        r = auth_client.post(CSRS, json={'cn': 'gen.example.test', 'key_type': 'EC-P256',
                                         'sans': ['DNS:host.example.']})
        assert r.status_code == 400, r.get_json()

    def test_sign_csr_refuses_a_malformed_name_from_the_request(self, auth_client, create_ca):
        ca = create_ca(cn='Profile DNS sign CA')
        csr_id = _upload(auth_client, _csr(_cn('ok.example.test'), [
            x509.DNSName('ok.example.test'), x509.DNSName('bad name.example')]))
        r = _sign(auth_client, csr_id, ca['id'])
        assert r.status_code == 400, r.get_json()
        assert 'bad name.example' in r.get_json()['message']


class TestNameImpliedByTheCn:
    @pytest.mark.parametrize('cert_type,cn', [
        ('client', 'John Doe'), ('email', 'Example, Inc.'),
        ('code_signing', 'noku_code'), ('server', 'café.example.com'),
    ])
    def test_a_cn_that_is_not_a_hostname_gives_no_dns_name(
            self, app, auth_client, create_ca, cert_type, cn):
        ca = create_ca(cn=f'Profile CN {cert_type} CA')
        csr_id = _upload(auth_client, _csr(_cn(cn)))
        r = _sign(auth_client, csr_id, ca['id'], cert_type=cert_type)
        assert r.status_code == 200, r.get_json()
        assert not [n for n in _san(_cert(app, csr_id)) if isinstance(n, x509.DNSName)]

    def test_a_hostname_cn_still_gives_its_dns_name(self, app, auth_client, create_ca):
        ca = create_ca(cn='Profile CN host CA')
        csr_id = _upload(auth_client, _csr(_cn('host.example.test')))
        assert _sign(auth_client, csr_id, ca['id']).status_code == 200
        assert _san(_cert(app, csr_id)) == [x509.DNSName('host.example.test')]

    def test_the_root_dot_of_a_cn_stays_out_of_the_dns_name(self, app, auth_client, create_ca):
        assert auto_san_buckets_from_cn('www.example.test.', 'server')['san_dns'] == ['www.example.test']
        ca = create_ca(cn='Profile CN root dot CA')
        csr_id = _upload(auth_client, _csr(_cn('dot.example.test.')))
        assert _sign(auth_client, csr_id, ca['id']).status_code == 200
        assert _san(_cert(app, csr_id)) == [x509.DNSName('dot.example.test')]

    def test_a_sub_ca_gets_no_name_from_its_cn(self, app, auth_client, create_ca):
        ca = create_ca(cn='Profile CN parent CA')
        csr_id = _upload(auth_client, _csr(_cn('sub.example.test')))
        r = _sign(auth_client, csr_id, ca['id'], cert_type='intermediate_ca')
        assert r.status_code == 200, r.get_json()
        from models import CA
        with app.app_context():
            sub = db.session.get(CA, r.get_json()['data']['id'])
            cert = x509.load_pem_x509_certificate(base64.b64decode(sub.crt))
        assert _san(cert) == []

    def test_est_device_request_gets_no_dns_name_from_a_person_cn(self, app):
        """The trunk EST signs through (cert_type device_cert)."""
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name(_cn('Profile trunk CA'))
        now = datetime.now(timezone.utc)
        ca_cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                   .public_key(key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now - timedelta(days=1))
                   .not_valid_after(now + timedelta(days=365))
                   .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                   .sign(key, hashes.SHA256()))
        with app.app_context():
            pem = TrustStoreService.sign_csr(
                csr_pem=_csr(_cn('Jane Roe')).public_bytes(serialization.Encoding.PEM),
                ca_cert=ca_cert, ca_private_key=key, validity_days=30, cert_type='device_cert')
        assert not [n for n in _san(x509.load_pem_x509_certificate(pem))
                    if isinstance(n, x509.DNSName)]


class TestSubjectBounds:
    def test_cn_over_64_characters_is_refused(self, auth_client, create_ca):
        ca = create_ca(cn='Profile bounds CN CA')
        long_cn = 'audit-' + 'y' * 80 + '.example.com'
        csr_id = _upload(auth_client, _csr(
            [x509.NameAttribute(NameOID.COMMON_NAME, long_cn, _validate=False)]))
        r = _sign(auth_client, csr_id, ca['id'])
        assert r.status_code == 400, r.get_json()
        assert '64' in r.get_json()['message']

    def test_three_letter_country_is_refused(self, auth_client, create_ca):
        ca = create_ca(cn='Profile bounds C CA')
        attrs = _cn('c.example.test') + [
            x509.NameAttribute(NameOID.COUNTRY_NAME, 'FRA', _validate=False)]
        csr_id = _upload(auth_client, _csr(attrs))
        r = _sign(auth_client, csr_id, ca['id'])
        assert r.status_code == 400, r.get_json()
        assert 'C' in r.get_json()['message']

    def test_empty_subject_takes_a_cn_that_fits(self, app, auth_client, create_ca):
        ca = create_ca(cn='Profile bounds empty CA')
        long_name = ('a' * 60) + '.example.test'
        csr_id = _upload(auth_client, _csr([], [x509.DNSName(long_name),
                                                x509.DNSName('short.example.test')]))
        r = _sign(auth_client, csr_id, ca['id'])
        assert r.status_code == 200, r.get_json()
        cert = _cert(app, csr_id)
        assert cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == 'short.example.test'


class TestExplicitRefusals:
    def test_sub_ca_under_path_length_zero(self, auth_client, create_ca):
        root = create_ca(cn='Profile pathlen root')
        sub = create_ca(cn='Profile pathlen 0 sub', type='intermediate',
                        parentCAId=root['id'], pathLength=0)
        csr_id = _upload(auth_client, _csr(_cn('Grandchild CA')))
        r = _sign(auth_client, csr_id, sub['id'], cert_type='intermediate_ca')
        assert r.status_code == 400, r.get_json()
        assert 'pathLenConstraint' in r.get_json()['message']

    def test_name_outside_the_ca_constraints(self, auth_client, create_ca):
        ca = create_ca(cn='Profile NC CA',
                       nameConstraintsPermitted=[{'type': 'dns', 'value': 'permitted.example'}])
        csr_id = _upload(auth_client, _csr(_cn('evil.other.example')))
        r = _sign(auth_client, csr_id, ca['id'])
        assert r.status_code == 400, r.get_json()
        assert 'NameConstraints' in r.get_json()['message']

    def test_dns_constraint_message_has_no_leading_dot_example(self, auth_client):
        r = auth_client.post('/api/v2/cas', json={
            'type': 'root', 'commonName': 'Profile NC dot CA', 'keyAlgo': 'RSA',
            'keySize': 2048, 'validityYears': 2,
            'nameConstraintsPermitted': [{'type': 'dns', 'value': '.example.com'}]})
        assert r.status_code == 400
        assert 'or .example.com' not in r.get_json()['message']


class TestSubjectEmailInTheSan:
    def test_form_server_certificate(self, app, auth_client, create_ca):
        ca = create_ca(cn='Profile email form CA')
        r = auth_client.post(CERTS, json={'ca_id': ca['id'], 'cn': 'mail.example.test',
                                          'cert_type': 'server', 'email': 'ops@example.test'})
        assert r.status_code == 201, r.get_json()
        assert x509.RFC822Name('ops@example.test') in _san(_cert(app, r.get_json()['data']['id']))

    def test_implicit_buckets_for_every_type(self):
        for cert_type in ('server', 'client', 'code_signing', 'email', 'combined'):
            got = auto_san_buckets_from_cn('x.example.test', cert_type, subject_email='a@example.test')
            assert got['san_email'] == ['a@example.test'], cert_type

    def test_sign_csr_with_its_own_san(self, app, auth_client, create_ca):
        ca = create_ca(cn='Profile email sign CA')
        attrs = _cn('box.example.test') + [
            x509.NameAttribute(NameOID.EMAIL_ADDRESS, 'box@example.test')]
        csr_id = _upload(auth_client, _csr(attrs, [x509.DNSName('box.example.test')]))
        assert _sign(auth_client, csr_id, ca['id']).status_code == 200
        assert _san(_cert(app, csr_id)) == [x509.DNSName('box.example.test'),
                                            x509.RFC822Name('box@example.test')]


class TestDefaultKeyUsage:
    @pytest.mark.parametrize('cert_type', ['client', 'code_signing', 'email'])
    def test_request_without_key_usage_gets_the_type_s(self, app, auth_client, create_ca, cert_type):
        ca = create_ca(cn=f'Profile KU {cert_type} CA')
        csr_id = _upload(auth_client, _csr(_cn(f'ku-{cert_type}.example.test')))
        assert _sign(auth_client, csr_id, ca['id'], cert_type=cert_type).status_code == 200
        ku = _cert(app, csr_id).extensions.get_extension_for_class(x509.KeyUsage)
        assert ku.critical and ku.value.digital_signature
        assert not ku.value.key_encipherment  # an EC key (RFC 5480 §3)


class TestRenewalAtPar:
    """A re-enrolment (EST simplereenroll, SCEP RenewalReq) keeps what the
    certificate it renews already carries."""

    def _ca(self):
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name(_cn('Profile renewal CA'))
        now = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=365))
                .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                .sign(key, hashes.SHA256()))
        return cert, key

    def _prior(self, ca_cert, ca_key, subject, sans):
        leaf = ec.generate_private_key(ec.SECP256R1())
        now = datetime.now(timezone.utc)
        return (x509.CertificateBuilder().subject_name(subject).issuer_name(ca_cert.subject)
                .public_key(leaf.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
                .add_extension(x509.SubjectAlternativeName(sans), critical=False)
                .sign(ca_key, hashes.SHA256()))

    def test_names_and_subject_already_issued_are_kept(self, app):
        ca_cert, ca_key = self._ca()
        subject = x509.Name([x509.NameAttribute(
            NameOID.COMMON_NAME, 'device-' + 'x' * 70, _validate=False)])
        sans = [x509.DNSName('old_host.example.'), x509.DNSName('new.example.test')]
        csr = x509.CertificateSigningRequestBuilder().subject_name(subject).add_extension(
            x509.SubjectAlternativeName(sans), critical=False).sign(
            ec.generate_private_key(ec.SECP256R1()), hashes.SHA256())
        pem = csr.public_bytes(serialization.Encoding.PEM)
        prior = self._prior(ca_cert, ca_key, subject, sans)
        with app.app_context():
            with pytest.raises(ValueError):
                TrustStoreService.sign_csr(csr_pem=pem, ca_cert=ca_cert, ca_private_key=ca_key,
                                           validity_days=30, cert_type='device_cert')
            out = TrustStoreService.sign_csr(csr_pem=pem, ca_cert=ca_cert, ca_private_key=ca_key,
                                             validity_days=30, cert_type='device_cert',
                                             renewal_of=prior)
        assert _san(x509.load_pem_x509_certificate(out)) == sans

    def test_a_new_malformed_name_is_still_refused(self, app):
        ca_cert, ca_key = self._ca()
        subject = x509.Name(_cn('dev.example.test'))
        prior = self._prior(ca_cert, ca_key, subject, [x509.DNSName('dev.example.test')])
        csr = x509.CertificateSigningRequestBuilder().subject_name(subject).add_extension(
            x509.SubjectAlternativeName([x509.DNSName('dev.example.test'),
                                         x509.DNSName('bad name.example')]),
            critical=False).sign(ec.generate_private_key(ec.SECP256R1()), hashes.SHA256())
        with app.app_context():
            with pytest.raises(ValueError, match='bad name.example'):
                TrustStoreService.sign_csr(
                    csr_pem=csr.public_bytes(serialization.Encoding.PEM), ca_cert=ca_cert,
                    ca_private_key=ca_key, validity_days=30, cert_type='device_cert',
                    renewal_of=prior)


class TestScepPath:
    """SCEP builds its certificate apart from the trunk: same refusals."""

    def _issue(self, app, create_ca, csr, txn):
        from models import CA, SCEPRequest
        from services.scep.scep_service import SCEPService
        ca = create_ca(cn=f'Profile SCEP CA {txn}')
        with app.app_context():
            ca_obj = db.session.get(CA, ca['id'])
            svc = SCEPService(ca_refid=ca_obj.refid, auto_approve=True)
            req = SCEPRequest(
                transaction_id=txn, ca_refid=ca_obj.refid, status='pending', subject='CN=x',
                csr=base64.b64encode(csr.public_bytes(serialization.Encoding.DER)).decode())
            db.session.add(req)
            db.session.flush()
            try:
                return svc._auto_approve_request(req, csr)
            finally:
                db.session.rollback()

    def test_malformed_dns_name_is_refused(self, app, create_ca):
        csr = _csr(_cn('scep.example.test'), [x509.DNSName('bad name.example')])
        with pytest.raises(ValueError, match='bad name.example'):
            self._issue(app, create_ca, csr, 'profile-scep-dns')

    def test_three_letter_country_is_refused(self, app, create_ca):
        csr = _csr(_cn('scep.example.test') + [
            x509.NameAttribute(NameOID.COUNTRY_NAME, 'FRA', _validate=False)])
        with pytest.raises(ValueError, match='two-letter'):
            self._issue(app, create_ca, csr, 'profile-scep-c')

    def test_a_valid_request_is_issued(self, app, create_ca):
        csr = _csr(_cn('scep.example.test'), [x509.DNSName('scep.example.test')])
        assert self._issue(app, create_ca, csr, 'profile-scep-ok')
