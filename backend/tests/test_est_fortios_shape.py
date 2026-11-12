"""EST from a FortiOS-shaped client (issues 405 to 407): requests of the shape
it sends, answers read by a strict decoder as limited as its own. Keys and
names are the test's."""
import base64
import json

import pytest
from asn1crypto import cms
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import AttributeOID, NameOID
from pyasn1.codec.der import decoder as der_decoder

from models import CA, db
from models.system_config import SystemConfig
from tests.test_est_rfc7030 import (  # noqa: F401  (est_config is the module fixture)
    EST_BASE, EST_PASSWORD, _set_config, est_config,
)

NAMES = ('fgt-test.example.test',)


@pytest.fixture(autouse=True)
def _est_on(app, est_config):  # noqa: F811
    with app.app_context():
        _set_config('est_enabled', 'true')
        _set_config('est_allow_empty_username', 'true')
    yield
    with app.app_context():
        row = SystemConfig.query.filter_by(key='est_allow_empty_username').first()
        if row:
            db.session.delete(row)
            db.session.commit()


@pytest.fixture
def labelled(app, create_ca, est_config):  # noqa: F811
    ca_data = create_ca(cn='EST FortiOS Labelled CA')
    with app.app_context():
        refid = db.session.get(CA, ca_data['id']).refid
        _set_config('est_labels', json.dumps({'branch': refid}))
    yield 'branch'
    with app.app_context():
        row = SystemConfig.query.filter_by(key='est_labels').first()
        if row:
            db.session.delete(row)
            db.session.commit()


def _strict_body(response):
    """What an OpenSSL base64 BIO accepts: short lines, nothing but base64."""
    lines = response.data.decode('ascii').split('\n')
    assert lines[-1] == '', 'the body ends with a line feed'
    lines = lines[:-1]
    assert len(lines) >= 1 and all(lines)
    assert all(len(line) <= 76 for line in lines), max(map(len, lines))
    return base64.b64decode(''.join(lines), validate=True)


def _strict_pkcs7_certs(response):
    der = _strict_body(response)
    info = cms.ContentInfo.load(der)
    assert info['content_type'].native == 'signed_data'
    assert info['content']['encap_content_info']['content'].native is None
    assert not info['content']['signer_infos'].native
    certs = pkcs7.load_der_pkcs7_certificates(der)
    assert certs
    return certs


def _folded_csr(csr, challenge=None):
    """Base64 folded at 64 characters, as a libest-based client sends it."""
    text = base64.b64encode(csr.public_bytes(serialization.Encoding.DER)).decode()
    return '\n'.join(text[i:i + 64] for i in range(0, len(text), 64)) + '\n'


def _csr(key, cn, names=NAMES, challenge=None):
    builder = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    ).add_extension(x509.SubjectAlternativeName([x509.DNSName(n) for n in names]), False)
    if challenge is not None:
        builder = builder.add_attribute(AttributeOID.CHALLENGE_PASSWORD, challenge)
    return builder.sign(key, hashes.SHA256())


def _empty_username_basic():
    token = base64.b64encode(f':{EST_PASSWORD}'.encode()).decode()
    return {'Authorization': f'Basic {token}'}


def _post(client, path, csr, headers=None, content_type=None, **kw):
    """content_type None sends no Content-Type header at all."""
    return client.post(f'{EST_BASE}/{path}', data=_folded_csr(csr).encode(),
                       headers=headers or {}, content_type=content_type, **kw)


@pytest.mark.parametrize('prefix', ['', 'branch/'], ids=['default', 'label'])
def test_fortios_enrol_then_reenrol_reads_back_strictly(client, labelled, caplog, prefix):
    cn = f'fgt-{prefix.strip("/") or "default"}.example.test'
    names = (cn,)
    for operation in ('cacerts', 'csrattrs'):
        r = client.get(f'{EST_BASE}/{prefix}{operation}')
        assert r.status_code == 200, r.data
        if operation == 'cacerts':
            _strict_pkcs7_certs(r)
        else:
            attrs, rest = der_decoder.decode(_strict_body(r))
            assert rest == b''
            assert str(AttributeOID.CHALLENGE_PASSWORD.dotted_string) not in [str(a) for a in attrs]

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    # No Content-Type at all, then application/pkcs10: both enrol
    caplog.set_level('WARNING')
    issued = None
    for content_type in (None, 'application/pkcs10'):
        r = _post(client, f'{prefix}simpleenroll', _csr(key, cn, names),
                  headers=_empty_username_basic(), content_type=content_type)
        assert r.status_code == 200, r.data
        certs = _strict_pkcs7_certs(r)
        assert len(certs) == 1
        issued = certs[0]
    assert "Content-Type is 'missing'" in caplog.text

    # The TLS worker hands the client certificate over as DER
    r = _post(client, f'{prefix}simplereenroll', _csr(key, cn, names),
              content_type='application/pkcs10',
              environ_overrides={'peercert': issued.public_bytes(serialization.Encoding.DER)})
    assert r.status_code == 200, r.data
    renewed = _strict_pkcs7_certs(r)
    assert len(renewed) == 1 and renewed[0].serial_number != issued.serial_number
    assert renewed[0].subject == issued.subject


def test_basic_auth_with_empty_username_is_refused_unless_the_profile_allows_it(app, client):
    with app.app_context():
        _set_config('est_allow_empty_username', 'false')
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    r = _post(client, 'simpleenroll', _csr(key, 'fgt-nouser.example.test', ('fgt-nouser.example.test',)),
              headers=_empty_username_basic(), content_type='application/pkcs10')
    assert r.status_code == 401


def test_challenge_password_without_a_tls_unique_is_refused_as_in_tls_1_3(client):
    """Freezes today's behaviour: a TLS 1.3 connection has no tls-unique (RFC 9266),
    so a CSR carrying the challengePassword gets a 400 naming TLS 1.3, not an enrolment."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = _csr(key, 'fgt-pop.example.test', ('fgt-pop.example.test',), challenge=b'Zm9yLXRlc3Q=')
    r = _post(client, 'simpleenroll', csr, headers=_empty_username_basic(),
              content_type='application/pkcs10')
    assert r.status_code == 400
    assert b'TLS 1.3' in r.data and b'without challengePassword' in r.data


def test_worker_gives_no_tls_unique_on_tls_1_3_so_the_challenge_is_refused(client):
    from workers import _tls_unique

    class _Tls13:
        def version(self):
            return 'TLSv1.3'

        def get_channel_binding(self, kind):
            raise AssertionError('not asked for on TLS 1.3')

    assert _tls_unique(_Tls13()) is None


def test_challenge_password_matching_the_tls_1_2_binding_is_accepted(client):
    binding = b'\x01' * 12
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = _csr(key, 'fgt-pop12.example.test', ('fgt-pop12.example.test',),
               challenge=base64.b64encode(binding))
    r = _post(client, 'simpleenroll', csr, headers=_empty_username_basic(),
              content_type='application/pkcs10', environ_overrides={'ucm.tls_unique': binding})
    assert r.status_code == 200, r.data
