"""CMS SignedData outputs of EST, SCEP and TSA under fixed keys, time and nonces.

``fixtures/cms/regenerate.py`` writes them; ``test_cms_signed_golden.py`` compares.
"""
import datetime as _dt
import json
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest import mock

from asn1crypto import cms, core, tsp
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import dsa, ec, ed448, ed25519, padding, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

FIXTURES = Path(__file__).parent / 'fixtures' / 'cms'
PQC_KEY = Path(__file__).parent / 'fixtures' / 'pqc' / 'mldsa65-seed.pem'
FIXED_TIME = _dt.datetime(2026, 11, 7, 12, 0, 0, tzinfo=_dt.timezone.utc)
NONCE = bytes(range(16))
TST_DATA = b'timestamped by the golden fixtures'
_HASHES = {'sha256': hashes.SHA256, 'sha384': hashes.SHA384, 'sha512': hashes.SHA512}
_GENERATORS = {
    'rsa': lambda: rsa.generate_private_key(65537, 2048),
    'ec256': lambda: ec.generate_private_key(ec.SECP256R1()),
    'ec384': lambda: ec.generate_private_key(ec.SECP384R1()),
    'ed25519': ed25519.Ed25519PrivateKey.generate,
    'ed448': ed448.Ed448PrivateKey.generate,
    'dsa': lambda: dsa.generate_private_key(2048),
    'package': lambda: ec.generate_private_key(ec.SECP256R1()),
}
SIGNERS = ('rsa', 'ec256', 'ec384', 'ed25519', 'ed448', 'dsa', 'mldsa')


def _write_material():
    """Root RSA CA and one timeStamping leaf per signer key (run once, then kept)."""
    keys = {name: make() for name, make in _GENERATORS.items()}
    keys['root'] = rsa.generate_private_key(65537, 2048)
    keys['mldsa'] = serialization.load_pem_private_key(PQC_KEY.read_bytes(), None)
    for name, key in keys.items():
        if name != 'mldsa':
            (FIXTURES / f'{name}-key.pem').write_bytes(key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption()))
    root_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'CMS golden root')])
    start, end = FIXED_TIME - _dt.timedelta(days=1), FIXED_TIME + _dt.timedelta(days=36500)
    root = (x509.CertificateBuilder().subject_name(root_name).issuer_name(root_name)
            .public_key(keys['root'].public_key()).serial_number(1)
            .not_valid_before(start).not_valid_after(end)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(True, False, False, False, False, True, True, False, False),
                           critical=True)
            .sign(keys['root'], hashes.SHA256()))
    (FIXTURES / 'root.pem').write_bytes(root.public_bytes(serialization.Encoding.PEM))
    for serial, name in enumerate(SIGNERS, start=2):
        leaf = (x509.CertificateBuilder()
                .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f'CMS golden {name}')]))
                .issuer_name(root_name).public_key(keys[name].public_key()).serial_number(serial)
                .not_valid_before(start).not_valid_after(end)
                .add_extension(x509.KeyUsage(True, False, False, False, False, False, False, False, False),
                               critical=True)
                .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.TIME_STAMPING]), critical=True)
                .sign(keys['root'], hashes.SHA256()))
        (FIXTURES / f'{name}.pem').write_bytes(leaf.public_bytes(serialization.Encoding.PEM))


def material():
    """(keys, certs) by name; certs['root'] is the anchor."""
    keys = {name: serialization.load_pem_private_key((FIXTURES / f'{name}-key.pem').read_bytes(), None)
            for name in (*_GENERATORS, 'root')}
    keys['mldsa'] = serialization.load_pem_private_key(PQC_KEY.read_bytes(), None)
    certs = {name: x509.load_pem_x509_certificate((FIXTURES / f'{name}.pem').read_bytes())
             for name in (*SIGNERS, 'root')}
    return keys, certs


# HSM key ids of the fake provider: RSA bound to SHA-384, EC to SHA-512, ML-DSA
_HSM_BOUND = {1: 'sha384', 2: 'sha512'}


@contextmanager
def fake_hsm(keys):
    """HsmService.sign/signing_hash backed by the software keys."""
    from services.hsm import HsmService
    soft = {1: keys['rsa'], 2: keys['ec256'], 3: keys['mldsa']}

    def sign(key_id, data, key_algorithm=None, hash_algorithm=None, padding=None, **_):
        key = soft[key_id]
        if isinstance(key, rsa.RSAPrivateKey):
            h = _HASHES[hash_algorithm]()
            pad = (_pss(h) if padding == 'pss' else _v15())
            return key.sign(data, pad, h)
        if isinstance(key, ec.EllipticCurvePrivateKey):
            return key.sign(data, ec.ECDSA(_HASHES[hash_algorithm]()))
        return key.sign(data)

    def signing_hash(key_id, key_algorithm=None, requested='sha256'):
        return _HSM_BOUND.get(key_id, requested)

    with mock.patch.object(HsmService, 'sign', sign), \
            mock.patch.object(HsmService, 'signing_hash', signing_hash):
        yield


def _pss(h):
    return padding.PSS(mgf=padding.MGF1(h), salt_length=h.digest_size)


def _v15():
    return padding.PKCS1v15()


def _hsm_keys(keys):
    from services.hsm.hsm_private_key import (
        HsmECPrivateKey, HsmMLDSA65PrivateKey, HsmRSAPrivateKey)
    return {
        'hsm_rsa': HsmRSAPrivateKey(1, keys['rsa'].public_key(), 'RSA-2048'),
        'hsm_ec': HsmECPrivateKey(2, keys['ec256'].public_key(), 'EC-P256'),
        'hsm_mldsa': HsmMLDSA65PrivateKey(3, keys['mldsa'].public_key()),
    }


def _signer(keys, certs, name):
    """(signer key, signer cert) for a case name: software, PSS-bound or HSM wrapper."""
    from utils.signing_hash import PssBoundRSAKey
    if name == 'rsa_pss':
        return PssBoundRSAKey(keys['rsa']), certs['rsa']
    if name.startswith('hsm_'):
        base = {'hsm_rsa': 'rsa', 'hsm_ec': 'ec256', 'hsm_mldsa': 'mldsa'}[name]
        return _hsm_keys(keys)[name], certs[base]
    return keys[name], certs[name]


def tst_info_der(hash_name='sha256'):
    import hashlib
    return tsp.TSTInfo({
        'version': 'v1', 'policy': '1.2.3.4.1',
        'message_imprint': {'hash_algorithm': {'algorithm': hash_name},
                            'hashed_message': hashlib.new(hash_name, TST_DATA).digest()},
        'serial_number': 0x1234567890ABCDEF, 'gen_time': FIXED_TIME, 'nonce': 42,
    }).dump()


def _scep_attrs():
    return [
        {'type': '2.16.840.1.113733.1.9.7', 'values': [core.PrintableString('golden-txn')]},
        {'type': '2.16.840.1.113733.1.9.2', 'values': [core.PrintableString('3')]},
        {'type': '2.16.840.1.113733.1.9.3', 'values': [core.PrintableString('0')]},
        {'type': '2.16.840.1.113733.1.9.5', 'values': [core.OctetString(NONCE)]},
        {'type': '2.16.840.1.113733.1.9.6', 'values': [core.OctetString(NONCE[::-1])]},
    ]


# name -> (kind, signer, deterministic, build(signer_key, signer_cert, keys, certs) -> DER)
def _est(chain=()):
    def build(key, cert, keys, certs):
        from utils.est_cms import signed_key_package
        return signed_key_package(keys['package'], key, cert, [certs[c] for c in chain]).dump()
    return build


def _scep(data=b'golden scep payload', attrs=True):
    def build(key, cert, keys, certs):
        from services.scep.crypto_helpers import create_signed_pkcs7
        return create_signed_pkcs7(data, key, cert, signed_attributes=_scep_attrs() if attrs else None)
    return build


def _scep_rep(status, fail_info=None):
    def build(key, cert, keys, certs):
        from services.scep import response_builder
        return response_builder.build_cert_rep(status, b'', 'golden-txn', NONCE[::-1], key, cert,
                                               fail_info=fail_info)
    return build


def _scep_degenerate(crl=False):
    def build(key, cert, keys, certs):
        from services.scep.crypto_helpers import create_degenerate_pkcs7
        if not crl:
            return create_degenerate_pkcs7([certs['rsa'], certs['root']])
        revoked = (x509.CertificateRevocationListBuilder()
                   .issuer_name(certs['root'].subject)
                   .last_update(FIXED_TIME).next_update(FIXED_TIME + _dt.timedelta(days=7))
                   .sign(keys['root'], hashes.SHA256()))
        return create_degenerate_pkcs7([], crls=[revoked])
    return build


def _tsa(hash_name='sha256', include_certs=True, chain=False):
    def build(key, cert, keys, certs):
        from services.tsa_service import TSAService
        service = TSAService(cert, key, chain_certs=[certs['root']] if chain else None)
        return service._build_signed_response(tst_info_der(hash_name), include_certs, hash_name)
    return build


def _tsa_request(key, cert, keys, certs):
    """Full process_request with uuid and clock pinned."""
    import hashlib
    from services.tsa_service import TSAService
    req = tsp.TimeStampReq({
        'version': 'v1',
        'message_imprint': {'hash_algorithm': {'algorithm': 'sha256'},
                            'hashed_message': hashlib.sha256(TST_DATA).digest()},
        'nonce': 7, 'cert_req': True,
    }).dump()
    der, status = TSAService(cert, key).process_request(req)
    assert status == 200
    return der


CASES = {
    'est_rsa': ('est', 'rsa', True, _est()),
    'est_rsa_chain': ('est', 'rsa', True, _est(chain=('root', 'ed25519'))),
    'est_rsa_pss': ('est', 'rsa_pss', False, _est()),
    'est_ec256': ('est', 'ec256', False, _est()),
    'est_ec384': ('est', 'ec384', False, _est()),
    'est_ed25519': ('est', 'ed25519', True, _est()),
    'est_ed448': ('est', 'ed448', True, _est()),
    'est_mldsa': ('est', 'mldsa', False, _est()),
    'est_hsm_rsa': ('est', 'hsm_rsa', True, _est()),
    'est_hsm_ec': ('est', 'hsm_ec', False, _est()),
    'est_hsm_mldsa': ('est', 'hsm_mldsa', False, _est()),
    'scep_rsa': ('scep', 'rsa', True, _scep()),
    'scep_rsa_no_content': ('scep', 'rsa', True, _scep(data=None)),
    'scep_rsa_no_attrs': ('scep', 'rsa', True, _scep(attrs=False)),
    'scep_rsa_pending': ('scep', 'rsa', True, _scep_rep(3)),
    'scep_rsa_failure': ('scep', 'rsa', True, _scep_rep(2, fail_info=2)),
    'scep_rsa_pss': ('scep', 'rsa_pss', False, _scep()),
    'scep_ec256': ('scep', 'ec256', False, _scep()),
    'scep_ec384': ('scep', 'ec384', False, _scep()),
    'scep_ed25519': ('scep', 'ed25519', True, _scep()),
    'scep_dsa': ('scep', 'dsa', False, _scep()),
    'scep_hsm_rsa': ('scep', 'hsm_rsa', True, _scep()),
    'scep_hsm_ec': ('scep', 'hsm_ec', False, _scep()),
    'scep_degenerate_certs': ('scep', 'rsa', True, _scep_degenerate()),
    'scep_degenerate_crl': ('scep', 'rsa', True, _scep_degenerate(crl=True)),
    'tsa_rsa': ('tsa', 'rsa', True, _tsa()),
    'tsa_rsa_sha384': ('tsa', 'rsa', True, _tsa('sha384')),
    'tsa_rsa_sha512': ('tsa', 'rsa', True, _tsa('sha512')),
    'tsa_rsa_no_certs': ('tsa', 'rsa', True, _tsa(include_certs=False)),
    'tsa_rsa_chain': ('tsa', 'rsa', True, _tsa(chain=True)),
    'tsa_rsa_request': ('tsa', 'rsa', True, _tsa_request),
    'tsa_ec256': ('tsa', 'ec256', False, _tsa()),
    'tsa_ec384_sha512': ('tsa', 'ec384', False, _tsa('sha512')),
    'tsa_mldsa': ('tsa', 'mldsa', False, _tsa()),
    'tsa_hsm_rsa': ('tsa', 'hsm_rsa', True, _tsa()),
    'tsa_hsm_ec': ('tsa', 'hsm_ec', False, _tsa()),
    'tsa_hsm_mldsa': ('tsa', 'hsm_mldsa', False, _tsa('sha384')),
}

# Refusals whose message is part of the contract
ERROR_CASES = {
    'est_dsa': ('dsa', _est()),
    'scep_ed448': ('ed448', _scep()),
    'scep_mldsa': ('mldsa', _scep()),
    'tsa_ed25519': ('ed25519', _tsa()),
    'tsa_rsa_pss': ('rsa_pss', _tsa()),
}


@contextmanager
def pinned():
    """Clock, nonces and serials of the three callers fixed."""
    class _Clock(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return FIXED_TIME if tz else FIXED_TIME.replace(tzinfo=None)

    import uuid
    with ExitStack() as stack:
        stack.enter_context(mock.patch('services.scep.crypto_helpers.datetime', _Clock))
        stack.enter_context(mock.patch('services.tsa_service.datetime', _Clock))
        stack.enter_context(mock.patch('services.scep.response_builder.secrets.token_bytes',
                                       lambda n: NONCE[:n]))
        stack.enter_context(mock.patch('services.tsa_service.uuid.uuid4',
                                       lambda: uuid.UUID(int=0x0123456789ABCDEF0123456789ABCDEF)))
        yield


def build(name):
    kind, signer, _det, make = CASES[name]
    keys, certs = material()
    key, cert = _signer(keys, certs, signer)
    with pinned(), fake_hsm(keys):
        return make(key, cert, keys, certs)


def build_error(name):
    signer, make = ERROR_CASES[name]
    keys, certs = material()
    key, cert = _signer(keys, certs, signer)
    with pinned(), fake_hsm(keys):
        try:
            make(key, cert, keys, certs)
        except Exception as e:  # noqa: BLE001 (the message is the fixture)
            # A ValueError subclass still meets the callers' contract
            return f"{'ValueError' if isinstance(e, ValueError) else type(e).__name__}: {e}"
    return 'no error'


def signed_data(der, kind):
    """The SignedData of an EST package, a SCEP ContentInfo or a TSA TimeStampResp."""
    if kind == 'est':
        return cms.SignedData.load(der)
    if kind == 'tsa':
        return tsp.TimeStampResp.load(der)['time_stamp_token']['content']
    return cms.ContentInfo.load(der)['content']


def structure(der, kind):
    """Every encoded field but the signature values, for randomised signatures."""
    parts = []
    if kind == 'tsa':
        resp = tsp.TimeStampResp.load(der)
        parts += [resp['status'].dump(), resp['time_stamp_token']['content_type'].dump()]
    elif kind == 'scep':
        parts.append(cms.ContentInfo.load(der)['content_type'].dump())
    sd = signed_data(der, kind)
    for field in ('version', 'digest_algorithms', 'encap_content_info', 'certificates', 'crls'):
        parts.append(sd[field].dump())
    for info in sd['signer_infos']:
        for field in ('version', 'sid', 'digest_algorithm', 'signed_attrs', 'signature_algorithm',
                      'unsigned_attrs'):
            parts.append(info[field].dump())
    return [p.hex() for p in parts]


def errors_fixture():
    return json.loads((FIXTURES / 'errors.json').read_text())
