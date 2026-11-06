"""EST /serverkeygen key delivery (RFC 7030 §4.4.2): PKCS#8 in clear without a
requested encryption key, else an RFC 5958 key package in SignedData signed by the
issuing CA (RFC 5652 §5.3 signedAttrs) inside EnvelopedData."""
import base64
import hashlib
import subprocess

import pytest
from asn1crypto import cms, core
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed448, ed25519, padding as asym_padding, rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from pyasn1.codec.der import decoder as der_decoder
from pyasn1_alt_modules import rfc5652, rfc5958

from models import CA, Certificate, SystemConfig, db
from tests.test_acme_pq import OPENSSL, needs_openssl_35
from tests.test_est_rfc7030 import (
    EST_PASSWORD, EST_USER, _basic_auth, _make_csr, _multipart_parts, _post_csr, _set_config,
    _unpad_aes_cbc,
)
from utils import key_algorithms

AKEY_PACKAGE = '2.16.840.1.101.2.1.2.78.5'
ASYMMETRIC_ID = '1.2.840.113549.1.9.16.2.54'
SYMMETRIC_ID = '1.2.840.113549.1.9.16.2.37'
_KEYS = ('est_enabled', 'est_ca_refid', 'est_username', 'est_password', 'est_validity_days')
needs_openssl = pytest.mark.skipif(not OPENSSL, reason='needs the openssl command')


def expected_key_package_signer(ca_cert):
    """The certificate that must sign an encrypted serverkeygen package of *ca_cert*."""
    return ca_cert


def openssl_verify_signed_by(signed_p7, anchor_pem, expected_signer, workdir):
    """`openssl cms -verify` against *anchor_pem*, pinned to *expected_signer*; the eContent."""
    verify = subprocess.run(
        [OPENSSL, 'cms', '-verify', '-inform', 'DER', '-in', str(signed_p7),
         '-CAfile', str(anchor_pem), '-purpose', 'any', '-binary',
         '-signer', str(workdir / 'signer.pem'), '-out', str(workdir / 'package.der')],
        capture_output=True, text=True)
    assert verify.returncode == 0, verify.stderr
    signers = x509.load_pem_x509_certificates((workdir / 'signer.pem').read_bytes())
    assert signers == [expected_signer], [c.subject.rfc4514_string() for c in signers]
    return (workdir / 'package.der').read_bytes()


@pytest.fixture(scope='module')
def est_cas(create_ca):
    signing = ['digitalSignature', 'keyCertSign', 'cRLSign']
    return {
        'signing': create_ca(cn='EST keygen signing root', keyUsage=signing),
        # The default root profile: keyCertSign and cRLSign only
        'nosign': create_ca(cn='EST keygen root without digitalSignature'),
    }


@pytest.fixture
def est_ca(app, est_cas):
    with app.app_context():
        previous = {k: getattr(SystemConfig.query.filter_by(key=k).first(), 'value', None)
                    for k in _KEYS}

    def _use(which):
        with app.app_context():
            ca = db.session.get(CA, est_cas[which]['id'])
            for key, value in (('est_enabled', 'true'), ('est_ca_refid', ca.refid),
                               ('est_username', EST_USER), ('est_password', EST_PASSWORD),
                               ('est_validity_days', '30')):
                _set_config(key, value)
            return x509.load_pem_x509_certificate(base64.b64decode(ca.crt))

    yield _use
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


def _enrol_transport(client, cn):
    """A transport certificate the EST CA issued (the presented-certificate rule)."""
    csr, key = _make_csr(common_name=cn)
    r = _post_csr(client, 'simpleenroll', csr, headers=_basic_auth())
    assert r.status_code == 200, r.data
    (cert,) = pkcs7.load_der_pkcs7_certificates(base64.b64decode(r.data))
    return cert, key, cert.public_bytes(serialization.Encoding.PEM).decode()


def _ski(cert):
    return x509.SubjectKeyIdentifier.from_public_key(cert.public_key()).digest


def _issued(parts):
    (cert,) = pkcs7.load_der_pkcs7_certificates(parts[0].get_payload(decode=True))
    return cert


def _same_key(private_key, cert):
    der = serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    return private_key.public_key().public_bytes(*der) == cert.public_key().public_bytes(*der)


def _decrypt_signed_data(part, client_key):
    enveloped = cms.ContentInfo.load(part.get_payload(decode=True))
    assert enveloped['content_type'].native == 'enveloped_data'
    recipient = enveloped['content']['recipient_infos'][0].chosen
    cek = client_key.decrypt(recipient['encrypted_key'].native, asym_padding.OAEP(
        mgf=asym_padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    info = enveloped['content']['encrypted_content_info']
    assert info['content_type'].native == 'signed_data'
    iv = info['content_encryption_algorithm']['parameters'].native
    return _unpad_aes_cbc(info['encrypted_content'].native, cek, iv)


def _encrypted_keygen(client, est_ca, cn):
    ca_cert = est_ca('signing')
    transport, client_key, client_pem = _enrol_transport(client, f'transport-{cn}')
    csr, _ = _make_csr(common_name=cn, extra_attributes=((ASYMMETRIC_ID, _ski(transport)),))
    r = _post_csr(client, 'serverkeygen', csr, client_cert_pem=client_pem)
    assert r.status_code == 200, r.data
    parts = _multipart_parts(r)
    assert parts[1].get_content_type() == 'application/pkcs7-mime'
    assert parts[1].get_param('smime-type') == 'server-generated-key'
    return ca_cert, transport, client_key, parts


class TestClearPkcs8:
    """§4.4.2: without additional encryption the key part MUST be application/pkcs8."""

    def test_basic_returns_an_unencrypted_private_key_info(self, client, est_ca):
        est_ca('signing')
        csr, _ = _make_csr(common_name='clear-basic.keygen.test')
        r = _post_csr(client, 'serverkeygen', csr, headers=_basic_auth())
        assert r.status_code == 200, r.data
        parts = _multipart_parts(r)
        assert [p.get_content_type() for p in parts] == ['application/pkcs7-mime', 'application/pkcs8']
        key = serialization.load_der_private_key(parts[1].get_payload(decode=True), password=None)
        assert _same_key(key, _issued(parts))

    def test_mtls_without_an_identifier_returns_an_unencrypted_private_key_info(self, client, est_ca):
        est_ca('signing')
        _, _, client_pem = _enrol_transport(client, 'transport-clear.keygen.test')
        csr, _ = _make_csr(common_name='clear-mtls.keygen.test')
        r = _post_csr(client, 'serverkeygen', csr, client_cert_pem=client_pem)
        assert r.status_code == 200, r.data
        parts = _multipart_parts(r)
        assert parts[1].get_content_type() == 'application/pkcs8'
        key = serialization.load_der_private_key(parts[1].get_payload(decode=True), password=None)
        assert _same_key(key, _issued(parts))

    def test_a_root_without_digital_signature_still_delivers_in_clear(self, client, est_ca):
        est_ca('nosign')
        csr, _ = _make_csr(common_name='clear-nosign.keygen.test')
        r = _post_csr(client, 'serverkeygen', csr, headers=_basic_auth())
        assert r.status_code == 200, r.data
        assert _multipart_parts(r)[1].get_content_type() == 'application/pkcs8'


class TestKeyPackage:

    def test_signed_data_carries_an_asymmetric_key_package_signed_by_the_issuing_ca(
            self, client, est_ca):
        ca_cert, _, client_key, parts = _encrypted_keygen(client, est_ca, 'package.keygen.test')
        signed_der = _decrypt_signed_data(parts[1], client_key)

        # Decoded by pyasn1 with the RFC 5652 and RFC 5958 modules, not by the encoder's library
        signed, rest = der_decoder.decode(signed_der, asn1Spec=rfc5652.SignedData())
        assert not rest
        assert int(signed['version']) == 3  # RFC 5652 §5.1: eContentType is not id-data
        econtent = signed['encapContentInfo']
        assert str(econtent['eContentType']) == AKEY_PACKAGE
        package, rest = der_decoder.decode(bytes(econtent['eContent']),
                                           asn1Spec=rfc5958.AsymmetricKeyPackage())
        assert not rest and len(package) == 1
        from pyasn1.codec.der import encoder as der_encoder
        key = serialization.load_der_private_key(der_encoder.encode(package[0]), password=None)
        assert _same_key(key, _issued(parts))

        (signer,) = signed['signerInfos']
        sid = signer['sid']['issuerAndSerialNumber']
        assert int(sid['serialNumber']) == ca_cert.serial_number
        attrs = {str(a['attrType']): a['attrValues'] for a in signer['signedAttrs']}
        assert str(der_decoder.decode(bytes(attrs[str(rfc5652.id_contentType)][0]))[0]) == AKEY_PACKAGE
        digest = bytes(der_decoder.decode(bytes(attrs[str(rfc5652.id_messageDigest)][0]))[0])
        assert digest == hashlib.sha256(bytes(econtent['eContent'])).digest()

        # The signature covers the DER of signedAttrs as a SET OF (RFC 5652 §5.4)
        from pyasn1.codec.der import encoder as der_encoder
        attrs_set = rfc5652.SignedAttributes()
        for a in signer['signedAttrs']:
            attrs_set.append(a)
        to_be_signed = der_encoder.encode(attrs_set)
        ca_cert.public_key().verify(bytes(signer['signature']), to_be_signed,
                                    asym_padding.PKCS1v15(), hashes.SHA256())
        with pytest.raises(Exception):
            key.public_key().verify(bytes(signer['signature']), to_be_signed,
                                    asym_padding.PKCS1v15(), hashes.SHA256())

    @needs_openssl
    def test_openssl_decrypts_and_verifies_against_the_cacerts_anchor(
            self, client, est_ca, tmp_path):
        ca_cert, transport, client_key, parts = _encrypted_keygen(client, est_ca,
                                                                  'openssl.keygen.test')
        cacerts = client.get('/.well-known/est/cacerts')
        assert cacerts.status_code == 200
        (tmp_path / 'cacerts.p7').write_bytes(base64.b64decode(cacerts.data))
        subprocess.run([OPENSSL, 'pkcs7', '-inform', 'DER', '-in', str(tmp_path / 'cacerts.p7'),
                        '-print_certs', '-out', str(tmp_path / 'anchor.pem')], check=True)
        (tmp_path / 'key.p7').write_bytes(parts[1].get_payload(decode=True))
        (tmp_path / 'client.pem').write_bytes(transport.public_bytes(serialization.Encoding.PEM))
        (tmp_path / 'client.key').write_bytes(client_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))
        subprocess.run([OPENSSL, 'cms', '-decrypt', '-inform', 'DER', '-in', str(tmp_path / 'key.p7'),
                        '-recip', str(tmp_path / 'client.pem'), '-inkey', str(tmp_path / 'client.key'),
                        '-binary', '-out', str(tmp_path / 'signed.der')], check=True,
                       capture_output=True)
        # EnvelopedData carries the SignedData content: wrap it in its ContentInfo for openssl
        signed = cms.SignedData.load((tmp_path / 'signed.der').read_bytes())
        (tmp_path / 'signed.p7').write_bytes(
            cms.ContentInfo({'content_type': 'signed_data', 'content': signed}).dump())
        package_der = openssl_verify_signed_by(tmp_path / 'signed.p7', tmp_path / 'anchor.pem',
                                               expected_key_package_signer(ca_cert), tmp_path)
        printed = subprocess.run(
            [OPENSSL, 'cms', '-cmsout', '-print', '-inform', 'DER', '-in', str(tmp_path / 'signed.p7')],
            capture_output=True, text=True, check=True).stdout
        assert '2.16.840.1.101.2.1.2.78.5' in printed or 'id-ct-KP-aKeyPackage' in printed
        package, _ = der_decoder.decode(package_der, asn1Spec=rfc5958.AsymmetricKeyPackage())
        assert len(package) == 1

    def test_a_signer_failure_answers_5xx_before_any_certificate_is_issued(
            self, app, client, est_ca, monkeypatch):
        import utils.est_cms as est_cms
        est_ca('signing')
        transport, _, client_pem = _enrol_transport(client, 'transport-hsmfail.keygen.test')

        def failing_suite(_key):
            raise ValueError('The HSM returned a signature that does not verify')
        monkeypatch.setattr(est_cms, '_signature_suite', failing_suite)
        cn = 'hsmfail.keygen.test'
        csr, _ = _make_csr(common_name=cn, extra_attributes=((ASYMMETRIC_ID, _ski(transport)),))
        r = _post_csr(client, 'serverkeygen', csr, client_cert_pem=client_pem)
        assert r.status_code >= 500, (r.status_code, r.data)
        assert b'client' not in r.data.lower()
        with app.app_context():
            assert Certificate.query.filter(Certificate.subject_cn == cn).count() == 0

    def test_a_ca_without_digital_signature_refuses_to_sign_before_issuing(
            self, app, client, est_ca):
        est_ca('nosign')
        transport, _, client_pem = _enrol_transport(client, 'transport-nosign.keygen.test')
        cn = 'refused-nosign.keygen.test'
        csr, _ = _make_csr(common_name=cn, extra_attributes=((ASYMMETRIC_ID, _ski(transport)),))
        r = _post_csr(client, 'serverkeygen', csr, client_cert_pem=client_pem)
        assert r.status_code == 400, r.data
        assert b'digitalSignature' in r.data
        with app.app_context():
            assert Certificate.query.filter(Certificate.subject_cn == cn).count() == 0


class TestRequestedProtection:
    """§4.4.1.1 and §4.4.1.2: a requested key the server lacks terminates the request."""

    def test_basic_with_an_asymmetric_identifier_is_refused(self, client, est_ca, caplog):
        est_ca('signing')
        csr, _ = _make_csr(common_name='basic-asym.keygen.test',
                           extra_attributes=((ASYMMETRIC_ID, b'\x01' * 20),))
        with caplog.at_level('WARNING', logger='api.est_protocol'):
            r = _post_csr(client, 'serverkeygen', csr, headers=_basic_auth())
        assert r.status_code == 400, r.data
        logged = ' '.join(rec.getMessage() for rec in caplog.records if rec.name == 'api.est_protocol')
        assert 'Basic' in logged and 'authenticated client certificate' not in logged

    def test_basic_with_a_symmetric_identifier_is_refused(self, client, est_ca):
        est_ca('signing')
        csr, _ = _make_csr(common_name='basic-sym.keygen.test',
                           extra_attributes=((SYMMETRIC_ID, b'\x02' * 20),))
        r = _post_csr(client, 'serverkeygen', csr, headers=_basic_auth())
        assert r.status_code == 400, r.data

    def test_a_client_certificate_without_key_transport_usage_is_refused(self, client, est_ca):
        est_ca('signing')
        csr, client_key = _make_csr(common_name='transport-signonly.keygen.test')
        csr = (x509.CertificateSigningRequestBuilder().subject_name(csr.subject)
               .add_extension(x509.KeyUsage(True, False, False, False, False, False, False,
                                            False, False), critical=True)
               .sign(client_key, hashes.SHA256()))
        r = _post_csr(client, 'simpleenroll', csr, headers=_basic_auth())
        assert r.status_code == 200, r.data
        (transport,) = pkcs7.load_der_pkcs7_certificates(base64.b64decode(r.data))
        usage = transport.extensions.get_extension_for_class(x509.KeyUsage).value
        if usage.key_encipherment:
            pytest.skip('the EST profile adds keyEncipherment to RSA certificates')
        keygen_csr, _ = _make_csr(common_name='signonly.keygen.test',
                                  extra_attributes=((ASYMMETRIC_ID, _ski(transport)),))
        r = _post_csr(client, 'serverkeygen', keygen_csr,
                      client_cert_pem=transport.public_bytes(serialization.Encoding.PEM).decode())
        assert r.status_code == 400, r.data


def _self_signed_signer(key, *, digital_signature=True):
    import datetime
    from cryptography.x509.oid import NameOID
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'keygen cms signer')])
    now = datetime.datetime.now(datetime.timezone.utc)
    algorithm = None if isinstance(key, (ed25519.Ed25519PrivateKey, ed448.Ed448PrivateKey)) \
        or key_algorithms.family_for_public_key(key.public_key()) == 'ML-DSA' else hashes.SHA256()
    return (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=30))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(digital_signature, False, False, False, False, True, True,
                                         False, False), critical=True)
            .sign(key, algorithm))


def _signer_keys():
    keys = {
        'rsa': lambda: rsa.generate_private_key(65537, 2048),
        'ec-p384': lambda: ec.generate_private_key(ec.SECP384R1()),
        'ed25519': ed25519.Ed25519PrivateKey.generate,
        'ed448': ed448.Ed448PrivateKey.generate,
    }
    if key_algorithms.mldsa_supported():
        keys['ml-dsa-65'] = lambda: key_algorithms.generate('ML-DSA-65')
    return keys


def _verify_with_openssl(signed, signer_cert, tmp_path):
    (tmp_path / 'signed.p7').write_bytes(
        cms.ContentInfo({'content_type': 'signed_data', 'content': signed}).dump())
    (tmp_path / 'anchor.pem').write_bytes(signer_cert.public_bytes(serialization.Encoding.PEM))
    return openssl_verify_signed_by(tmp_path / 'signed.p7', tmp_path / 'anchor.pem',
                                    signer_cert, tmp_path)


def _verify_ed448(signed, signer_cert):
    """OpenSSL lacks id-shake256-len in CMS: pyasn1 decoding and pyca verification instead."""
    from pyasn1.codec.der import encoder as der_encoder
    decoded, _ = der_decoder.decode(signed.dump(), asn1Spec=rfc5652.SignedData())
    (signer,) = decoded['signerInfos']
    assert str(signer['digestAlgorithm']['algorithm']) == '2.16.840.1.101.3.4.2.18'
    assert der_decoder.decode(bytes(signer['digestAlgorithm']['parameters']))[0] == 512
    package = bytes(decoded['encapContentInfo']['eContent'])
    attrs = {str(a['attrType']): a['attrValues'] for a in signer['signedAttrs']}
    digest = bytes(der_decoder.decode(bytes(attrs[str(rfc5652.id_messageDigest)][0]))[0])
    assert digest == hashlib.shake_256(package).digest(64)
    attrs_set = rfc5652.SignedAttributes()
    for a in signer['signedAttrs']:
        attrs_set.append(a)
    signer_cert.public_key().verify(bytes(signer['signature']), der_encoder.encode(attrs_set))
    return package


@needs_openssl
@pytest.mark.parametrize('which', [
    pytest.param(name, marks=needs_openssl_35) if name.startswith('ml-dsa') else name
    for name in sorted(_signer_keys())])
def test_every_ca_key_family_signs_a_package_an_independent_verifier_accepts(which, tmp_path):
    from utils.est_cms import signed_key_package
    signer_key = _signer_keys()[which]()
    signer_cert = _self_signed_signer(signer_key)
    generated = ec.generate_private_key(ec.SECP256R1())
    signed = signed_key_package(generated, signer_key, signer_cert)
    if which == 'ed448':
        package_der = _verify_ed448(signed, signer_cert)
    else:
        package_der = _verify_with_openssl(signed, signer_cert, tmp_path)
    package, _ = der_decoder.decode(package_der, asn1Spec=rfc5958.AsymmetricKeyPackage())
    from pyasn1.codec.der import encoder as der_encoder
    assert _same_key(serialization.load_der_private_key(der_encoder.encode(package[0]), None),
                     _self_signed_signer(generated))


@needs_openssl
def test_an_rsa_pss_ca_signs_with_pss(tmp_path):
    from utils.est_cms import signed_key_package
    from utils.signing_hash import PssBoundRSAKey
    raw = rsa.generate_private_key(65537, 2048)
    signer_cert = _self_signed_signer(raw)
    signed = signed_key_package(ec.generate_private_key(ec.SECP256R1()), PssBoundRSAKey(raw),
                                signer_cert)
    assert signed['signer_infos'][0]['signature_algorithm']['algorithm'].native == 'rsassa_pss'
    _verify_with_openssl(signed, signer_cert, tmp_path)


class _BoundDigestKey:
    """An HSM-like EC key whose provider signs with SHA-512 whatever is asked."""

    def __init__(self, key):
        self._key = key
        self.curve = key.curve
        self.key_size = key.key_size

    def public_key(self):
        return self._key.public_key()

    def signing_hash(self, requested):
        return hashes.SHA512()

    def sign(self, data, algorithm):
        assert isinstance(algorithm.algorithm, hashes.SHA512)
        return self._key.sign(data, algorithm)


ec.EllipticCurvePrivateKey.register(_BoundDigestKey)


def test_a_provider_bound_digest_drives_the_cms_digest():
    from utils.est_cms import signed_key_package
    raw = ec.generate_private_key(ec.SECP256R1())
    signed = signed_key_package(ec.generate_private_key(ec.SECP256R1()), _BoundDigestKey(raw),
                                _self_signed_signer(raw))
    info = signed['signer_infos'][0]
    assert info['digest_algorithm']['algorithm'].native == 'sha512'
    assert info['signature_algorithm']['algorithm'].native == 'sha512_ecdsa'
    raw.public_key().verify(info['signature'].native, b'\x31' + info['signed_attrs'].dump()[1:],
                            ec.ECDSA(hashes.SHA512()))


def test_a_signer_certificate_without_digital_signature_is_named():
    from utils.est_cms import key_package_signer_problem
    key = ec.generate_private_key(ec.SECP256R1())
    assert key_package_signer_problem(_self_signed_signer(key)) is None
    assert 'digitalSignature' in key_package_signer_problem(
        _self_signed_signer(key, digital_signature=False))


def test_attribute_encoding_is_a_der_set():
    """openssl re-encodes signedAttrs as DER before verifying: the order must be canonical."""
    from utils.est_cms import signed_key_package
    key = ec.generate_private_key(ec.SECP256R1())
    signed = signed_key_package(ec.generate_private_key(ec.SECP256R1()), key,
                                _self_signed_signer(key))
    attrs = signed['signer_infos'][0]['signed_attrs']
    encoded = [a.dump() for a in attrs]
    assert encoded == sorted(encoded)
    assert isinstance(attrs, core.SetOf)
