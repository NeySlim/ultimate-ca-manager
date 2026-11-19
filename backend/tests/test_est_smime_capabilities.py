"""EST /serverkeygen key encryption (RFC 7030 §4.4.2): the key wrap is one the CSR's
SMIMECapabilities list (RFC 8551 §2.5.2, in the client's order of preference); an EC client
certificate gets KeyAgreeRecipientInfo with ephemeral-static ECDH (RFC 5652 §6.2.2, RFC 5753
§3.1). Every response is decrypted by OpenSSL and decoded by pyasn1, not by the encoder."""
import base64
import datetime
import subprocess

import pytest
from asn1crypto import cms
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding as asym_padding, rsa
from cryptography.hazmat.primitives.kdf.x963kdf import X963KDF
from cryptography.hazmat.primitives.keywrap import aes_key_unwrap
from cryptography.x509.name import _ASN1Type
from cryptography.x509.oid import NameOID
from pyasn1.codec.der import decoder as der_decoder, encoder as der_encoder
from pyasn1.type import tag, univ
from pyasn1_alt_modules import rfc2986, rfc4055, rfc5280, rfc5652, rfc5751, rfc5753, rfc5958

import fips_mode
from models import Certificate
from tests.test_est_rfc7030 import _multipart_parts, _post_csr, _unpad_aes_cbc
from tests.test_est_serverkeygen_cms import (  # noqa: F401 (fixtures)
    ASYMMETRIC_ID, est_ca, est_cas, expected_key_package_signer, needs_openssl,
    openssl_verify_signed_by,
)
from utils.est_key_encryption import UnsupportedCapabilities, choose_key_encryption, smime_capabilities

SMIME_CAPABILITIES = '1.2.840.113549.1.9.15'


def _hex(text):
    return bytes.fromhex(''.join(text.split()))


# RFC 3565 §5.1
AES128_CBC = _hex('30 0B 06 09 60 86 48 01 65 03 04 01 02')
AES192_CBC = _hex('30 0B 06 09 60 86 48 01 65 03 04 01 16')
AES256_CBC = _hex('30 0B 06 09 60 86 48 01 65 03 04 01 2A')
AES256_GCM = _hex('30 0B 06 09 60 86 48 01 65 03 04 01 2E')
# RFC 3560 §5: rSAES-OAEP-Default-Identifier (SHA-1, MGF1 with SHA-1)
OAEP_DEFAULT = _hex('30 0D 06 09 2A 86 48 86 F7 0D 01 01 07 30 00')
RSA_ENCRYPTION = _hex('30 0D 06 09 2A 86 48 86 F7 0D 01 01 01 05 00')
# RFC 5990: id-rsa-kem, a key transport UCM does not offer
RSA_KEM = _hex('30 0D 06 0B 2A 86 48 86 F7 0D 01 09 10 03 0E')


def _oaep(identifier):
    """An RSAES-OAEP capability as the RFC 4055 ASN.1 module encodes it (pyasn1)."""
    return der_encoder.encode(identifier)


OAEP_SHA256 = _oaep(rfc4055.rSAES_OAEP_SHA256_Identifier)
OAEP_SHA384 = _oaep(rfc4055.rSAES_OAEP_SHA384_Identifier)
OAEP_SHA512 = _oaep(rfc4055.rSAES_OAEP_SHA512_Identifier)


def _oaep_mixed(hash_id, mgf_id):
    """RSAES-OAEP with a hash and an MGF1 identifier of its own (RFC 4055 module, pyasn1)."""
    params = rfc4055.RSAES_OAEP_params()
    if hash_id is not None:
        params['hashFunc'] = hash_id.subtype(explicitTag=tag.Tag(
            tag.tagClassContext, tag.tagFormatConstructed, 0), cloneValueFlag=True)
    if mgf_id is not None:
        params['maskGenFunc'] = mgf_id.subtype(explicitTag=tag.Tag(
            tag.tagClassContext, tag.tagFormatConstructed, 1), cloneValueFlag=True)
    identifier = rfc5280.AlgorithmIdentifier()
    identifier['algorithm'] = rfc4055.id_RSAES_OAEP
    identifier['parameters'] = params
    return der_encoder.encode(identifier)


OAEP_SHA256_MGF1_SHA1 = _oaep_mixed(rfc4055.sha256Identifier, None)
OAEP_SHA1_MGF1_SHA256 = _oaep_mixed(None, rfc4055.mgf1SHA256Identifier)
# RFC 3560 §5, copied: rSAES-OAEP-SHA256-Identifier and -SHA384- as printed (no [0]/[1] tags)
RFC3560_OAEP_SHA256 = _hex("""30 38 06 09 2A 86 48 86 F7 0D 01 01 07 30 2B 30
    0D 06 09 60 86 48 01 65 03 04 02 01 05 00 30 1A 06 09 2A 86 48 86 F7 0D 01 01 08 30 0D 06 09 60
    86 48 01 65 03 04 02 01 05 00""".replace('\n', ' '))
RFC3560_OAEP_SHA384 = _hex("""30 38 06 09 2A 86 48 86 F7 0D 01 01 07 30 2B 30
    0D 06 09 60 86 48 01 65 03 04 02 02 05 00 30 1A 06 09 2A 86 48 86 F7 0D 01 01 08 30 0D 06 09 60
    86 48 01 65 03 04 02 02 05 00""".replace('\n', ' '))
# RSAES-OAEP-params with a field the module lacks, at the top and inside hashFunc: not defaults
OAEP_UNKNOWN_FIELD = _hex('30 10 06 09 2A 86 48 86 F7 0D 01 01 07 30 03 02 01 01')
# RSAES-OAEP-params found by fuzzing that made the parser raise AttributeError (a REAL, an
# ObjectDescriptor, an InstanceOf where an AlgorithmIdentifier part was expected)
OAEP_GARBLED = [_hex('30 3c 06 09 2A 86 48 86 F7 0D 01 01 07') + _hex(h) for h in (
    '302fa00f300d06096086480165030402010500091c301a06092a864886f70d010108300d06096086480165030402'
    '0105a5',
    '302fa00f300d06096086480165030402010500a11c301a06092a864886060d010108300d06096086480165030402'
    '010700',
    '302fa00f300d06026086480165030402010500a11c301a06092a864886f70d010108300d060960860c0165030402'
    '013000')]
OAEP_NESTED_EXTRA = _hex('30 21 06 09 2A 86 48 86 F7 0D 01 01 07 30 14 A0 12 30 10'
                         '06 09 60 86 48 01 65 03 04 02 01 05 00 02 01 01')


def _ka(scheme, wrap):
    """RFC 5753 §6 key agreement capability: scheme OID last arcs, wrap OID last arc."""
    arc, kdf = scheme
    return _hex(f'30 15 06 06 2b 81 04 01 {arc:02x} {kdf:02x} 30 0b 06 09 60 86 48 01 65 03 04 01 {wrap:02x}')


STD, COFACTOR = 0x0B, 0x0E
SHA224, SHA256, SHA384, SHA512 = range(4)
WRAP128, WRAP192, WRAP256 = 0x05, 0x19, 0x2D
# RFC 5753 §6, copied: KA=ECDH standard KDF=SHA-256 Wrap=AES-128 and Wrap=AES-256
assert _ka((STD, SHA256), WRAP128) == _hex(
    '30 15 06 06 2b 81 04 01 0B 01 30 0b 06 09 60 86 48 01 65 03 04 01 05')
assert _ka((STD, SHA256), WRAP256) == _hex(
    '30 15 06 06 2b 81 04 01 0B 01 30 0b 06 09 60 86 48 01 65 03 04 01 2D')


def _ka_wrap_params(wrap, params):
    """A key agreement capability whose KeyWrapAlgorithm carries *params*."""
    return _hex(f'30 {0x15 + len(params):02x} 06 06 2b 81 04 01 0B 01 30 {0x0b + len(params):02x}'
                f' 06 09 60 86 48 01 65 03 04 01 {wrap:02x}') + params

_KDF_HASH = {'1.3.132.1.11.0': hashes.SHA224, '1.3.132.1.11.1': hashes.SHA256,
             '1.3.132.1.11.2': hashes.SHA384, '1.3.132.1.11.3': hashes.SHA512,
             '1.3.132.1.14.0': hashes.SHA224, '1.3.132.1.14.1': hashes.SHA256,
             '1.3.132.1.14.2': hashes.SHA384, '1.3.132.1.14.3': hashes.SHA512}
_WRAP = {'2.16.840.1.101.3.4.1.5': 16, '2.16.840.1.101.3.4.1.25': 24, '2.16.840.1.101.3.4.1.45': 32}
_CBC = {'2.16.840.1.101.3.4.1.2': 16, '2.16.840.1.101.3.4.1.22': 24, '2.16.840.1.101.3.4.1.42': 32}
_OAEP_HASH = {'1.3.14.3.2.26': hashes.SHA1, '2.16.840.1.101.3.4.2.4': hashes.SHA224,
              '2.16.840.1.101.3.4.2.1': hashes.SHA256, '2.16.840.1.101.3.4.2.2': hashes.SHA384,
              '2.16.840.1.101.3.4.2.3': hashes.SHA512}


def _capabilities_der(capabilities):
    """SMIMECapabilities (RFC 5751 module, pyasn1) of DER SMIMECapability entries."""
    value = rfc5751.SMIMECapabilities()
    for entry in capabilities:
        value.append(der_decoder.decode(entry, asn1Spec=rfc5751.SMIMECapability())[0])
    return der_encoder.encode(value)


def _keygen_csr(cn, ski, capabilities=None, values=1, attributes=1, raw_value=None):
    """A serverkeygen CSR naming *ski*, with an SMIMECapabilities attribute unless None;
    *raw_value* is put as the attribute value instead of an encoded list."""
    key = rsa.generate_private_key(65537, 2048)
    builder = (x509.CertificateSigningRequestBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
               .add_attribute(x509.ObjectIdentifier(ASYMMETRIC_ID), ski, _tag=_ASN1Type.OctetString))
    csr = builder.sign(key, hashes.SHA256())
    if capabilities is None and raw_value is None:
        return csr
    request, _ = der_decoder.decode(csr.public_bytes(serialization.Encoding.DER),
                                    asn1Spec=rfc2986.CertificationRequest())
    info = request['certificationRequestInfo']
    for _ in range(attributes):
        attribute = info['attributes'].getComponentType().clone()
        attribute['type'] = rfc5751.smimeCapabilities
        for _ in range(values):
            attribute['values'].append(raw_value or _capabilities_der(capabilities))
        info['attributes'].append(attribute)
    tbs = der_encoder.encode(info)
    request['signature'] = univ.BitString.fromOctetString(
        key.sign(tbs, asym_padding.PKCS1v15(), hashes.SHA256()))
    return x509.load_der_x509_csr(der_encoder.encode(request))


_ISSUER_KEY = ec.generate_private_key(ec.SECP384R1())
_ISSUER = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Manufacturer test CA')])


def _client_certificate(key, usage='encrypt'):
    """A client certificate from another authority (RFC 7030 §3.3.2: accepted as presented).
    *usage*: 'encrypt' (keyEncipherment or keyAgreement), 'sign' (digitalSignature) or None."""
    now = datetime.datetime.now(datetime.timezone.utc)
    builder = (x509.CertificateBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'est client')]))
               .issuer_name(_ISSUER).public_key(key.public_key())
               .serial_number(x509.random_serial_number())
               .not_valid_before(now - datetime.timedelta(days=1))
               .not_valid_after(now + datetime.timedelta(days=30)))
    if usage is not None:
        is_rsa = isinstance(key, rsa.RSAPrivateKey)
        encrypt = usage == 'encrypt'
        builder = builder.add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False,
            key_encipherment=encrypt and is_rsa, data_encipherment=False,
            key_agreement=encrypt and not is_rsa, key_cert_sign=False, crl_sign=False,
            encipher_only=False, decipher_only=False), critical=True)
    return builder.sign(_ISSUER_KEY, hashes.SHA384())


def _ski(cert):
    return x509.SubjectKeyIdentifier.from_public_key(cert.public_key()).digest


def _serverkeygen(client, cert, cn, capabilities=None, **csr_options):
    csr = _keygen_csr(cn, _ski(cert), capabilities, **csr_options)
    return _post_csr(client, 'serverkeygen', csr,
                     client_cert_pem=cert.public_bytes(serialization.Encoding.PEM).decode())


def _pem_files(tmp_path, cert, key):
    (tmp_path / 'client.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (tmp_path / 'client.key').write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))


def _openssl_open(client, ca_cert, parts, cert, key, tmp_path):
    """`openssl cms -decrypt -recip client.pem -inkey client.key`, then `-verify` against the
    /cacerts anchor pinned to the key generator: the RFC 5958 package."""
    _pem_files(tmp_path, cert, key)
    (tmp_path / 'key.p7').write_bytes(parts[1].get_payload(decode=True))
    decrypt = subprocess.run(
        ['openssl', 'cms', '-decrypt', '-inform', 'DER', '-in', 'key.p7', '-recip', 'client.pem',
         '-inkey', 'client.key', '-binary', '-out', 'signed.der'],
        capture_output=True, text=True, cwd=tmp_path)
    assert decrypt.returncode == 0, decrypt.stderr
    signed = cms.SignedData.load((tmp_path / 'signed.der').read_bytes())
    (tmp_path / 'signed.p7').write_bytes(
        cms.ContentInfo({'content_type': 'signed_data', 'content': signed}).dump())
    cacerts = client.get('/.well-known/est/cacerts')
    (tmp_path / 'cacerts.p7').write_bytes(base64.b64decode(cacerts.data))
    subprocess.run(['openssl', 'pkcs7', '-inform', 'DER', '-in', 'cacerts.p7', '-print_certs',
                    '-out', 'anchor.pem'], check=True, cwd=tmp_path)
    package_der = openssl_verify_signed_by(
        tmp_path / 'signed.p7', tmp_path / 'anchor.pem',
        expected_key_package_signer(client.application, ca_cert), tmp_path)
    (package,) = der_decoder.decode(package_der, asn1Spec=rfc5958.AsymmetricKeyPackage())[0]
    generated = serialization.load_der_private_key(der_encoder.encode(package), None)
    (issued,) = serialization.pkcs7.load_der_pkcs7_certificates(parts[0].get_payload(decode=True))
    spki = serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    assert generated.public_key().public_bytes(*spki) == issued.public_key().public_bytes(*spki)


def _enveloped(parts):
    """The response EnvelopedData, decoded by pyasn1 with the RFC 5652 module."""
    content_info, rest = der_decoder.decode(parts[1].get_payload(decode=True),
                                            asn1Spec=rfc5652.ContentInfo())
    assert not rest and content_info['contentType'] == rfc5652.id_envelopedData
    enveloped, rest = der_decoder.decode(content_info['content'], asn1Spec=rfc5652.EnvelopedData())
    assert not rest
    return enveloped


def _content(enveloped, cek):
    info = enveloped['encryptedContentInfo']
    oid = str(info['contentEncryptionAlgorithm']['algorithm'])
    assert len(cek) == _CBC[oid]
    iv = bytes(der_decoder.decode(info['contentEncryptionAlgorithm']['parameters'])[0])
    signed = _unpad_aes_cbc(bytes(info['encryptedContent']), cek, iv)
    der_decoder.decode(signed, asn1Spec=rfc5652.SignedData())
    return oid


def _kari(enveloped, cert):
    """The kari fields RFC 5753 §3.1.1 fixes, decoded by pyasn1."""
    assert int(enveloped['version']) == 2  # RFC 5652 §6.1: a version 3 RecipientInfo
    (info,) = enveloped['recipientInfos']
    assert info.getName() == 'kari'
    kari = info['kari']
    assert int(kari['version']) == 3
    originator = kari['originator']
    assert originator.getName() == 'originatorKey'
    assert originator['originatorKey']['algorithm']['algorithm'] == rfc5753.id_ecPublicKey
    assert kari['ukm'].isValue and len(bytes(kari['ukm'])) > 0
    (recipient,) = kari['recipientEncryptedKeys']
    rid = recipient['rid']['issuerAndSerialNumber']
    assert int(rid['serialNumber']) == cert.serial_number
    assert der_encoder.encode(rid['issuer']) == cert.issuer.public_bytes()
    algorithm = kari['keyEncryptionAlgorithm']
    wrap, rest = der_decoder.decode(algorithm['parameters'], asn1Spec=rfc5753.KeyWrapAlgorithm())
    assert not rest and not wrap['parameters'].isValue  # RFC 3565 §2.3.2: absent
    return kari, str(algorithm['algorithm']), wrap, recipient


def _kari_cek(enveloped, cert, key):
    """The CEK by an independent ECDH: X9.63 KDF over ECC-CMS-SharedInfo built by pyasn1."""
    kari, scheme, wrap, recipient = _kari(enveloped, cert)
    point = kari['originator']['originatorKey']['publicKey'].asOctets()
    ephemeral = ec.EllipticCurvePublicKey.from_encoded_point(key.curve, point)
    size = _WRAP[str(wrap['algorithm'])]
    shared_info = rfc5753.ECC_CMS_SharedInfo()
    shared_info['keyInfo']['algorithm'] = wrap['algorithm']
    shared_info['entityUInfo'] = bytes(kari['ukm'])
    shared_info['suppPubInfo'] = (size * 8).to_bytes(4, 'big')
    kek = X963KDF(_KDF_HASH[scheme](), size, der_encoder.encode(shared_info)).derive(
        key.exchange(ec.ECDH(), ephemeral))
    return scheme, str(wrap['algorithm']), aes_key_unwrap(kek, bytes(recipient['encryptedKey']))


def _ktri_cek(enveloped, cert, key):
    assert int(enveloped['version']) == 0
    (info,) = enveloped['recipientInfos']
    assert info.getName() == 'ktri'
    ktri = info['ktri']
    rid = ktri['rid']['issuerAndSerialNumber']
    assert int(rid['serialNumber']) == cert.serial_number
    algorithm = ktri['keyEncryptionAlgorithm']
    encrypted = bytes(ktri['encryptedKey'])
    if algorithm['algorithm'] == rfc4055.rsaEncryption:
        assert der_encoder.encode(algorithm['parameters']) == b'\x05\x00'  # RFC 3370 §4.2.1
        return ('pkcs1v15',), key.decrypt(encrypted, asym_padding.PKCS1v15())
    assert algorithm['algorithm'] == rfc4055.id_RSAES_OAEP
    params, _ = der_decoder.decode(algorithm['parameters'], asn1Spec=rfc4055.RSAES_OAEP_params())
    # RFC 4055 §4.1: the encoder omits hashFunc for SHA-1
    hash_oid = str(params['hashFunc']['algorithm']) if params['hashFunc'].isValue else '1.3.14.3.2.26'
    if params['maskGenFunc'].isValue:
        mgf_hash, _ = der_decoder.decode(params['maskGenFunc']['parameters'],
                                         asn1Spec=rfc5280.AlgorithmIdentifier())
        mgf_oid = str(mgf_hash['algorithm'])
    else:
        mgf_oid = '1.3.14.3.2.26'
    assert not params['pSourceFunc'].isValue
    cek = key.decrypt(encrypted, asym_padding.OAEP(
        mgf=asym_padding.MGF1(_OAEP_HASH[mgf_oid]()), algorithm=_OAEP_HASH[hash_oid](), label=None))
    return ('oaep', _OAEP_HASH[hash_oid].name, _OAEP_HASH[mgf_oid].name), cek


def _assert_ok(response):
    assert response.status_code == 200, response.data
    parts = _multipart_parts(response)
    assert parts[1].get_param('smime-type') == 'server-generated-key'
    return parts


_CURVES = {'P-256': ec.SECP256R1, 'P-384': ec.SECP384R1, 'P-521': ec.SECP521R1,
           'brainpoolP256r1': ec.BrainpoolP256R1}


@needs_openssl
class TestKeyAgreement:
    """EC client certificates: kari, ephemeral-static ECDH (RFC 5753 §3.1)."""

    @pytest.mark.parametrize('curve', sorted(_CURVES))
    def test_without_capabilities_the_defaults_decrypt_with_openssl(
            self, client, est_ca, tmp_path, curve):
        ca_cert = est_ca('signing')
        key = ec.generate_private_key(_CURVES[curve]())
        cert = _client_certificate(key)
        parts = _assert_ok(_serverkeygen(client, cert, f'kari-{curve}.keygen.test'))
        enveloped = _enveloped(parts)
        scheme, wrap, cek = _kari_cek(enveloped, cert, key)
        assert (scheme, wrap) == ('1.3.132.1.11.1', '2.16.840.1.101.3.4.1.45')
        assert _content(enveloped, cek) == '2.16.840.1.101.3.4.1.42'
        _openssl_open(client, ca_cert, parts, cert, key, tmp_path)

    @pytest.mark.parametrize('capabilities,expected', [
        # The first key agreement listed, its key wrap size for the content cipher
        ([_ka((STD, SHA384), WRAP128), _ka((STD, SHA256), WRAP256)],
         ('1.3.132.1.11.2', '2.16.840.1.101.3.4.1.5', '2.16.840.1.101.3.4.1.2')),
        ([_ka((STD, SHA512), WRAP256), _ka((STD, SHA256), WRAP128)],
         ('1.3.132.1.11.3', '2.16.840.1.101.3.4.1.45', '2.16.840.1.101.3.4.1.42')),
        ([_ka((COFACTOR, SHA224), WRAP192)],
         ('1.3.132.1.14.0', '2.16.840.1.101.3.4.1.25', '2.16.840.1.101.3.4.1.22')),
        # The first content cipher listed, then the first key agreement of the same size
        ([AES128_CBC, AES256_CBC, _ka((STD, SHA384), WRAP256), _ka((STD, SHA256), WRAP128)],
         ('1.3.132.1.11.1', '2.16.840.1.101.3.4.1.5', '2.16.840.1.101.3.4.1.2')),
        ([AES256_GCM, AES192_CBC, AES256_CBC, _ka((STD, SHA256), WRAP256)],
         ('1.3.132.1.11.1', '2.16.840.1.101.3.4.1.45', '2.16.840.1.101.3.4.1.42')),
        # Unknown and RSA entries are passed over
        ([OAEP_SHA256, _hex('30 0a 06 08 2a 86 48 ce 3d 04 03 02'), _ka((STD, SHA384), WRAP192)],
         ('1.3.132.1.11.2', '2.16.840.1.101.3.4.1.25', '2.16.840.1.101.3.4.1.22')),
        # RFC 8551 §2.5.2, the list is partial: no matching or usable content cipher, the
        # AES-CBC of the key wrap size; no key agreement listed, the default one
        ([_ka((STD, SHA256), WRAP128), AES256_CBC],
         ('1.3.132.1.11.1', '2.16.840.1.101.3.4.1.5', '2.16.840.1.101.3.4.1.2')),
        ([AES256_GCM, _ka((STD, SHA384), WRAP192)],
         ('1.3.132.1.11.2', '2.16.840.1.101.3.4.1.25', '2.16.840.1.101.3.4.1.22')),
        ([AES128_CBC], ('1.3.132.1.11.1', '2.16.840.1.101.3.4.1.45', '2.16.840.1.101.3.4.1.42')),
        # KeyWrapAlgorithm parameters: NULL read as absent, any other value passes the entry over
        ([_ka_wrap_params(WRAP128, b'\x05\x00')],
         ('1.3.132.1.11.1', '2.16.840.1.101.3.4.1.5', '2.16.840.1.101.3.4.1.2')),
        ([_ka_wrap_params(WRAP128, b'\x04\x00'), _ka((STD, SHA384), WRAP256)],
         ('1.3.132.1.11.2', '2.16.840.1.101.3.4.1.45', '2.16.840.1.101.3.4.1.42')),
        ([AES128_CBC, _ka((STD, SHA384), WRAP128), _ka((STD, SHA256), WRAP128)],
         ('1.3.132.1.11.2', '2.16.840.1.101.3.4.1.5', '2.16.840.1.101.3.4.1.2')),
    ], ids=['kdf384-wrap128', 'kdf512-wrap256', 'cofactor-224-wrap192', 'content-first',
            'gcm-skipped', 'others-skipped', 'no-size-match', 'gcm-only', 'content-only',
            'wrap-null-params', 'wrap-params-passed-over', 'ka-order-same-size'])
    def test_capabilities_pick_the_algorithms_in_the_client_order(
            self, client, est_ca, tmp_path, capabilities, expected):
        ca_cert = est_ca('signing')
        key = ec.generate_private_key(ec.SECP256R1())
        cert = _client_certificate(key)
        parts = _assert_ok(_serverkeygen(client, cert, 'kari-caps.keygen.test', capabilities))
        enveloped = _enveloped(parts)
        scheme, wrap, cek = _kari_cek(enveloped, cert, key)
        assert (scheme, wrap, _content(enveloped, cek)) == expected
        _openssl_open(client, ca_cert, parts, cert, key, tmp_path)

    def test_a_certificate_without_key_usage_is_unrestricted(self, client, est_ca, tmp_path):
        ca_cert = est_ca('signing')
        key = ec.generate_private_key(ec.SECP384R1())
        cert = _client_certificate(key, usage=None)
        parts = _assert_ok(_serverkeygen(client, cert, 'kari-noku.keygen.test'))
        _openssl_open(client, ca_cert, parts, cert, key, tmp_path)


@needs_openssl
class TestKeyTransport:
    """RSA client certificates: ktri with the key transport and the content cipher listed."""

    @pytest.mark.parametrize('capabilities,expected', [
        (None, (('oaep', 'sha256', 'sha256'), '2.16.840.1.101.3.4.1.42')),
        ([OAEP_SHA512, OAEP_SHA256, AES192_CBC, AES256_CBC],
         (('oaep', 'sha512', 'sha512'), '2.16.840.1.101.3.4.1.22')),
        ([AES128_CBC, OAEP_SHA384], (('oaep', 'sha384', 'sha384'), '2.16.840.1.101.3.4.1.2')),
        ([OAEP_DEFAULT], (('oaep', 'sha1', 'sha1'), '2.16.840.1.101.3.4.1.42')),
        # RSAES-PKCS1-v1_5 only when no OAEP is listed
        ([RSA_ENCRYPTION, OAEP_SHA256], (('oaep', 'sha256', 'sha256'), '2.16.840.1.101.3.4.1.42')),
        ([RSA_ENCRYPTION, AES128_CBC], (('pkcs1v15',), '2.16.840.1.101.3.4.1.2')),
        ([_ka((STD, SHA256), WRAP256), AES256_GCM, AES128_CBC, OAEP_SHA256],
         (('oaep', 'sha256', 'sha256'), '2.16.840.1.101.3.4.1.2')),
        ([OAEP_SHA256_MGF1_SHA1], (('oaep', 'sha256', 'sha1'), '2.16.840.1.101.3.4.1.42')),
        ([OAEP_SHA1_MGF1_SHA256], (('oaep', 'sha1', 'sha256'), '2.16.840.1.101.3.4.1.42')),
        # RFC 3560 §5 printed encodings, matched byte for byte
        ([RFC3560_OAEP_SHA256], (('oaep', 'sha256', 'sha256'), '2.16.840.1.101.3.4.1.42')),
        ([RFC3560_OAEP_SHA384], (('oaep', 'sha384', 'sha384'), '2.16.840.1.101.3.4.1.42')),
        # Parameters with unknown fields are passed over, not read as the SHA-1 defaults
        ([OAEP_UNKNOWN_FIELD, OAEP_SHA384], (('oaep', 'sha384', 'sha384'), '2.16.840.1.101.3.4.1.42')),
        ([OAEP_NESTED_EXTRA, OAEP_SHA384], (('oaep', 'sha384', 'sha384'), '2.16.840.1.101.3.4.1.42')),
        # RFC 8551 §2.5.2, the list is partial: AES-256-CBC, or the default transport
        ([OAEP_SHA256, AES256_GCM], (('oaep', 'sha256', 'sha256'), '2.16.840.1.101.3.4.1.42')),
        ([AES128_CBC], (('oaep', 'sha256', 'sha256'), '2.16.840.1.101.3.4.1.2')),
        *[([garbled, OAEP_SHA384], (('oaep', 'sha384', 'sha384'), '2.16.840.1.101.3.4.1.42'))
          for garbled in OAEP_GARBLED],
    ], ids=['defaults', 'sha512-aes192', 'sha384-aes128', 'oaep-default-sha1', 'oaep-over-v15',
            'v15-alone', 'others-skipped', 'sha256-mgf1-sha1', 'sha1-mgf1-sha256',
            'rfc3560-sha256', 'rfc3560-sha384', 'unknown-field', 'nested-unknown-field',
            'gcm-only', 'content-only', 'garbled-real', 'garbled-descriptor',
            'garbled-instance-of'])
    def test_capabilities_pick_the_algorithms_in_the_client_order(
            self, client, est_ca, tmp_path, capabilities, expected):
        ca_cert = est_ca('signing')
        key = rsa.generate_private_key(65537, 2048)
        cert = _client_certificate(key)
        parts = _assert_ok(_serverkeygen(client, cert, 'ktri-caps.keygen.test', capabilities))
        enveloped = _enveloped(parts)
        transport, cek = _ktri_cek(enveloped, cert, key)
        assert (transport, _content(enveloped, cek)) == expected
        _openssl_open(client, ca_cert, parts, cert, key, tmp_path)


def _no_certificate_for(app, cn):
    with app.app_context():
        return Certificate.query.filter(Certificate.subject_cn == cn).count() == 0


class TestRefusals:
    """RFC 7030 §4.4.1.2: a key the server cannot encrypt to terminates the request, before
    any certificate is issued."""

    @pytest.mark.parametrize('key_type,capabilities,expected', [
        ('ec', [OAEP_SHA256, AES256_CBC], 'key agreement dhSinglePass'),
        ('ec', [_ka((STD, SHA256), 0x30)], 'key agreement dhSinglePass'),  # id-aes256-wrap-pad
        ('ec', [_ka_wrap_params(WRAP128, b'\x04\x00')], 'key agreement dhSinglePass'),
        ('rsa', [_ka((STD, SHA256), WRAP256)], 'RSAES-OAEP'),
        ('rsa', [OAEP_UNKNOWN_FIELD, AES128_CBC], 'RSAES-OAEP'),
        ('rsa', [RSA_KEM, AES256_CBC, AES192_CBC], 'RSAES-OAEP'),
    ], ids=['ec-rsa-only', 'ec-unknown-wrap', 'ec-wrap-params', 'rsa-ka-only', 'rsa-unknown-field',
            'rsa-kem-only'])
    def test_capabilities_with_nothing_supported_are_refused(
            self, app, client, est_ca, key_type, capabilities, expected):
        est_ca('signing')
        key = ec.generate_private_key(ec.SECP256R1()) if key_type == 'ec' else \
            rsa.generate_private_key(65537, 2048)
        cn = f'refused-{key_type}-{len(capabilities)}.keygen.test'
        r = _serverkeygen(client, _client_certificate(key), cn, capabilities)
        assert r.status_code == 400, r.data
        assert b'supported: ' in r.data and expected.encode() in r.data, r.data
        assert _no_certificate_for(app, cn)

    @pytest.mark.parametrize('options', [{'values': 2}, {'attributes': 2}])
    def test_a_repeated_capabilities_attribute_is_refused(self, app, client, est_ca, options):
        """RFC 8551 §2.5.2: a single attribute with a single value."""
        est_ca('signing')
        cn = f'malformed-{sorted(options)[0]}.keygen.test'
        csr = _keygen_csr(cn, b'\x01', [OAEP_SHA256], **options)
        with pytest.raises(ValueError):
            smime_capabilities(csr.public_bytes(serialization.Encoding.DER))
        r = _serverkeygen(client, _client_certificate(rsa.generate_private_key(65537, 2048)), cn,
                          [OAEP_SHA256], **options)
        assert r.status_code == 400, r.data
        assert _no_certificate_for(app, cn)

    @pytest.mark.parametrize('key,usage,expected', [
        (lambda: ec.generate_private_key(ec.SECP256R1()), 'sign', b'key agreement'),
        (lambda: rsa.generate_private_key(65537, 2048), 'sign', b'key transport'),
        (lambda: ec.generate_private_key(ec.SECP224R1()), 'encrypt', b'curve'),
        (ed25519.Ed25519PrivateKey.generate, None, b'Unsupported client key'),
        (lambda: rsa.generate_private_key(65537, 1024), 'encrypt', b'under 2048 bits'),
    ], ids=['ec-sign-only', 'rsa-sign-only', 'ec-p224', 'ed25519', 'rsa-1024'])
    def test_a_client_key_that_cannot_receive_is_refused(self, app, client, est_ca, key, usage,
                                                          expected):
        est_ca('signing')
        private_key = key()
        if isinstance(private_key, ed25519.Ed25519PrivateKey):
            now = datetime.datetime.now(datetime.timezone.utc)
            cert = (x509.CertificateBuilder().subject_name(_ISSUER).issuer_name(_ISSUER)
                    .public_key(private_key.public_key()).serial_number(7)
                    .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=1))
                    .sign(private_key, None))
        else:
            cert = _client_certificate(private_key, usage)
        cn = f'refused-key-{cert.serial_number % 100000}.keygen.test'
        r = _serverkeygen(client, cert, cn, [OAEP_SHA256, _ka((STD, SHA256), WRAP256)])
        assert r.status_code == 400 and expected in r.data, r.data
        assert _no_certificate_for(app, cn)


    @needs_openssl
    def test_an_rsassa_pss_key_is_refused(self, app, client, est_ca, tmp_path):
        """RFC 4055 §1.2: an id-RSASSA-PSS subject key is for signatures only."""
        est_ca('signing')
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa-pss', '-pkeyopt',
                        'rsa_keygen_bits:2048', '-nodes', '-keyout', 'pss.key', '-out', 'pss.pem',
                        '-subj', '/CN=pss client', '-days', '2',
                        '-addext', 'keyUsage=critical,digitalSignature,keyEncipherment'],
                       check=True, capture_output=True, cwd=tmp_path)
        cert = x509.load_pem_x509_certificate((tmp_path / 'pss.pem').read_bytes())
        assert cert.public_key_algorithm_oid.dotted_string == '1.2.840.113549.1.1.10'
        cn = 'refused-pss.keygen.test'
        r = _serverkeygen(client, cert, cn, [OAEP_SHA256])
        assert r.status_code == 400 and b'RSASSA-PSS' in r.data, r.data
        assert _no_certificate_for(app, cn)

    # Found by fuzzing the attribute: a REAL, an InstanceOf, an ObjectDescriptor where the
    # parser expected another type
    @pytest.mark.parametrize('value', [
        '3064303c06092a864886f70d010107302fa00f300d06096086480165030402010500a11c301a06092a864886'
        'a00d010108300d06096086480165030402010500301506062b8104010b01090b060960864801650304012d'
        '300d06092a864886f70d01010730a1',
        '3064303c06092a864886f70d010107302fa00f300d0609608648016503040201a100a181301a06092a8648'
        '86f70d010108300d06096086480165030402010500301506062b8104f60b01300b06096086480165030401'
        '2d300d06092a864886f70d0101078800',
        '3064303c06092a864886f70d010109302fa00f300d06096086480165030402010500a11c301a06092a8648'
        '86f70d010108304106096006480165030402010500301506062b8104010b01e70b06096086480165030401'
        '2d300d06092a864886f70d0101073000',
    ], ids=['real', 'instance-of', 'object-descriptor'])
    def test_a_garbled_attribute_is_a_logged_400(self, app, client, est_ca, caplog, value):
        est_ca('signing')
        cn = f'garbled-{value[-6:]}.keygen.test'
        cert = _client_certificate(ec.generate_private_key(ec.SECP256R1()))
        csr = _keygen_csr(cn, _ski(cert), raw_value=bytes.fromhex(value))
        with caplog.at_level('WARNING', logger='api.est_protocol'):
            r = _post_csr(client, 'serverkeygen', csr,
                          client_cert_pem=cert.public_bytes(serialization.Encoding.PEM).decode())
        assert r.status_code == 400 and b'Server key generation failed' not in r.data, r.data
        records = [rec for rec in caplog.records if rec.name == 'api.est_protocol']
        assert records and all(rec.levelname == 'WARNING' for rec in records)
        assert _no_certificate_for(app, cn)


    # Found by fuzzing: entries whose parameters crash a re-encoding of the attribute; they are
    # passed over as unsupported, the attribute itself is read
    @pytest.mark.parametrize('value,status', [
        ('3055303c06132a864886f70d0101073000a00f300d06096086480165030402010500a11c301a06092a8648'
         '86f70d010108300d06096086480165030402010500301506062b8104010b01300b06096086480165030401'
         '2d', 200),
        ('3055303c06092a864886f70d010107302fa00f300d06076086480165030402010500a11c301a06092a8648'
         '86f70d010108300d06096086480165030402010500301506062b8104010b01090b05096086480165030401'
         '2d', 400),
        ('3055303c06092a864886f70d010107302fa00f300d06096086480165030402010500a11c301a06a02a8648'
         '86f70d010108300d06096086480165030402010500301506062b8104010b01ca0b06096086480165090401'
         '2d', 400),
    ], ids=['instance-of', 'real', 'none-subscript'])
    def test_garbled_parameters_are_passed_over(self, app, client, est_ca, caplog, value, status):
        est_ca('signing')
        cn = f'garbled-params-{abs(hash(value)) % 10**8}.keygen.test'
        cert = _client_certificate(ec.generate_private_key(ec.SECP256R1()))
        csr = _keygen_csr(cn, _ski(cert), raw_value=bytes.fromhex(value))
        with caplog.at_level('WARNING', logger='api.est_protocol'):
            r = _post_csr(client, 'serverkeygen', csr,
                          client_cert_pem=cert.public_bytes(serialization.Encoding.PEM).decode())
        assert r.status_code == status and b'Malformed' not in r.data, r.data
        assert all(rec.levelname == 'WARNING' for rec in caplog.records
                   if rec.name == 'api.est_protocol')
        if status == 400:
            assert b'supported: ' in r.data and _no_certificate_for(app, cn)


def test_an_oaep_hash_too_large_for_the_modulus_is_passed_over():
    """RFC 8017 §7.1.1: SHA-512 OAEP needs k - 130 bytes for the CEK; RSA-1024 has k = 128."""
    public_key = rsa.generate_private_key(65537, 1024).public_key()
    sha512 = ('1.2.840.113549.1.1.7', der_encoder.encode(rfc4055.rSAES_OAEP_SHA512_Params))
    sha256 = ('1.2.840.113549.1.1.7', der_encoder.encode(rfc4055.rSAES_OAEP_SHA256_Params))
    assert choose_key_encryption(public_key, [sha512, sha256]).recipient.oaep_hash == 'sha256'
    with pytest.raises(UnsupportedCapabilities):
        choose_key_encryption(public_key, [sha512])


class TestFips:
    """FIPS mode: RSAES-PKCS1-v1_5 and Brainpool key agreement are refused; OAEP with SHA-1 is
    still served, as for SCEP (Windows CNG defaults to it, SP 800-131A non-signature use)."""

    @pytest.fixture
    def fips_on(self, monkeypatch):
        monkeypatch.setattr(fips_mode, 'enabled', lambda: True)

    @pytest.mark.parametrize('capabilities', [
        [RSA_ENCRYPTION], [RSA_ENCRYPTION, AES128_CBC],
    ], ids=['pkcs1v15', 'pkcs1v15-aes128'])
    def test_pkcs1v15_is_refused(self, fips_on, capabilities):
        public_key = rsa.generate_private_key(65537, 2048).public_key()
        caps = smime_capabilities(_keygen_csr('fips.keygen.test', b'\x01', capabilities)
                                  .public_bytes(serialization.Encoding.DER))
        with pytest.raises(UnsupportedCapabilities) as refused:
            choose_key_encryption(public_key, caps)
        assert 'PKCS1' not in str(refused.value) and 'RSAES-OAEP' in str(refused.value)

    @pytest.mark.parametrize('capabilities', [
        [OAEP_DEFAULT], [RSA_ENCRYPTION, OAEP_DEFAULT],
    ], ids=['oaep-sha1', 'pkcs1v15-then-oaep-sha1'])
    def test_sha1_oaep_is_served(self, fips_on, capabilities):
        public_key = rsa.generate_private_key(65537, 2048).public_key()
        caps = smime_capabilities(_keygen_csr('fips.keygen.test', b'\x01', capabilities)
                                  .public_bytes(serialization.Encoding.DER))
        chosen = choose_key_encryption(public_key, caps)
        assert (chosen.recipient.oaep_hash, chosen.recipient.mgf_hash) == ('sha1', 'sha1')

    def test_the_client_order_holds_among_oaep_hashes(self, fips_on):
        public_key = rsa.generate_private_key(65537, 2048).public_key()
        chosen = choose_key_encryption(public_key, [
            ('1.2.840.113549.1.1.1', b'\x05\x00'), ('1.2.840.113549.1.1.7', b'\x30\x00'),
            ('1.2.840.113549.1.1.7', der_encoder.encode(rfc4055.rSAES_OAEP_SHA256_Params))])
        assert chosen.recipient.oaep_hash == 'sha1'

    def test_the_route_refuses_pkcs1v15_before_issuing(self, fips_on, app, client, est_ca):
        est_ca('signing')
        cn = 'fips-v15.keygen.test'
        r = _serverkeygen(client, _client_certificate(rsa.generate_private_key(65537, 2048)), cn,
                          [RSA_ENCRYPTION])
        assert r.status_code == 400 and b'RSAES-OAEP' in r.data and b'PKCS1' not in r.data, r.data
        assert _no_certificate_for(app, cn)

    def test_the_route_serves_sha1_oaep(self, fips_on, client, est_ca):
        est_ca('signing')
        key = rsa.generate_private_key(65537, 2048)
        cert = _client_certificate(key)
        parts = _assert_ok(_serverkeygen(client, cert, 'fips-sha1.keygen.test', [OAEP_DEFAULT]))
        enveloped = _enveloped(parts)
        transport, cek = _ktri_cek(enveloped, cert, key)
        assert transport == ('oaep', 'sha1', 'sha1')
        _content(enveloped, cek)

    def test_a_brainpool_client_key_is_refused(self, fips_on, app, client, est_ca):
        est_ca('signing')
        cn = 'fips-brainpool.keygen.test'
        r = _serverkeygen(client, _client_certificate(ec.generate_private_key(ec.BrainpoolP256R1())),
                          cn)
        assert r.status_code == 400 and b'FIPS' in r.data, r.data
        assert _no_certificate_for(app, cn)
