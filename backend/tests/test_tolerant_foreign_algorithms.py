"""Tolerant reading of certificates whose algorithms pyca cannot load.

SM2, GOST R 34.10-2012 and FRP256v1 certificates are shown by OID and known
name, never raise, and a chain through them is reported as not verifiable.
Nothing here issues anything.
"""
import base64
import datetime as dt
import json
import os
import shutil
import subprocess

import pytest
from asn1crypto import core
from asn1crypto import x509 as ax
from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization

SM2_OID = '1.2.156.10197.1.301'
SM2_SIG_OID = '1.2.156.10197.1.501'
GOST256_OID = '1.2.643.7.1.1.1.1'
GOST512_OID = '1.2.643.7.1.1.1.2'
GOST_SIG256_OID = '1.2.643.7.1.1.3.2'
FRP_OID = '1.2.250.1.223.101.256.1'
EC_PUBKEY_OID = '1.2.840.10045.2.1'
ECDSA_SHA256_OID = '1.2.840.10045.4.3.2'
UNNAMED_OID = '1.3.9999.1.2.3'


# ---------------------------------------------------------------- builders

def _seq(*items):
    return core.Sequence(contents=b''.join(i.dump() for i in items))


def _oid(value):
    return core.ObjectIdentifier(value)


def _alg(oid, params=None):
    return _seq(_oid(oid), params) if params is not None else _seq(_oid(oid))


def _spki(key_alg, key_bytes):
    return _seq(key_alg, core.OctetBitString(key_bytes))


KEYS = {
    'sm2': (_alg(EC_PUBKEY_OID, _oid(SM2_OID)), b'\x04' + b'\x11' * 64, _alg(SM2_SIG_OID)),
    'frp': (_alg(EC_PUBKEY_OID, _oid(FRP_OID)), b'\x04' + b'\x22' * 64, _alg(ECDSA_SHA256_OID)),
    'gost': (_alg(GOST256_OID, _seq(_oid('1.2.643.7.1.2.1.1.1'), _oid('1.2.643.7.1.1.2.2'))),
             b'\x33' * 64, _alg(GOST_SIG256_OID)),
    'gost512': (_alg(GOST512_OID, _seq(_oid('1.2.643.7.1.2.1.2.1'), _oid('1.2.643.7.1.1.2.3'))),
                b'\x44' * 128, _alg('1.2.643.7.1.1.3.3')),
    'unnamed': (_alg(UNNAMED_OID), b'\x55' * 40, _alg(UNNAMED_OID)),
}


def _name(cn):
    return ax.Name.build({'common_name': cn})


def _extensions(is_ca):
    if not is_ca:
        return b''
    exts = ax.Extensions([{'extn_id': 'basic_constraints', 'critical': True,
                           'extn_value': {'ca': True}}])
    return b'\xa3' + core.Integer(0).dump()[:0] + _der_len(exts.dump()) + exts.dump()


def _der_len(content):
    n = len(content)
    if n < 0x80:
        return bytes([n])
    raw = n.to_bytes((n.bit_length() + 7) // 8, 'big')
    return bytes([0x80 | len(raw)]) + raw


def build_cert(kind, cn, issuer_cn=None, is_ca=False, serial=0x1234567):
    key_alg, key_bytes, sig_alg = KEYS[kind]
    utc = dt.timezone.utc
    validity = _seq(core.UTCTime(dt.datetime(2026, 1, 1, tzinfo=utc)),
                    core.UTCTime(dt.datetime(2046, 1, 1, tzinfo=utc)))
    body = b'\xa0\x03\x02\x01\x02' + b''.join(i.dump() for i in (
        core.Integer(serial), sig_alg, _name(issuer_cn or cn), validity, _name(cn),
        _spki(key_alg, key_bytes)))
    body += _extensions(is_ca)
    tbs = core.Sequence(contents=body)
    der = _seq(tbs, sig_alg, core.OctetBitString(b'\x99' * 64)).dump()
    return der


def build_csr(kind, cn):
    key_alg, key_bytes, sig_alg = KEYS[kind]
    info = _seq(core.Integer(0), _name(cn), _spki(key_alg, key_bytes))
    info = core.Sequence(contents=info.contents + b'\xa0\x00')
    return _seq(info, sig_alg, core.OctetBitString(b'\x99' * 64)).dump()


def pem(der, label='CERTIFICATE'):
    b64 = base64.encodebytes(der).decode().replace('\n', '')
    lines = [b64[i:i + 64] for i in range(0, len(b64), 64)]
    return f'-----BEGIN {label}-----\n' + '\n'.join(lines) + f'\n-----END {label}-----\n'


EXPECTED = {
    # kind: (algorithm name, key oid, key size)
    'sm2': ('SM2', SM2_OID, 256),
    'frp': ('FRP256v1', FRP_OID, 256),
    'gost': ('GOST2012-256', GOST256_OID, 256),
    'gost512': ('GOST2012-512', GOST512_OID, 512),
}
NAMED = sorted(EXPECTED)
ALL_KINDS = NAMED + ['unnamed']


@pytest.fixture(params=ALL_KINDS)
def kind(request):
    return request.param


# ------------------------------------------------- the premise: pyca refuses

def test_pyca_cannot_load_these_keys(kind):
    cert = x509.load_der_x509_certificate(build_cert(kind, 'x'))
    with pytest.raises(UnsupportedAlgorithm):
        cert.public_key()


# ------------------------------------------------------------ the helper

def test_describe_public_key(kind):
    from utils.foreign_algorithms import describe_public_key
    cert = x509.load_der_x509_certificate(build_cert(kind, 'x'))
    info = describe_public_key(cert)
    if kind == 'unnamed':
        assert info['name'] is None
        assert info['label'] == UNNAMED_OID
        return
    name, oid, size = EXPECTED[kind]
    assert info['name'] == name
    assert info['oid'] == oid
    assert info['key_size'] == size
    assert info['label'] == name


def test_describe_public_key_of_csr(kind):
    from utils.foreign_algorithms import describe_public_key
    csr = x509.load_der_x509_csr(build_csr(kind, 'x'))
    info = describe_public_key(csr)
    assert info['label'] == (EXPECTED[kind][0] if kind != 'unnamed' else UNNAMED_OID)


def test_describe_public_key_known_key_is_untouched():
    """A key pyca loads is not this module's business."""
    from cryptography.hazmat.primitives.asymmetric import ec
    from utils.foreign_algorithms import describe_public_key
    key = ec.generate_private_key(ec.SECP256R1())
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, 'k')]))
            .issuer_name(x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, 'k')]))
            .public_key(key.public_key()).serial_number(5)
            .not_valid_before(dt.datetime(2026, 1, 1)).not_valid_after(dt.datetime(2027, 1, 1))
            .sign(key, __import__('cryptography').hazmat.primitives.hashes.SHA256()))
    assert describe_public_key(cert) is None


def test_spki_der_of_foreign_certificate_is_the_certificates_own(kind):
    from utils.foreign_algorithms import spki_der
    cert = x509.load_der_x509_certificate(build_cert(kind, 'x'))
    key_alg, key_bytes, _ = KEYS[kind]
    assert spki_der(cert) == _spki(key_alg, key_bytes).dump()


def test_signature_name_is_known_for_foreign_oids():
    from utils.foreign_algorithms import signature_name
    assert signature_name(SM2_SIG_OID) == 'SM2-with-SM3'
    assert signature_name(UNNAMED_OID) is None


# ------------------------------------------------ utils.cert_extensions

def test_parse_certificate_info(kind):
    from utils.cert_extensions import parse_certificate_info
    info = parse_certificate_info(pem(build_cert(kind, 'x')))
    expected = EXPECTED[kind][0] if kind != 'unnamed' else UNNAMED_OID
    assert info['key_algorithm'] == expected
    assert info['key_size'] == (EXPECTED[kind][2] if kind != 'unnamed' else 0)
    assert info['signature_algorithm']
    assert len(info['fingerprint_sha256']) == 64


def test_signature_label_names_foreign_oids():
    from utils.signature_label import signature_algorithm_label
    sm2 = x509.load_der_x509_certificate(build_cert('sm2', 'x'))
    gost = x509.load_der_x509_certificate(build_cert('gost', 'x'))
    unnamed = x509.load_der_x509_certificate(build_cert('unnamed', 'x'))
    assert signature_algorithm_label(sm2) == 'SM2-with-SM3'
    assert 'GOST R 34.10-2012' in signature_algorithm_label(gost)
    assert signature_algorithm_label(unnamed) == UNNAMED_OID
    csr = x509.load_der_x509_csr(build_csr('sm2', 'x'))
    assert signature_algorithm_label(csr) == 'SM2-with-SM3'


# -------------------------------------------------------- trust store

def test_trust_store_certificate_details(kind):
    from services.trust_store.trust_store_service import TrustStoreService
    details = TrustStoreService.parse_certificate_details(pem(build_cert(kind, 'x')).encode())
    pk = details['public_key']
    expected = EXPECTED[kind][0] if kind != 'unnamed' else UNNAMED_OID
    assert pk['algorithm'] == expected
    assert pk['oid'] == (EXPECTED[kind][1] if kind != 'unnamed' else UNNAMED_OID)


# ---------------------------------------------------------- api tools

def test_tools_cert_to_dict(kind):
    from api.v2.tools import cert_to_dict
    cert = x509.load_der_x509_certificate(build_cert(kind, 'x'))
    out = cert_to_dict(cert)
    expected = EXPECTED[kind][0] if kind != 'unnamed' else UNNAMED_OID
    assert out['public_key']['type'] == expected
    assert out['public_key']['oid'] == (EXPECTED[kind][1] if kind != 'unnamed' else UNNAMED_OID)


def test_tools_csr_to_dict(kind):
    from api.v2.tools import csr_to_dict
    csr = x509.load_der_x509_csr(build_csr(kind, 'x'))
    out = csr_to_dict(csr)
    expected = EXPECTED[kind][0] if kind != 'unnamed' else UNNAMED_OID
    assert out['public_key']['type'] == expected


def test_tools_public_key_bytes_of_foreign_certificate():
    from api.v2.tools import get_public_key_bytes
    cert = x509.load_der_x509_certificate(build_cert('frp', 'x'))
    key_alg, key_bytes, _ = KEYS['frp']
    assert get_public_key_bytes(cert) == _spki(key_alg, key_bytes).dump()


# ------------------------------------------------------------- models

def _b64pem(der):
    return base64.b64encode(pem(der).encode()).decode()


def test_certificate_model_describes_foreign_certificate(kind):
    from models import Certificate
    crt = Certificate(refid='r', descr='d', crt=_b64pem(build_cert(kind, 'x')))
    expected = EXPECTED[kind][0] if kind != 'unnamed' else UNNAMED_OID
    assert crt.key_type.split()[0] == expected
    assert crt.key_algorithm == expected
    assert crt.signature_algorithm not in ('N/A', '')
    assert crt.key_size == (EXPECTED[kind][2] if kind != 'unnamed' else 0)
    assert crt.key_algo == expected  # stored spelling follows the certificate
    d = crt.to_dict()
    assert d['key_algorithm'] == expected


def test_certificate_model_names_sm2_signature():
    from models import Certificate
    crt = Certificate(refid='r3', descr='d', crt=_b64pem(build_cert('sm2', 'x')))
    assert crt.signature_algorithm == 'SM2-with-SM3'


def test_certificate_model_csr_only_foreign_key():
    from models import Certificate
    c = Certificate(refid='r2', descr='d', csr=base64.b64encode(pem(build_csr('sm2', 'x'), 'CERTIFICATE REQUEST').encode()).decode())
    assert c.key_type.split()[0] == 'SM2'


def test_ca_model_describes_foreign_certificate(kind):
    from models import CA
    ca = CA(refid='c', descr='d', crt=_b64pem(build_cert(kind, 'x', is_ca=True)))
    expected = EXPECTED[kind][0] if kind != 'unnamed' else UNNAMED_OID
    assert ca.key_type.split()[0] == expected
    assert ca.hash_algorithm not in ('N/A', '')
    assert ca.to_dict()['key_type'].split()[0] == expected


def test_hash_algorithm_of_sm2_ca_is_its_signature_name():
    from models import CA
    ca = CA(refid='c', descr='d', crt=_b64pem(build_cert('sm2', 'x', is_ca=True)))
    assert ca.hash_algorithm == 'SM2-with-SM3'


# --------------------------------------------------------- issuer check

def test_foreign_issuer_is_unverifiable_not_a_mismatch():
    from utils.cert_issuer import UnsupportedIssuerKey, certificate_signed_by
    ca = x509.load_der_x509_certificate(build_cert('sm2', 'ca', is_ca=True))
    leaf = x509.load_der_x509_certificate(build_cert('sm2', 'leaf', issuer_cn='ca'))
    with pytest.raises(UnsupportedIssuerKey):
        certificate_signed_by(leaf, ca)


def test_foreign_signature_under_a_known_key_is_unverifiable():
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from utils.cert_issuer import UnsupportedIssuerKey, certificate_signed_by
    key = ec.generate_private_key(ec.SECP256R1())
    issuer = (x509.CertificateBuilder()
              .subject_name(x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, 'ca')]))
              .issuer_name(x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, 'ca')]))
              .public_key(key.public_key()).serial_number(7)
              .not_valid_before(dt.datetime(2026, 1, 1)).not_valid_after(dt.datetime(2027, 1, 1))
              .sign(key, hashes.SHA256()))
    leaf = x509.load_der_x509_certificate(build_cert('sm2', 'leaf', issuer_cn='ca'))
    with pytest.raises(UnsupportedIssuerKey):
        certificate_signed_by(leaf, issuer)


def test_self_issued_foreign_certificate_is_still_a_root():
    from utils.cert_issuer import is_self_signed
    cert = x509.load_der_x509_certificate(build_cert('gost', 'root', is_ca=True))
    assert is_self_signed(cert) is True


def test_known_keys_still_verify_normally():
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from utils.cert_issuer import certificate_signed_by
    k1, k2 = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())

    def make(key, signer):
        return (x509.CertificateBuilder()
                .subject_name(x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, 'a')]))
                .issuer_name(x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, 'a')]))
                .public_key(key.public_key()).serial_number(9)
                .not_valid_before(dt.datetime(2026, 1, 1)).not_valid_after(dt.datetime(2027, 1, 1))
                .sign(signer, hashes.SHA256()))
    own = make(k1, k1)
    assert certificate_signed_by(own, own) is True
    assert certificate_signed_by(make(k1, k2), own) is False


# --------------------------------------------------------- smart import

def test_smart_import_parser_reads_foreign_certificate(kind):
    from services.smart_import.parser import SmartParser
    objs = SmartParser().parse(pem(build_cert(kind, 'x')))
    assert len(objs) == 1
    expected = EXPECTED[kind][0] if kind != 'unnamed' else UNNAMED_OID
    assert objs[0].key_algorithm == expected
    assert objs[0].key_size == (EXPECTED[kind][2] if kind != 'unnamed' else 0)


def test_smart_import_chain_through_foreign_keys_is_unverifiable():
    from services.smart_import.chain_builder import ChainBuilder
    from services.smart_import.parser import SmartParser
    content = pem(build_cert('sm2', 'root', is_ca=True)) + pem(
        build_cert('sm2', 'leaf', issuer_cn='root', serial=0x777))
    objs = SmartParser().parse(content)
    chains = ChainBuilder().build_chains(objs)
    assert chains
    chain = chains[0]
    d = chain.to_dict()
    assert d['is_valid'] is False
    assert d['verifiable'] is False
    assert any('not verifiable' in e for e in d['errors'])
    assert not any('Signature verification failed' in e for e in d['errors'])


def test_analyze_endpoint_accepts_foreign_chain(auth_client):
    content = pem(build_cert('sm2', 'root', is_ca=True)) + pem(
        build_cert('sm2', 'leaf', issuer_cn='root', serial=0x778))
    r = auth_client.post('/api/v2/import/analyze', data=json.dumps({'content': content}),
                         content_type='application/json')
    assert r.status_code == 200, r.data
    data = r.get_json()['data']
    assert len(data['objects']) == 2
    assert {o['key_algorithm'] for o in data['objects']} == {'SM2'}
    assert all(c['verifiable'] is False for c in data['chains'])


# ------------------------------------------------------------- the API

def test_truststore_import_foreign_certificate(auth_client, kind):
    r = auth_client.post(
        '/api/v2/truststore/import',
        data={'file': (__import__('io').BytesIO(pem(build_cert(kind, f'ts-{kind}', is_ca=True,
                                                               serial=0xA0 + ALL_KINDS.index(kind))).encode()),
                       f'{kind}.pem'), 'name': f'ts-{kind}', 'purpose': 'custom'},
        content_type='multipart/form-data')
    assert r.status_code in (200, 201), r.data
    body = r.get_json()['data']
    shown = auth_client.get(f"/api/v2/truststore/{body['id']}")
    assert shown.status_code == 200, shown.data
    assert auth_client.get('/api/v2/truststore').status_code == 200


def test_truststore_import_foreign_certificate_der(auth_client):
    r = auth_client.post(
        '/api/v2/truststore/import',
        data={'file': (__import__('io').BytesIO(build_cert('frp', 'ts-der', serial=0xB1)), 'x.der'),
              'name': 'ts-der', 'purpose': 'custom'},
        content_type='multipart/form-data')
    assert r.status_code in (200, 201), r.data


def test_import_foreign_leaf_certificate(auth_client, kind):
    r = auth_client.post('/api/v2/certificates/import', data={
        'pem_content': pem(build_cert(kind, f'leaf-{kind}', issuer_cn='Elsewhere',
                                      serial=0xC0 + ALL_KINDS.index(kind))),
        'name': f'leaf-{kind}'})
    assert r.status_code in (200, 201), r.data
    expected = EXPECTED[kind][0] if kind != 'unnamed' else UNNAMED_OID
    assert expected in json.dumps(r.get_json()['data'])


def test_foreign_leaf_is_listed_and_readable(auth_client):
    r = auth_client.post('/api/v2/certificates/import', data={
        'pem_content': pem(build_cert('sm2', 'leaf-listed', issuer_cn='Elsewhere', serial=0xD1)),
        'name': 'leaf-listed'})
    assert r.status_code in (200, 201), r.data
    cid = r.get_json()['data']['id']
    assert auth_client.get(f'/api/v2/certificates/{cid}').status_code == 200
    assert auth_client.get('/api/v2/certificates').status_code == 200


def test_reimport_of_foreign_leaf_does_not_crash(auth_client):
    data = {'pem_content': pem(build_cert('gost', 'leaf-twice', issuer_cn='Elsewhere', serial=0xD2)),
            'name': 'leaf-twice'}
    assert auth_client.post('/api/v2/certificates/import', data=data).status_code in (200, 201)
    again = auth_client.post('/api/v2/certificates/import', data=data)
    assert again.status_code < 500, again.data


def test_import_foreign_ca_certificate(auth_client, kind):
    r = auth_client.post('/api/v2/certificates/import', data={
        'pem_content': pem(build_cert(kind, f'ca-{kind}', is_ca=True,
                                      serial=0xE0 + ALL_KINDS.index(kind))),
        'name': f'ca-{kind}'})
    assert r.status_code in (200, 201), r.data
    cas = auth_client.get('/api/v2/cas')
    assert cas.status_code == 200, cas.data
    expected = EXPECTED[kind][0] if kind != 'unnamed' else UNNAMED_OID
    assert expected in json.dumps(cas.get_json())


def test_foreign_ca_detail_and_chain_endpoints_answer(auth_client):
    r = auth_client.post('/api/v2/cas/import', data={
        'pem_content': pem(build_cert('sm2', 'ca-detail', is_ca=True, serial=0xF1)),
        'name': 'ca-detail'})
    assert r.status_code in (200, 201), r.data
    ca_id = r.get_json()['data']['id']
    assert auth_client.get(f'/api/v2/cas/{ca_id}').status_code == 200
    assert auth_client.get('/api/v2/cas/tree').status_code < 500


# ----------------------------------------- a real SM2 certificate (OpenSSL)

@pytest.mark.skipif(shutil.which('openssl') is None, reason='no openssl')
def test_real_openssl_sm2_certificate(tmp_path):
    key = tmp_path / 'k.pem'
    crt = tmp_path / 'c.pem'
    try:
        subprocess.run(['openssl', 'ecparam', '-name', 'SM2', '-genkey', '-noout', '-out', str(key)],
                       check=True, capture_output=True)
        subprocess.run(['openssl', 'req', '-new', '-x509', '-key', str(key), '-subj', '/CN=sm2-real',
                        '-days', '30', '-sm3', '-out', str(crt)], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        pytest.skip('this OpenSSL has no SM2')
    from utils.cert_extensions import parse_certificate_info
    from services.trust_store.trust_store_service import TrustStoreService
    data = crt.read_bytes()
    info = parse_certificate_info(data.decode())
    assert info['key_algorithm'] == 'SM2'
    assert info['signature_algorithm'] == 'SM2-with-SM3'
    details = TrustStoreService.parse_certificate_details(data)
    assert details['public_key']['oid'] == SM2_OID


# ------------------------------------------------ regression: RSA unchanged

def test_rsa_certificate_description_is_unchanged():
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from utils.cert_extensions import parse_certificate_info
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, 'r')])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(3)
            .not_valid_before(dt.datetime(2026, 1, 1)).not_valid_after(dt.datetime(2027, 1, 1))
            .sign(key, hashes.SHA256()))
    info = parse_certificate_info(cert.public_bytes(serialization.Encoding.PEM).decode())
    assert info['key_algorithm'] == 'RSA'
    assert info['key_size'] == 2048


# ------------------------------------------- read paths over imported records

def test_read_endpoints_answer_for_imported_foreign_records(auth_client):
    leaf = auth_client.post('/api/v2/certificates/import', data={
        'pem_content': pem(build_cert('sm2', 'sweep-leaf', issuer_cn='sweep-ca', serial=0x501)),
        'name': 'sweep-leaf'})
    ca = auth_client.post('/api/v2/certificates/import', data={
        'pem_content': pem(build_cert('sm2', 'sweep-ca', is_ca=True, serial=0x502)),
        'name': 'sweep-ca'})
    assert leaf.status_code in (200, 201), leaf.data
    assert ca.status_code in (200, 201), ca.data
    leaf_id = leaf.get_json()['data']['id']
    ca_id = ca.get_json()['data']['id']
    urls = [
        '/api/v2/certificates?search=sweep', '/api/v2/certificates?sort_by=key_algo',
        '/api/v2/certificates/stats', '/api/v2/certificates/compliance',
        f'/api/v2/certificates/{leaf_id}', f'/api/v2/certificates/{leaf_id}/lint',
        f'/api/v2/certificates/{leaf_id}/export?format=pem',
        f'/api/v2/certificates/{leaf_id}/export?format=pem&include_chain=true',
        '/api/v2/cas', f'/api/v2/cas/{ca_id}', f'/api/v2/cas/{ca_id}/certificates',
        f'/api/v2/cas/{ca_id}/export?format=pem', '/api/v2/truststore', '/api/v2/truststore/stats',
    ]
    codes = {u: auth_client.get(u).status_code for u in urls}
    assert all(code < 500 for code in codes.values()), codes


# ------------------------------------------------------------ decode tools

def test_decode_tools_answer_for_foreign_certificate_and_csr(auth_client):
    r = auth_client.post('/api/v2/tools/decode-cert', json={'pem': pem(build_cert('sm2', 'dec'))})
    assert r.status_code == 200, r.data
    assert r.get_json()['data']['public_key']['type'] == 'SM2'
    r = auth_client.post('/api/v2/tools/decode-csr',
                         json={'pem': pem(build_csr('gost', 'dec'), 'CERTIFICATE REQUEST')})
    assert r.status_code == 200, r.data
    assert r.get_json()['data']['public_key']['type'] == 'GOST2012-256'


def test_key_matcher_compares_foreign_certificate_and_csr(auth_client):
    r = auth_client.post('/api/v2/tools/match-keys', json={
        'certificate': pem(build_cert('frp', 'm')),
        'csr': pem(build_csr('frp', 'm'), 'CERTIFICATE REQUEST')})
    assert r.status_code == 200, r.data
    data = r.get_json()['data']
    assert all(item['valid'] for item in data['items'])
    assert data['all_match'] is True
    other = auth_client.post('/api/v2/tools/match-keys', json={
        'certificate': pem(build_cert('frp', 'm')),
        'csr': pem(build_csr('sm2', 'm'), 'CERTIFICATE REQUEST')})
    assert other.get_json()['data']['all_match'] is False


def test_smart_import_parser_reads_foreign_csr(kind):
    from services.smart_import.parser import SmartParser
    objs = SmartParser().parse(pem(build_csr(kind, 'x'), 'CERTIFICATE REQUEST'))
    assert len(objs) == 1
    assert objs[0].key_algorithm == (EXPECTED[kind][0] if kind != 'unnamed' else UNNAMED_OID)


def test_known_private_key_is_refused_for_foreign_certificate(auth_client):
    from cryptography.hazmat.primitives.asymmetric import ec
    leaf = auth_client.post('/api/v2/certificates/import', data={
        'pem_content': pem(build_cert('sm2', 'key-target', issuer_cn='Elsewhere', serial=0x601)),
        'name': 'key-target', 'import_key': 'false'})
    assert leaf.status_code in (200, 201), leaf.data
    key_pem = ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    r = auth_client.post(f"/api/v2/certificates/{leaf.get_json()['data']['id']}/key", json={'key': key_pem})
    assert r.status_code == 400
    assert 'does not match' in r.get_json()['message']
