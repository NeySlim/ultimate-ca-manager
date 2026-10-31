"""SCEP and ML-DSA: an ML-DSA CA is refused everywhere SCEP picks a CA, while an
ML-DSA client (CSR and self-signed signer, RFC 9882 SignerInfo) enrolls under an RSA CA."""
import json
from datetime import datetime, timedelta, timezone

import asn1crypto.cms
import asn1crypto.core
import asn1crypto.x509
import pytest
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed448, mldsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import AttributeOID, NameOID

from models import CA, SystemConfig, db
from services.scep.crypto_helpers import create_signed_pkcs7, encrypt_for_client
from services.scep.message_parser import extract_signer_certificate, verify_cms_signature
from services.scep.scep_service import SCEPService
from tests.pqc_fixtures import fixture_bytes, load_mldsa_key
from tests.test_scep_rfc8894_operations import (
    MESSAGE_TYPE_OID, PKI_STATUS_OID, SENDER_NONCE_OID, TRANSACTION_ID_OID,
    _decrypt_password_response, _load_ca_material, _response_attributes,
)
from utils import key_algorithms

pytestmark = pytest.mark.skipif(not key_algorithms.mldsa_supported(),
                                reason='this build has no ML-DSA')

CHALLENGE = 'pq challenge for scep'


def _self_signed(key, cn='SCEP ML-DSA client'):
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.now(timezone.utc)
    return (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
            .sign(key, None))


def _signer_oid(key):
    return next(a.oid for a in key_algorithms.algorithms('ML-DSA') if a.matches_key(key))


def scep_pq_signed_cms(data, key, cert, attrs, digest='sha512'):
    """CMS SignedData signed the RFC 9882 way: SHA-512 messageDigest, pure ML-DSA over
    the DER SignedAttrs, the key's OID as signatureAlgorithm with no parameters."""
    h = hashes.Hash(hashes.SHA512() if digest == 'sha512' else hashes.SHA256())
    h.update(data)
    signed_attrs = asn1crypto.cms.CMSAttributes([
        *attrs,
        {'type': 'content_type', 'values': ['data']},
        {'type': 'message_digest', 'values': [asn1crypto.core.OctetString(h.finalize())]},
    ])
    signature = key.sign(b'\x31' + signed_attrs.dump()[1:])
    cert_asn1 = asn1crypto.x509.Certificate.load(cert.public_bytes(serialization.Encoding.DER))
    signer_info = asn1crypto.cms.SignerInfo({
        'version': 'v1',
        'sid': {'issuer_and_serial_number': {'issuer': cert_asn1.issuer,
                                             'serial_number': cert_asn1.serial_number}},
        'digest_algorithm': {'algorithm': digest},
        'signed_attrs': signed_attrs,
        'signature_algorithm': {'algorithm': _signer_oid(key)},
        'signature': asn1crypto.core.OctetString(signature),
    })
    return asn1crypto.cms.ContentInfo({'content_type': 'signed_data', 'content': {
        'version': 'v1', 'digest_algorithms': [{'algorithm': digest}],
        'encap_content_info': {'content_type': 'data',
                               'content': asn1crypto.core.OctetString(data)},
        'certificates': [cert_asn1], 'signer_infos': [signer_info],
    }}).dump()


def _signed_data(der):
    return asn1crypto.cms.ContentInfo.load(der)['content']


def _scep_attrs(message_type, nonce):
    attrs = [
        {'type': TRANSACTION_ID_OID, 'values': [asn1crypto.core.PrintableString('txn-pq')]},
        {'type': MESSAGE_TYPE_OID, 'values': [asn1crypto.core.PrintableString(str(message_type))]},
    ]
    if nonce is not None:
        attrs.append({'type': SENDER_NONCE_OID, 'values': [asn1crypto.core.OctetString(nonce)]})
    return attrs


class TestRfc9882SignerInfo:
    def test_openssl_mldsa_cms_verifies(self):
        sd = _signed_data(fixture_bytes('mldsa65-signed.cms'))
        signer = extract_signer_certificate(sd)
        assert isinstance(signer.public_key(), mldsa.MLDSA65PublicKey)
        verify_cms_signature(sd, signer)

    def test_tampered_content_is_refused(self):
        sd = _signed_data(fixture_bytes('mldsa65-signed.cms'))
        signer = extract_signer_certificate(sd)
        sd['encap_content_info']['content'] = asn1crypto.core.OctetString(b'other content')
        with pytest.raises(InvalidSignature):
            verify_cms_signature(sd, signer)

    def test_bare_public_key_is_accepted(self):
        key = load_mldsa_key()
        cert = _self_signed(key)
        sd = _signed_data(scep_pq_signed_cms(b'payload', key, cert, []))
        verify_cms_signature(sd, key.public_key())

    @pytest.mark.parametrize('param', ['44', '87'])
    def test_every_parameter_set_verifies(self, param):
        key = key_algorithms.generate(f'ML-DSA-{param}')
        cert = _self_signed(key)
        verify_cms_signature(_signed_data(scep_pq_signed_cms(b'payload', key, cert, [])), cert)

    def test_digest_other_than_sha512_is_refused(self):
        key = load_mldsa_key()
        cert = _self_signed(key)
        sd = _signed_data(scep_pq_signed_cms(b'payload', key, cert, [], digest='sha256'))
        with pytest.raises(ValueError, match='ML-DSA'):
            verify_cms_signature(sd, cert)

    def test_oid_of_another_parameter_set_is_refused(self):
        key = load_mldsa_key()
        cert = _self_signed(key)
        sd = _signed_data(scep_pq_signed_cms(b'payload', key, cert, []))
        sd['signer_infos'][0]['signature_algorithm'] = {'algorithm': key_algorithms.get('ML-DSA-44').oid}
        with pytest.raises(ValueError, match='ML-DSA'):
            verify_cms_signature(sd, cert)

    def test_signature_parameters_are_refused(self):
        sd = _signed_data(fixture_bytes('mldsa65-signed.cms'))
        signer = extract_signer_certificate(sd)
        alg = sd['signer_infos'][0]['signature_algorithm']
        sd['signer_infos'][0]['signature_algorithm'] = {
            'algorithm': alg['algorithm'].dotted, 'parameters': asn1crypto.core.Null()}
        with pytest.raises(ValueError, match='parameters'):
            verify_cms_signature(sd, signer)

    def test_forged_signature_is_refused(self):
        sd = _signed_data(fixture_bytes('mldsa65-signed.cms'))
        signer = extract_signer_certificate(sd)
        sig = bytearray(sd['signer_infos'][0]['signature'].native)
        sig[10] ^= 0xFF
        sd['signer_infos'][0]['signature'] = asn1crypto.core.OctetString(bytes(sig))
        with pytest.raises(InvalidSignature):
            verify_cms_signature(sd, signer)

    def test_ed448_signer_is_refused_by_name(self):
        sd = _signed_data(fixture_bytes('mldsa65-signed.cms'))
        with pytest.raises(ValueError, match='Ed448'):
            verify_cms_signature(sd, ed448.Ed448PrivateKey.generate().public_key())


def test_reply_signer_names_an_unsupported_key():
    """CertRep is signed by the RSA CA; any other signer is named in the refusal."""
    key = load_mldsa_key()
    with pytest.raises(ValueError, match='ML-DSA-65'):
        create_signed_pkcs7(b'x', key, _self_signed(key))


class TestMldsaClientEnrollment:
    def _enroll(self, app, create_ca, csr_key, signer_key, signer_cert=None):
        ca_data = create_ca(cn='SCEP RSA CA for ML-DSA client')
        signer_cert = signer_cert or _self_signed(signer_key)
        csr = (x509.CertificateSigningRequestBuilder()
               .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'pq-scep.example')]))
               .add_attribute(AttributeOID.CHALLENGE_PASSWORD, CHALLENGE.encode())
               .sign(csr_key, None))
        with app.app_context():
            ca, ca_cert, _ = _load_ca_material(ca_data['id'])
            envelope = encrypt_for_client(csr.public_bytes(serialization.Encoding.DER), ca_cert)
            request = scep_pq_signed_cms(envelope, signer_key, signer_cert,
                                         _scep_attrs(19, b'pq-scep-nonce-01'))
            response, status = SCEPService(ca.refid, challenge_password=CHALLENGE,
                                           auto_approve=True).process_pkcs_req(request, '127.0.0.1')
        return response, status, ca_cert

    def test_pkcsreq_returns_an_mldsa_leaf_signed_by_the_rsa_ca(self, app, create_ca):
        key = load_mldsa_key()
        response, status, ca_cert = self._enroll(app, create_ca, key, key)
        attrs = _response_attributes(response)
        assert status == 200
        assert attrs[PKI_STATUS_OID] == '0', attrs
        # CertRep signed by the RSA CA, verified as a client would
        reply = _signed_data(response)
        assert reply['signer_infos'][0]['signature_algorithm']['algorithm'].native == 'rsassa_pkcs1v15'
        verify_cms_signature(reply, ca_cert)
        plaintext, recipient_info, _ = _decrypt_password_response(response, CHALLENGE)
        assert recipient_info.name == 'pwri'     # an ML-DSA key cannot receive a key transport
        (leaf,) = pkcs7.load_der_pkcs7_certificates(plaintext)
        assert isinstance(leaf.public_key(), mldsa.MLDSA65PublicKey)
        assert leaf.public_key() == key.public_key()
        leaf.verify_directly_issued_by(ca_cert)

    def test_signature_by_another_key_is_bad_message_check(self, app, create_ca):
        key = load_mldsa_key()
        intruder = key_algorithms.generate('ML-DSA-65')
        response, status, _ = self._enroll(app, create_ca, key, intruder,
                                           signer_cert=_self_signed(key))
        attrs = _response_attributes(response)
        assert attrs[PKI_STATUS_OID] == '2'
        assert attrs['2.16.840.1.113733.1.9.4'] == '1'   # badMessageCheck


# --- an ML-DSA CA cannot serve SCEP ---------------------------------------------------

def _set(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if row is None:
        db.session.add(SystemConfig(key=key, value=value))
    else:
        row.value = value
    db.session.commit()


@pytest.fixture
def scep_pq_ca_config(app, mldsa_ca):
    keys = ('scep_enabled', 'scep_ca_id')
    with app.app_context():
        saved = {k: getattr(SystemConfig.query.filter_by(key=k).first(), 'value', None) for k in keys}
        ca = CA.query.filter_by(refid=mldsa_ca.refid).first()
        ca_id = ca.id
        _set('scep_enabled', 'true')
    yield ca_id
    with app.app_context():
        for k, v in saved.items():
            row = SystemConfig.query.filter_by(key=k).first()
            if v is None:
                if row:
                    db.session.delete(row)
            else:
                row.value = v
        db.session.commit()


@pytest.mark.parametrize('method,operation', [
    ('get', 'GetCACaps'), ('get', 'GetCACert'), ('post', 'PKIOperation'), ('get', 'PKIOperation')])
def test_mldsa_ca_refuses_every_operation(app, client, scep_pq_ca_config, method, operation):
    with app.app_context():
        _set('scep_ca_id', str(scep_pq_ca_config))
    url = f'/scep/pkiclient.exe?operation={operation}'
    if method == 'post':
        r = client.post(url, data=b'\x30\x00', content_type='application/x-pki-message')
    else:
        r = client.get(url + ('&message=MAA=' if operation == 'PKIOperation' else ''))
    body = r.get_data(as_text=True)
    assert r.status_code == 503, body
    assert 'ML-DSA-65' in body and 'RSA' in body


def test_mldsa_ca_cannot_be_chosen_in_settings(app, auth_client, scep_pq_ca_config):
    with app.app_context():
        _set('scep_ca_id', '')
    r = auth_client.patch('/api/v2/scep/config', data=json.dumps({'ca_id': scep_pq_ca_config}),
                          content_type='application/json')
    assert r.status_code == 400
    assert 'ML-DSA-65' in r.get_data(as_text=True)


def test_dashboard_does_not_count_an_mldsa_ca_as_serving(app, auth_client, scep_pq_ca_config):
    with app.app_context():
        _set('scep_ca_id', str(scep_pq_ca_config))
    r = auth_client.get('/api/v2/dashboard/system-status')
    data = json.loads(r.data).get('data', {})
    services = data.get('services', data)
    # Profiles left by other tests may still serve; the global CA must not count
    assert not services['scep']['message'].startswith('Configured'), services['scep']

