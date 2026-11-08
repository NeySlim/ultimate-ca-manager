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
from tests.test_est_rfc7030 import _basic_auth, _post_csr, est_config  # noqa: F401
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
        'a\n.example', '_sip._tcp.example.com', '_acme-challenge.example.com',
        'xn--zz.example', 'xn--.example', '256.1.1.1', '0x.1.2.3', '*.10.0.0.1', 'host.123',
    ])
    def test_refused(self, value):
        assert validate_dns_san(value) is not None

    @pytest.mark.parametrize('value', [
        'www.example.com', '*.example.com', 'localhost',
        'xn--bcher-kva.example', 'XN--BCHER-KVA.example', 'A-1.Example.COM', '1a.example',
    ])
    def test_accepted(self, value):
        assert validate_dns_san(value) is None

    @pytest.mark.parametrize('value', ['a\n.example.com', '_sip._tcp.example.com',
                                       'my_host.example.com'])
    def test_acme_identifier_follows_the_same_rule(self, value):
        from services.acme.identifiers import is_valid_dns_identifier
        assert is_valid_dns_identifier(value) is False

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

    @pytest.mark.parametrize('cert_type', ['server', 'combined'])
    def test_form_refuses_an_underscore_host_cn(self, auth_client, create_ca, cert_type):
        """As Sign CSR does, rather than a TLS certificate without a name."""
        ca = create_ca(cn=f'Profile DNS form CN CA {cert_type}')
        r = auth_client.post(CERTS, json={'ca_id': ca['id'], 'cn': 'my_host.example.com',
                                          'cert_type': cert_type})
        assert r.status_code == 400, r.get_json()
        assert 'my_host.example.com' in r.get_json()['message']

    @pytest.mark.parametrize('extra', [{'san_dns': ['host.example.com']},
                                       {'san_ip': ['192.0.2.10']}, 'ip_template'])
    def test_form_issues_an_underscore_cn_that_names_nothing(
            self, app, auth_client, create_ca, extra):
        """As Sign CSR: a request with its own SAN, or a template without DNS, takes no name from the CN."""
        if extra == 'ip_template':
            from tests.test_template_san_types import _template
            extra = {'template_id': _template(app, ['ip'])}
        ca = create_ca(cn=f'Profile DNS form CN named CA {sorted(extra)[0]}')
        r = auth_client.post(CERTS, json={'ca_id': ca['id'], 'cn': 'my_host.example.com',
                                          'cert_type': 'server', **extra})
        assert r.status_code == 201, r.get_json()
        assert 'my_host.example.com' not in [
            n.value for n in _san(_cert(app, r.get_json()['data']['id']))
            if isinstance(n, x509.DNSName)]

    def test_form_client_with_an_underscore_cn_is_issued(self, auth_client, create_ca):
        ca = create_ca(cn='Profile DNS form CN client CA')
        r = auth_client.post(CERTS, json={'ca_id': ca['id'], 'cn': 'svc_backup.corp.example',
                                          'cert_type': 'client'})
        assert r.status_code == 201, r.get_json()

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

    @pytest.mark.parametrize('bad', ['evil\n.example.test', 'end.example.test\n', '10.0.0.1'])
    def test_sign_csr_refuses_what_the_form_refuses(self, auth_client, create_ca, bad):
        ca = create_ca(cn=f'Profile DNS trunk CA {len(bad)}')
        csr_id = _upload(auth_client, _csr(_cn('ok.example.test'), [
            x509.DNSName('ok.example.test'), x509.DNSName(bad)]))
        r = _sign(auth_client, csr_id, ca['id'])
        assert r.status_code == 400, r.get_json()

    def test_bulk_sign_gives_the_reason(self, auth_client, create_ca):
        ca = create_ca(cn='Profile DNS bulk CA')
        csr_id = _upload(auth_client, _csr(_cn('ok.example.test'), [
            x509.DNSName('bad name.example')]))
        r = auth_client.post(f'{CSRS}/bulk/sign', json={
            'ids': [csr_id], 'ca_id': ca['id'], 'validity_days': 30})
        assert r.status_code == 200, r.get_json()
        failed = r.get_json()['data']['failed']
        assert failed and 'bad name.example' in failed[0]['error'], failed


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

    @pytest.mark.parametrize('cn', ['intranet', 'localhost', 'fgt-01'])
    def test_a_single_label_cn_gives_its_dns_name(self, app, auth_client, create_ca, cn):
        """RFC 5280 §4.2.1.6 allows a one-label dNSName; the form's dot rule is its own."""
        ca = create_ca(cn=f'Profile CN label CA {cn}')
        csr_id = _upload(auth_client, _csr(_cn(cn)))
        assert _sign(auth_client, csr_id, ca['id']).status_code == 200
        assert _san(_cert(app, csr_id)) == [x509.DNSName(cn)]

    def test_an_underscore_hostname_cn_is_refused(self, auth_client, create_ca):
        ca = create_ca(cn='Profile CN underscore CA')
        csr_id = _upload(auth_client, _csr(_cn('my_host.example.com')))
        r = _sign(auth_client, csr_id, ca['id'])
        assert r.status_code == 400, r.get_json()
        assert 'my_host.example.com' in r.get_json()['message']

    @pytest.mark.parametrize('cn', ['fgt_01', '12345678'])
    def test_a_name_like_cn_without_dns_name_says_so(self, app, auth_client, create_ca, cn):
        ca = create_ca(cn=f'Profile CN notice CA {cn}')
        csr_id = _upload(auth_client, _csr(_cn(cn)))
        r = _sign(auth_client, csr_id, ca['id'])
        assert r.status_code == 200, r.get_json()
        assert not _san(_cert(app, csr_id))
        notices = (r.get_json().get('meta') or {}).get('notices') or []
        assert any(cn in n and 'DNS' in n for n in notices), notices

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

    def test_a_one_label_person_cn_adds_no_dns_name_under_constraints(
            self, app, auth_client, create_ca):
        """#389: an S/MIME request CN=jdoe signed with its address gets no DNS:jdoe."""
        ca = create_ca(cn='Profile CN smime NC CA', nameConstraintsPermitted=[
            {'type': 'dns', 'value': 'example.com'}, {'type': 'email', 'value': 'example.com'}])
        csr_id = _upload(auth_client, _csr(_cn('jdoe')))
        r = _sign(auth_client, csr_id, ca['id'], cert_type='email', san_email=['jdoe@example.com'])
        assert r.status_code == 200, r.get_json()
        assert _san(_cert(app, csr_id)) == [x509.RFC822Name('jdoe@example.com')]

    def test_a_dotted_person_cn_adds_no_dns_name_to_an_smime_certificate(
            self, app, auth_client, create_ca):
        """An S/MIME CN names a person: john.doe is no host, even under constraints."""
        ca = create_ca(cn='Profile CN smime dotted NC CA', nameConstraintsPermitted=[
            {'type': 'dns', 'value': 'example.com'}, {'type': 'email', 'value': 'example.com'}])
        csr_id = _upload(auth_client, _csr(_cn('john.doe')))
        r = _sign(auth_client, csr_id, ca['id'], cert_type='email',
                  san_email=['john.doe@example.com'])
        assert r.status_code == 200, r.get_json()
        assert _san(_cert(app, csr_id)) == [x509.RFC822Name('john.doe@example.com')]

    def test_the_form_and_its_approval_issue_a_dotted_person_cn(
            self, app, auth_client, create_ca, create_user):
        from tests.test_approval_on_sign_and_renew import _drop_policy, _json, _operator, _policy
        ca = create_ca(cn='Profile CN smime form NC CA', nameConstraintsPermitted=[
            {'type': 'dns', 'value': 'example.com'}, {'type': 'email', 'value': 'example.com'}])
        body = {'ca_id': ca['id'], 'cn': 'john.doe', 'cert_type': 'email',
                'san_email': ['john.doe@example.com']}
        r = auth_client.post(CERTS, json=body)
        assert r.status_code == 201, r.get_json()
        assert _san(_cert(app, r.get_json()['data']['id'])) == [
            x509.RFC822Name('john.doe@example.com')]
        pid = _policy(app, ca['id'], 'profile-smime-dotted')
        try:
            r = _operator(app, create_user).post(CERTS, json=body)
            approval_id = r.get_json()['data']['approval_id']
            r = _json(auth_client, 'post', f'/api/v2/approvals/{approval_id}/approve',
                      {'comment': 'ok'})
            assert r.get_json()['data']['certificate_issued'] is True, r.get_json()
        finally:
            _drop_policy(app, pid)

    @pytest.mark.parametrize('cert_type,cn', [
        ('client', 'jdoe'), ('email', 'jdoe'), ('code_signing', 'jdoe'),
        ('client', 'svc_backup.corp.example'), ('code_signing', 'svc_backup.corp.example'),
        ('client', 'fgt_01'),
    ])
    def test_a_non_host_cn_gives_no_dns_name_and_no_refusal(
            self, app, auth_client, create_ca, cert_type, cn):
        ca = create_ca(cn=f'Profile CN non host CA {cert_type} {len(cn)}')
        csr_id = _upload(auth_client, _csr(_cn(cn)))
        r = _sign(auth_client, csr_id, ca['id'], cert_type=cert_type)
        assert r.status_code == 200, r.get_json()
        assert not [n for n in _san(_cert(app, csr_id)) if isinstance(n, x509.DNSName)]
        assert not (r.get_json().get('meta') or {}).get('notices'), r.get_json()

    def test_a_non_host_dotted_cn_keeps_its_dns_name(self, app, auth_client, create_ca):
        ca = create_ca(cn='Profile CN client host CA')
        csr_id = _upload(auth_client, _csr(_cn('laptop.corp.example')))
        assert _sign(auth_client, csr_id, ca['id'], cert_type='client').status_code == 200
        assert _san(_cert(app, csr_id)) == [x509.DNSName('laptop.corp.example')]

    def test_est_device_one_label_cn_keeps_its_dns_name(self, app):
        """EST and FortiGate enrol device_cert with CN=intranet."""
        from utils.request_names import cn_implied_names
        assert cn_implied_names(x509.Name(_cn('intranet')), 'device_cert') == [
            x509.DNSName('intranet')]

    def test_a_name_the_template_drops_is_not_refused(self, app, auth_client, create_ca):
        """The syntax check judges the names that land, after the template's SAN types."""
        from tests.test_template_san_types import _template
        tpl_id = _template(app, ['ip'])
        ca = create_ca(cn='Profile CN template CA')
        csr_id = _upload(auth_client, _csr(_cn('my_host.example.com')))
        r = _sign(auth_client, csr_id, ca['id'], template_id=tpl_id)
        assert r.status_code == 200, r.get_json()
        assert not [n for n in _san(_cert(app, csr_id)) if isinstance(n, x509.DNSName)]

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
        long_cn = 'long-' + 'y' * 80 + '.example.com'
        csr_id = _upload(auth_client, _csr(
            [x509.NameAttribute(NameOID.COMMON_NAME, long_cn, _validate=False)]))
        r = _sign(auth_client, csr_id, ca['id'])
        assert r.status_code == 400, r.get_json()
        assert '64' in r.get_json()['message']

    @pytest.mark.parametrize('country,asn1', [
        ('FR\n', x509.name._ASN1Type.UTF8String), ('FR', x509.name._ASN1Type.UTF8String)])
    def test_country_is_exactly_two_printable_letters(self, auth_client, create_ca, country, asn1):
        """X520countryName is PrintableString SIZE(2) (RFC 5280 annex A)."""
        ca = create_ca(cn=f'Profile bounds C CA {asn1.name} {len(country)}')
        attrs = _cn('c.example.test') + [
            x509.NameAttribute(NameOID.COUNTRY_NAME, country, _type=asn1, _validate=False)]
        r = _sign(auth_client, _upload(auth_client, _csr(attrs)), ca['id'])
        assert r.status_code == 400, r.get_json()
        assert 'C ' in r.get_json()['message']

    def test_country_with_a_final_newline_is_refused_whatever_its_type(self):
        from utils.request_names import subject_bounds_error
        name = x509.Name([x509.NameAttribute(NameOID.COUNTRY_NAME, 'FR\n', _validate=False)])
        assert 'two-letter' in (subject_bounds_error(name) or '')

    def test_three_letter_country_is_refused(self, auth_client, create_ca):
        ca = create_ca(cn='Profile bounds C CA')
        attrs = _cn('c.example.test') + [
            x509.NameAttribute(NameOID.COUNTRY_NAME, 'FRA', _validate=False)]
        csr_id = _upload(auth_client, _csr(attrs))
        r = _sign(auth_client, csr_id, ca['id'])
        assert r.status_code == 400, r.get_json()
        assert 'C' in r.get_json()['message']

    @pytest.mark.parametrize('oid,bound', [
        (NameOID.ORGANIZATION_NAME, 64), (NameOID.ORGANIZATIONAL_UNIT_NAME, 64),
        (NameOID.LOCALITY_NAME, 128), (NameOID.STATE_OR_PROVINCE_NAME, 128),
        (NameOID.SERIAL_NUMBER, 64), (NameOID.EMAIL_ADDRESS, 255),
    ])
    def test_each_bound_is_enforced(self, auth_client, create_ca, oid, bound):
        ca = create_ca(cn=f'Profile bounds {oid._name} CA')
        # Not one repeated letter, which the CSR list's bounded search tests look for
        size = bound - len('@example.test') if oid == NameOID.EMAIL_ADDRESS else bound
        filler = ('bound-' * bound)[:size]
        ok = filler + '@example.test' if oid == NameOID.EMAIL_ADDRESS else filler
        attrs = _cn('b.example.test') + [x509.NameAttribute(oid, ok, _validate=False)]
        assert _sign(auth_client, _upload(auth_client, _csr(attrs)), ca['id']).status_code == 200
        over = 'y' + ok
        attrs = _cn('b.example.test') + [x509.NameAttribute(oid, over, _validate=False)]
        r = _sign(auth_client, _upload(auth_client, _csr(attrs)), ca['id'])
        assert r.status_code == 400, r.get_json()
        assert str(bound) in r.get_json()['message']

    def test_an_override_subject_is_the_caller_s(self, app):
        """WSTEP builds the subject from the directory: the trunk does not re-check it."""
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name(_cn('Profile override CA'))
        now = datetime.now(timezone.utc)
        ca_cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                   .public_key(key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now - timedelta(days=1))
                   .not_valid_after(now + timedelta(days=365))
                   .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
                   .sign(key, hashes.SHA256()))
        directory = x509.Name([x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, 'dir-' * 18,
                                                  _validate=False)] + _cn('ad.example.test'))
        with app.app_context():
            pem = TrustStoreService.sign_csr(
                csr_pem=_csr(_cn('ad.example.test')).public_bytes(serialization.Encoding.PEM),
                ca_cert=ca_cert, ca_private_key=key, validity_days=30, cert_type='server_cert',
                override_subject=directory)
        assert x509.load_pem_x509_certificate(pem).subject == directory

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

    @pytest.mark.parametrize('email', ['not-an-email', 'jöe@exämple.com'])
    def test_an_address_off_the_syntax_is_not_added(self, app, auth_client, create_ca, email):
        """Only a valid ASCII address is an rfc822Name (RFC 5280 §4.2.1.6, RFC 8398)."""
        ca = create_ca(cn=f'Profile email bad CA {len(email)}')
        attrs = _cn('bad-mail.example.test') + [
            x509.NameAttribute(NameOID.EMAIL_ADDRESS, email, _type=x509.name._ASN1Type.UTF8String)]
        for sans in ([x509.DNSName('bad-mail.example.test')], ()):
            csr_id = _upload(auth_client, _csr(attrs, sans))
            r = _sign(auth_client, csr_id, ca['id'])
            assert r.status_code == 200, r.get_json()
            assert _san(_cert(app, csr_id)) == [x509.DNSName('bad-mail.example.test')]

    def test_sign_csr_server_cn_address_is_not_an_email_name(self, app, auth_client, create_ca):
        """Only the emailAddress attribute implies an rfc822Name (RFC 5280 §4.1.2.6)."""
        ca = create_ca(cn='Profile email CN CA')
        csr_id = _upload(auth_client, _csr(_cn('ops@example.test'),
                                           [x509.DNSName('srv.example.test')]))
        assert _sign(auth_client, csr_id, ca['id']).status_code == 200
        assert _san(_cert(app, csr_id)) == [x509.DNSName('srv.example.test')]


class TestDefaultKeyUsage:
    @pytest.mark.parametrize('cert_type', ['client', 'code_signing', 'email'])
    def test_request_without_key_usage_gets_the_type_s(self, app, auth_client, create_ca, cert_type):
        ca = create_ca(cn=f'Profile KU {cert_type} CA')
        csr_id = _upload(auth_client, _csr(_cn(f"ku-{cert_type.replace('_', '-')}.example.test")))
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


class TestScepReplies:
    """The device is told why, and a malformed request is not queued."""

    def _reply(self, app, create_ca, sans, auto_approve=True, **ca_kwargs):
        import uuid
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import AttributeOID
        from models import SCEPRequest
        from services.scep.crypto_helpers import create_signed_pkcs7, encrypt_for_client
        from services.scep.scep_service import SCEPService
        from tests.test_scep_fail_info import FAIL_INFO_TEXT_OID
        from tests.test_scep_rfc8894_operations import (
            MESSAGE_TYPE_OID, PKI_STATUS_OID, SENDER_NONCE_OID, TRANSACTION_ID_OID,
            _client_identity, _load_ca_material, _response_attributes)
        import asn1crypto.core
        ca_data = create_ca(cn=f'Profile SCEP reply CA {uuid.uuid4().hex[:8]}', **ca_kwargs)
        txn = uuid.uuid4().hex
        with app.app_context():
            ca, ca_cert = _load_ca_material(ca_data['id'])[:2]
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            signer, _ = _client_identity('scep-reply.example.test', key=key)
            csr = (x509.CertificateSigningRequestBuilder()
                   .subject_name(x509.Name(_cn('scep-reply.example.test')))
                   .add_extension(x509.SubjectAlternativeName(sans), critical=False)
                   .add_attribute(AttributeOID.CHALLENGE_PASSWORD, b'sekret')
                   .sign(key, hashes.SHA256()))
            envelope = encrypt_for_client(csr.public_bytes(serialization.Encoding.DER), ca_cert)
            message = create_signed_pkcs7(envelope, key, signer, signed_attributes=[
                {'type': TRANSACTION_ID_OID, 'values': [asn1crypto.core.PrintableString(txn)]},
                {'type': MESSAGE_TYPE_OID, 'values': [asn1crypto.core.PrintableString('19')]},
                {'type': SENDER_NONCE_OID, 'values': [asn1crypto.core.OctetString(b'profile-nonce-16')]},
            ])
            response, _ = SCEPService(ca.refid, challenge_password='sekret',
                                      auto_approve=auto_approve).process_pkcs_req(message, '127.0.0.1')
            attrs = _response_attributes(response)
            queued = SCEPRequest.query.filter_by(transaction_id=txn).count()
        return attrs[PKI_STATUS_OID], attrs.get(FAIL_INFO_TEXT_OID), queued

    def test_a_malformed_name_is_refused_with_its_reason(self, app, create_ca):
        status, text, _ = self._reply(app, create_ca, [x509.DNSName('bad name.example')])
        assert status == '2' and 'bad name.example' in (text or ''), text

    def test_a_malformed_request_is_not_queued_for_approval(self, app, create_ca):
        status, text, queued = self._reply(
            app, create_ca, [x509.DNSName('bad name.example')], auto_approve=False)
        assert status == '2' and 'bad name.example' in (text or ''), text
        assert queued == 0

    def test_a_refusal_at_issuance_gives_its_reason(self, app, create_ca):
        """A name outside the CA's constraints is refused while issuing, not before."""
        status, text, _ = self._reply(
            app, create_ca, [x509.DNSName('other.test')],
            nameConstraintsPermitted=[{'type': 'dns', 'value': 'example.test'}])
        assert status == '2' and 'NameConstraints' in (text or ''), text


class TestEstPath:
    def test_refusal_names_its_reason(self, client, est_config):
        csr = _csr(_cn('est.example.test'), [x509.DNSName('bad name.example')])
        r = _post_csr(client, 'simpleenroll', csr, headers=_basic_auth())
        assert r.status_code == 400
        assert b'bad name.example' in r.data


    def test_serverkeygen_refusal_names_its_reason(self, client, est_config):
        csr = _csr(_cn('keygen.example.test'), [x509.DNSName('bad name.example')])
        r = _post_csr(client, 'serverkeygen', csr, headers=_basic_auth())
        assert r.status_code == 400
        assert b'bad name.example' in r.data

    def test_simplereenroll_refusal_names_its_reason(self, client, est_config):
        """A key under the floor is refused with its reason, by the EST check or else the trunk."""
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives.serialization import pkcs7
        from tests.test_est_rfc7030 import _make_csr
        first, _key = _make_csr(san_names=('reenroll.example.test',))
        enrolled = _post_csr(client, 'simpleenroll', first, headers=_basic_auth())
        assert enrolled.status_code == 200, enrolled.data
        leaf = [c for c in pkcs7.load_der_pkcs7_certificates(base64.b64decode(enrolled.data))
                if not c.extensions.get_extension_for_class(x509.BasicConstraints).value.ca][0]
        weak = rsa.generate_private_key(public_exponent=65537, key_size=1024)
        csr = (x509.CertificateSigningRequestBuilder().subject_name(leaf.subject)
               .add_extension(leaf.extensions.get_extension_for_class(
                   x509.SubjectAlternativeName).value, critical=False)
               .sign(weak, hashes.SHA256()))
        r = _post_csr(client, 'simplereenroll', csr,
                      client_cert_pem=leaf.public_bytes(serialization.Encoding.PEM).decode())
        assert r.status_code == 400, r.data
        assert b'RSA key too small (1024 bits)' in r.data, r.data


class TestApprovalAfterTheChecks:
    def test_a_malformed_request_is_refused_before_it_is_queued(
            self, app, auth_client, create_ca, create_user):
        """Nothing for an approver to vote on: the signing would refuse it."""
        from models.policy import ApprovalRequest
        from tests.test_approval_on_sign_and_renew import _drop_policy, _operator, _policy
        ca = create_ca(cn='Profile approval CA')
        pid = _policy(app, ca['id'], 'profile-malformed')
        try:
            csr_id = _upload(auth_client, _csr(_cn('ok.example.test'), [
                x509.DNSName('bad name.example')]))
            operator = _operator(app, create_user)
            r = _sign(operator, csr_id, ca['id'])
            assert r.status_code == 400, r.get_json()
            assert 'bad name.example' in r.get_json()['message']
            r = operator.post(f'{CSRS}/bulk/sign', json={
                'ids': [csr_id], 'ca_id': ca['id'], 'validity_days': 30})
            assert r.status_code == 200, r.get_json()
            assert not r.get_json()['data'].get('pending_approval'), r.get_json()
            assert 'bad name.example' in r.get_json()['data']['failed'][0]['error']
            with app.app_context():
                assert ApprovalRequest.query.filter_by(policy_id=pid).count() == 0
        finally:
            _drop_policy(app, pid)
