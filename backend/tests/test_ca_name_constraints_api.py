"""#316: the Create CA API accepts NameConstraints and turns them into the
critical extension, and rejects inputs that would silently produce an
unconstrained CA.

No existing test drives NameConstraints through POST /api/v2/cas:
test_name_constraints_enforcement.py hand-builds the constrained CA cert with
x509.CertificateBuilder, which is exactly how the string-vs-dict API bug
survived.
"""
import ipaddress
import json

import pytest
from cryptography import x509
from cryptography.x509.oid import ExtensionOID

from tests.conftest import get_json


def _create_ca(auth_client, **overrides):
    payload = {
        'type': 'root',
        'commonName': 'NC API Root',
        'organization': 'Test Org',
        'country': 'US',
        'keyType': 'RSA',
        'keySize': 2048,
        'validityYears': 10,
        'hashAlgorithm': 'sha256',
    }
    payload.update(overrides)
    return auth_client.post(
        '/api/v2/cas', data=json.dumps(payload), content_type='application/json'
    )


class TestCreateCaAppliesNameConstraints:
    def test_permitted_and_excluded_land_in_the_critical_extension(self, auth_client):
        resp = _create_ca(
            auth_client,
            commonName='Constrained Org Root',
            nameConstraintsPermitted=[{'type': 'dns', 'value': 'example.com'}],
            nameConstraintsExcluded=[{'type': 'ip', 'value': '10.0.0.0/8'}],
        )
        assert resp.status_code in (200, 201), resp.data
        data = get_json(resp).get('data', get_json(resp))

        # Round-trips in the API view
        assert data['name_constraints_permitted'] == [
            {'type': 'dns', 'value': 'example.com'}
        ]
        assert data['name_constraints_excluded'] == [
            {'type': 'ip', 'value': '10.0.0.0/8'}
        ]

        cert = x509.load_pem_x509_certificate(data['pem'].encode())
        ext = cert.extensions.get_extension_for_oid(ExtensionOID.NAME_CONSTRAINTS)
        assert ext.critical is True
        assert list(ext.value.permitted_subtrees) == [x509.DNSName('example.com')]
        assert list(ext.value.excluded_subtrees) == [
            x509.IPAddress(ipaddress.ip_network('10.0.0.0/8'))
        ]

    def test_unconstrained_ca_has_no_name_constraints_extension(self, auth_client):
        resp = _create_ca(auth_client, commonName='Plain Root')
        data = get_json(resp).get('data', get_json(resp))
        cert = x509.load_pem_x509_certificate(data['pem'].encode())
        try:
            cert.extensions.get_extension_for_oid(ExtensionOID.NAME_CONSTRAINTS)
            raise AssertionError('unexpected NameConstraints on an unconstrained CA')
        except x509.ExtensionNotFound:
            pass

    def test_constrained_ca_rejects_a_violating_certificate(self, auth_client):
        resp = _create_ca(
            auth_client,
            commonName='Excluding Root',
            nameConstraintsExcluded=[{'type': 'dns', 'value': 'blocked.example'}],
        )
        ca = get_json(resp).get('data', get_json(resp))

        issued = auth_client.post(
            '/api/v2/certificates',
            data=json.dumps({
                'cn': 'ok.allowed.example',
                'ca_id': ca['id'],
                'validity_days': 30,
                'san_dns': ['host.blocked.example'],
            }),
            content_type='application/json',
        )
        assert issued.status_code == 400
        assert 'blocked.example' in get_json(issued).get('message', '')


class TestCreateCaRejectsBadNameConstraints:
    def test_plain_string_entries_are_rejected(self, auth_client):
        resp = _create_ca(
            auth_client, nameConstraintsPermitted=['example.com']
        )
        assert resp.status_code == 400
        assert 'nameConstraintsPermitted' in get_json(resp).get('message', '')

    def test_unknown_type_is_rejected(self, auth_client):
        resp = _create_ca(
            auth_client,
            nameConstraintsPermitted=[{'type': 'uri', 'value': 'https://example.com'}],
        )
        assert resp.status_code == 400
        assert 'dns, ip, email' in get_json(resp).get('message', '')

    def test_ip_network_with_host_bits_is_rejected_not_500(self, auth_client):
        resp = _create_ca(
            auth_client,
            nameConstraintsExcluded=[{'type': 'ip', 'value': '10.0.0.5/8'}],
        )
        assert resp.status_code == 400
        assert 'valid IP network' in get_json(resp).get('message', '')

    def test_empty_value_is_rejected(self, auth_client):
        resp = _create_ca(
            auth_client,
            nameConstraintsPermitted=[{'type': 'dns', 'value': '   '}],
        )
        assert resp.status_code == 400

    def test_name_constraints_rejected_for_external_csr_ca(self, auth_client):
        resp = _create_ca(
            auth_client,
            type='external',
            nameConstraintsPermitted=[{'type': 'dns', 'value': 'example.com'}],
        )
        assert resp.status_code == 400
        assert 'external' in get_json(resp).get('message', '').lower()

    def test_list_length_is_capped(self, auth_client):
        resp = _create_ca(
            auth_client,
            nameConstraintsPermitted=[
                {'type': 'dns', 'value': f'h{i}.example.com'} for i in range(33)
            ],
        )
        assert resp.status_code == 400
        assert 'at most' in get_json(resp).get('message', '')

    @pytest.mark.parametrize('bad', [
        'https://example.com', 'example.com/path', 'foo bar',
        'example..com', '-bad.example.com', 'exa_mple.com', '*.example.com',
        # RFC 5280 has no leading-dot form for dnsName (OpenSSL rejects it)
        '.example.com',
    ])
    def test_malformed_dns_value_is_rejected(self, auth_client, bad):
        resp = _create_ca(
            auth_client, nameConstraintsPermitted=[{'type': 'dns', 'value': bad}]
        )
        assert resp.status_code == 400, resp.data
        assert 'dns name constraint' in get_json(resp).get('message', '')

    @pytest.mark.parametrize('bad', [
        'not an email', 'https://x', '@example.com', 'a@b@c',
        # RFC 5322 dot-atom local part: no leading/trailing/doubled dot, atext only
        'a..b@example.com', '.a@example.com', 'a.@example.com', 'a:@example.com',
    ])
    def test_malformed_email_value_is_rejected(self, auth_client, bad):
        resp = _create_ca(
            auth_client, nameConstraintsExcluded=[{'type': 'email', 'value': bad}]
        )
        assert resp.status_code == 400, resp.data
        assert 'email name constraint' in get_json(resp).get('message', '')

    def test_non_ascii_value_is_rejected(self, auth_client):
        resp = _create_ca(
            auth_client,
            nameConstraintsPermitted=[{'type': 'dns', 'value': 'münchen.example'}],
        )
        assert resp.status_code == 400
        assert 'ASCII' in get_json(resp).get('message', '')


class TestCreateCaAcceptsValidNameConstraintForms:
    @pytest.mark.parametrize('ctype,value', [
        ('dns', 'example.com'),
        ('dns', 'sub.example.com'),
        ('email', 'user@example.com'),
        ('email', 'example.com'),
        ('email', '.example.com'),
    ])
    def test_accepted_forms_land_in_the_extension(self, auth_client, ctype, value):
        resp = _create_ca(
            auth_client,
            commonName=f'NC OK {ctype} {value}',
            nameConstraintsPermitted=[{'type': ctype, 'value': value}],
        )
        assert resp.status_code in (200, 201), resp.data
        data = get_json(resp).get('data', get_json(resp))
        assert data['name_constraints_permitted'] == [{'type': ctype, 'value': value}]
