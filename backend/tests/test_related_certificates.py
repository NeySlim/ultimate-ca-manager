"""RFC 9763: the relatedCertRequest attribute, the RelatedCertificate extension,
and the CA checks before B is issued with a link to A.

RFC 9763 publishes no test vectors (its Appendix A is the ASN.1 module), so the
encodings are checked against DER written by hand from that module."""
import base64
import json
from datetime import timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from models import CA, Certificate, db
from services.cert.related_pair import RelatedCertificateRefused, verify_request
from services.policy_service import PolicyViolation
from services.trust_store import TrustStoreService
from utils import key_algorithms, related_cert
from utils.datetime_utils import utc_now

pytestmark = pytest.mark.skipif(not key_algorithms.mldsa_supported(),
                                reason='this build has no ML-DSA')

PQ_LABEL = next(label for label in key_algorithms.labels('ML-DSA') if label.endswith('65'))


@pytest.fixture(scope='module', autouse=True)
def _certificates_made_here_go(app):
    """A sequential run shares one database, and listings read one page: the
    certificates made here are deleted when the module ends."""
    with app.app_context():
        first = db.session.query(db.func.max(Certificate.id)).scalar() or 0
    yield
    from services.cert_service import CertificateService
    with app.app_context():
        for row_id in [r.id for r in Certificate.query.filter(Certificate.id > first).all()]:
            CertificateService.delete_certificate(row_id, username='test')


# ---- encodings ----------------------------------------------------------------

NAME_CN_A = bytes.fromhex('300c310a300806035504030c0161')        # CN=a, UTF8String
IAS = bytes.fromhex('3012') + NAME_CN_A + bytes.fromhex('02020102')  # serial 0x0102
BINARY_TIME = bytes.fromhex('02046553f100')                      # 1700000000
URI = bytes.fromhex('1603753a78')                                # IA5String 'u:x'
SIGNATURE = bytes.fromhex('0303000102')                          # BIT STRING 0x0102


def _vector_request(location=URI):
    body = IAS + BINARY_TIME + location + SIGNATURE
    return bytes([0x30, len(body)]) + body


def test_requester_certificate_encodes_as_the_asn1_module():
    from asn1crypto import x509 as asn1_x509
    built = related_cert.RequesterCertificate({
        'cert_id': {'issuer': asn1_x509.Name.load(NAME_CN_A), 'serial_number': 0x0102},
        'request_time': 1700000000,
        'location_info': related_cert.LocationInfo(name='uri', value='u:x'),
        'signature': b'\x01\x02',
    }).dump()
    assert built == _vector_request()
    parsed = related_cert.parse_request(built)
    assert related_cert.requested_serial(parsed) == 0x0102
    assert related_cert.requested_issuer_der(parsed) == NAME_CN_A
    # What the requester signs: DER(IssuerAndSerialNumber) || DER(BinaryTime)
    assert related_cert.signed_content(parsed['cert_id'], 1700000000) == IAS + BINARY_TIME


def test_location_info_as_a_sequence_of_uri_is_read_too():
    # The ASN.1 module first printed SEQUENCE OF URI (erratum 8750 made it one IA5String)
    parsed = related_cert.parse_request(_vector_request(bytes.fromhex('3005') + URI))
    assert parsed['location_info'].native == ['u:x']


def test_a_request_that_is_not_der_is_refused():
    der = _vector_request()
    ber = bytes([0x30, 0x81, der[1]]) + der[2:]  # long-form length
    with pytest.raises(related_cert.RelatedCertError):
        related_cert.parse_request(ber)


def _self_signed(key, algorithm, serial=7):
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'a')])
    now = utc_now()
    return (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(serial)
            .not_valid_before(now).not_valid_after(now + timedelta(days=1)).sign(key, algorithm))


@pytest.mark.parametrize('algorithm,oid_hex', [
    (hashes.SHA384(), '0609608648016503040202'),
    (hashes.SHA256(), '0609608648016503040201'),
])
def test_related_certificate_extension_hashes_a_with_its_signature_digest(algorithm, oid_hex):
    import hashlib
    cert_a = _self_signed(ec.generate_private_key(ec.SECP384R1()), algorithm)
    digest = hashlib.new(algorithm.name, cert_a.public_bytes(serialization.Encoding.DER)).digest()
    alg_id = bytes.fromhex('300b' + oid_hex)  # parameters absent (RFC 5754 §2)
    body = alg_id + bytes([0x04, len(digest)]) + digest
    ext = related_cert.related_certificate_extension(cert_a)
    assert ext.oid.dotted_string == '1.3.6.1.5.5.7.1.36'
    assert ext.value == bytes([0x30, len(body)]) + body


def test_a_request_signed_by_a_verifies_and_one_signed_by_another_key_does_not():
    key_a = ec.generate_private_key(ec.SECP256R1())
    cert_a = _self_signed(key_a, hashes.SHA256())
    good = related_cert.parse_request(related_cert.build_request(cert_a, key_a, 'u:x'))
    assert related_cert.request_signature_valid(good, cert_a.public_key())
    forged = related_cert.parse_request(
        related_cert.build_request(cert_a, ec.generate_private_key(ec.SECP256R1()), 'u:x'))
    assert not related_cert.request_signature_valid(forged, cert_a.public_key())


# ---- the CA side ----------------------------------------------------------------

@pytest.fixture
def cert_a(app, create_cert):
    """An EC end-entity certificate A whose key the server holds: ``(row id, certificate, key)``."""
    data = create_cert(key_type='ec', key_size='256', cert_type='server')
    with app.app_context():
        row = db.session.get(Certificate, data['id'])
        cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
        from utils.key_codec import load_pem_bytes
        key = serialization.load_pem_private_key(load_pem_bytes(row.prv, context='test'), None)
        return row.id, cert, key


def _signing_ca(row_id):
    row = db.session.get(Certificate, row_id)
    ca = CA.query.filter_by(refid=row.caref).first()
    from services.hsm.ca_key_loader import get_ca_signing_key
    return ca, x509.load_pem_x509_certificate(base64.b64decode(ca.crt)), get_ca_signing_key(ca)


def _csr_b(cert_a, signer_key, request_time=None):
    key_b = key_algorithms.generate(PQ_LABEL)
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(cert_a.subject)
           .add_extension(cert_a.extensions.get_extension_for_class(x509.SubjectAlternativeName).value,
                          critical=False)
           .sign(key_b, None))
    request = related_cert.build_request(cert_a, signer_key, related_cert.data_url_for([cert_a]),
                                         request_time=request_time)
    return related_cert.csr_with_request(csr, key_b, request).public_bytes(serialization.Encoding.PEM)


def _sign(row_id, csr_pem, **kwargs):
    ca, ca_cert, ca_key = _signing_ca(row_id)
    return x509.load_pem_x509_certificate(TrustStoreService.sign_csr(
        csr_pem, ca_cert, ca_key, policy_scope={'ca_id': ca.id, 'template_id': None}, **kwargs))


def test_b_names_a_in_a_non_critical_extension(app, cert_a):
    row_id, cert, key = cert_a
    with app.app_context():
        cert_b = _sign(row_id, _csr_b(cert, key))
    ext = cert_b.extensions.get_extension_for_oid(related_cert.RELATED_CERT_EXTENSION_OID)
    assert ext.critical is False
    assert related_cert.references(cert_b, cert)
    assert key_algorithms.label_for_public_key(cert_b.public_key()) == PQ_LABEL


def test_an_attribute_signed_by_another_key_is_refused(app, cert_a):
    row_id, cert, _key = cert_a
    with app.app_context():
        with pytest.raises(RelatedCertificateRefused, match='signature does not verify'):
            _sign(row_id, _csr_b(cert, ec.generate_private_key(ec.SECP256R1())))


def test_a_revoked_a_is_refused(app, auth_client, cert_a):
    row_id, cert, key = cert_a
    csr_pem = _csr_b(cert, key)
    r = auth_client.post(f'/api/v2/certificates/{row_id}/revoke', json={'reason': 'superseded'})
    assert r.status_code == 200, r.data
    with app.app_context():
        with pytest.raises(RelatedCertificateRefused, match='revoked'):
            _sign(row_id, csr_pem)


def test_an_expired_a_is_refused(app, cert_a):
    row_id, cert, key = cert_a
    later = utc_now() + timedelta(days=4000)
    req = related_cert.parse_request(related_cert.build_request(cert, key, 'u:x', request_time=later))
    with app.app_context():
        with pytest.raises(RelatedCertificateRefused, match='expired'):
            verify_request(req, now=later)


@pytest.mark.parametrize('offset,message', [(timedelta(days=-8), 'too old'),
                                            (timedelta(hours=1), 'in the future')])
def test_a_request_out_of_its_time_window_is_refused(app, cert_a, offset, message):
    row_id, cert, key = cert_a
    with app.app_context():
        with pytest.raises(RelatedCertificateRefused, match=message):
            _sign(row_id, _csr_b(cert, key, request_time=utc_now() + offset))


def test_b_may_not_assert_an_eku_a_lacks(app, cert_a):
    row_id, cert, key = cert_a
    with app.app_context():
        with pytest.raises(RelatedCertificateRefused, match='1.3.6.1.5.5.7.3.3'):
            _sign(row_id, _csr_b(cert, key), extra_ekus=['codeSigning'])


def test_a_ca_request_may_not_name_a_related_certificate(app, cert_a):
    row_id, cert, key = cert_a
    with app.app_context():
        with pytest.raises(RelatedCertificateRefused, match='end-entity'):
            _sign(row_id, _csr_b(cert, key), cert_type='intermediate_ca')


def test_pkilint_finds_nothing_wrong_with_the_extension(app, cert_a):
    from services.cert_linting_service import lint_certificate_pem
    row_id, cert, key = cert_a
    with app.app_context():
        cert_b = _sign(row_id, _csr_b(cert, key))
    result = lint_certificate_pem(cert_b.public_bytes(serialization.Encoding.PEM).decode())
    if not result['available']:
        pytest.skip('pkilint is not installed')
    codes = [f['code'] for f in result['findings']]
    assert not [c for c in codes if 'unknown' in c or 'critical' in c], codes


def test_the_pair_lifts_the_rule_that_refuses_ml_dsa_alone(app, cert_a):
    row_id, cert, key = cert_a
    with app.app_context():
        ca, _ca_cert, _ca_key = _signing_ca(row_id)
        previous, ca.compliance_profile = ca.compliance_profile, 'anssi'
        db.session.commit()
        try:
            alone = key_algorithms.generate(PQ_LABEL)
            plain = (x509.CertificateSigningRequestBuilder().subject_name(cert.subject)
                     .sign(alone, None).public_bytes(serialization.Encoding.PEM))
            with pytest.raises(PolicyViolation, match='alone'):
                _sign(row_id, plain)
            assert related_cert.references(_sign(row_id, _csr_b(cert, key)), cert)
        finally:
            ca = db.session.get(CA, ca.id)
            ca.compliance_profile = previous
            db.session.commit()


# ---- generate_csr(related_to=) and the Sign CSR route ------------------------------

def _generate_b(app, row_id):
    from services.cert_service import CertificateService
    with app.app_context():
        cn = db.session.get(Certificate, row_id).common_name
        return CertificateService.generate_csr(
            descr=f'pq of {row_id}', dn={'CN': cn}, key_type=PQ_LABEL.lower(),
            san_dns=[cn], related_to=row_id).id


def test_generate_csr_signs_the_attribute_with_the_stored_key_of_a(app, auth_client, cert_a):
    row_id, cert, _key = cert_a
    csr_id = _generate_b(app, row_id)
    with app.app_context():
        ca, _c, _k = _signing_ca(row_id)
        csr_row = db.session.get(Certificate, csr_id)
        csr = x509.load_pem_x509_csr(base64.b64decode(csr_row.csr))
        req = related_cert.request_from_csr_der(csr.public_bytes(serialization.Encoding.DER))
        assert related_cert.requested_serial(req) == cert.serial_number
        assert related_cert.request_signature_valid(req, cert.public_key())
        ca_id = ca.id
    r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign', json={'ca_id': ca_id, 'validity_days': 30})
    assert r.status_code == 200, r.data
    signed = json.loads(r.data)['data']
    assert signed['related_certificate_id'] == row_id
    assert signed['hybrid_role'] == 'pq'
    with app.app_context():
        a_row = db.session.get(Certificate, row_id)
        assert (a_row.related_certificate_id, a_row.hybrid_role) == (signed['id'], 'classical')


def _sign_b(app, auth_client, row_id):
    csr_id = _generate_b(app, row_id)
    with app.app_context():
        ca_id = _signing_ca(row_id)[0].id
    r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign', json={'ca_id': ca_id, 'validity_days': 30})
    assert r.status_code == 200, r.data
    return json.loads(r.data)['data']['id']


def test_revoking_the_partner_alone_hands_the_link_to_the_newer_b(app, auth_client, cert_a):
    """What an ACME re-enrolment does: B2 names A, then the superseded B1 is revoked alone."""
    from services.cert.related_pair import mutual_partner
    row_id = cert_a[0]
    b1, b2 = _sign_b(app, auth_client, row_id), _sign_b(app, auth_client, row_id)
    with app.app_context():
        assert db.session.get(Certificate, row_id).related_certificate_id == b1
    r = auth_client.post(f'/api/v2/certificates/{b1}/revoke',
                         json={'reason': 'superseded', 'revoke_related': False})
    assert r.status_code == 200, r.data
    with app.app_context():
        assert mutual_partner(db.session.get(Certificate, row_id)).id == b2
    r = auth_client.post(f'/api/v2/certificates/{row_id}/revoke', json={'reason': 'keyCompromise'})
    assert json.loads(r.data)['data']['related_revoked'] == b2, r.data


def test_revoking_a_alone_moves_no_link(app, auth_client, cert_a):
    row_id = cert_a[0]
    b1, b2 = _sign_b(app, auth_client, row_id), _sign_b(app, auth_client, row_id)
    r = auth_client.post(f'/api/v2/certificates/{row_id}/revoke',
                         json={'reason': 'superseded', 'revoke_related': False})
    assert r.status_code == 200, r.data
    with app.app_context():
        assert db.session.get(Certificate, row_id).related_certificate_id == b1
        assert db.session.get(Certificate, b2).related_certificate_id == row_id


def test_the_sign_route_answers_400_when_a_was_revoked_meanwhile(app, auth_client, cert_a):
    row_id, _cert, _key = cert_a
    csr_id = _generate_b(app, row_id)
    with app.app_context():
        ca_id = _signing_ca(row_id)[0].id
    r = auth_client.post(f'/api/v2/certificates/{row_id}/revoke', json={'reason': 'superseded'})
    assert r.status_code == 200, r.data
    r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign', json={'ca_id': ca_id, 'validity_days': 30})
    assert r.status_code == 400, r.data
    assert 'related certificate is revoked' in json.loads(r.data)['message']


# ---- locationInfo (RFC 9763 §3.2) -------------------------------------------------

def _csr_b_located(cert_a, signer_key, location):
    key_b = key_algorithms.generate(PQ_LABEL)
    csr = x509.CertificateSigningRequestBuilder().subject_name(cert_a.subject).sign(key_b, None)
    request = related_cert.build_request(cert_a, signer_key, location)
    return related_cert.csr_with_request(csr, key_b, request).public_bytes(serialization.Encoding.PEM)


def test_a_data_url_naming_another_certificate_is_refused(app, cert_a, create_cert):
    row_id, cert, key = cert_a
    with app.app_context():
        other = x509.load_pem_x509_certificate(base64.b64decode(
            db.session.get(Certificate, create_cert(cn='not-a.example.com')['id']).crt))
        with pytest.raises(RelatedCertificateRefused, match='locationInfo is not the related'):
            _sign(row_id, _csr_b_located(cert, key, related_cert.data_url_for([other])))


@pytest.mark.parametrize('location', ['data:application/pkcs7-mime;base64,!!!',
                                      'data:application/pkix-cert;base64,AAAA', 'data:nocomma'])
def test_an_unreadable_data_url_is_refused(app, cert_a, location):
    row_id, cert, key = cert_a
    with app.app_context():
        with pytest.raises(RelatedCertificateRefused, match='locationInfo'):
            _sign(row_id, _csr_b_located(cert, key, location))


def test_a_data_url_holding_a_alone_in_der_is_accepted(app, cert_a):
    row_id, cert, key = cert_a
    location = 'data:application/pkix-cert;base64,' + base64.b64encode(
        cert.public_bytes(serialization.Encoding.DER)).decode()
    with app.app_context():
        assert related_cert.references(_sign(row_id, _csr_b_located(cert, key, location)), cert)


def test_a_data_url_holding_a_and_its_ca_is_accepted_whatever_the_order(app, create_cert):
    """The PKCS#7 certificates field is a SET OF, sorted by DER: A need not come first."""
    from utils.key_codec import load_pem_bytes
    data = create_cert(key_type='ec', key_size='256', cert_type='server',
                       san_dns=[f'host-{i}.large-a.example.com' for i in range(40)])
    with app.app_context():
        row = db.session.get(Certificate, data['id'])
        cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
        key = serialization.load_pem_private_key(load_pem_bytes(row.prv, context='test'), None)
        location = related_cert.data_url_for([cert, _signing_ca(row.id)[1]])
        assert related_cert.data_url_certificates(location)[0] != cert
        assert related_cert.references(_sign(row.id, _csr_b_located(cert, key, location)), cert)


def test_a_uri_that_is_not_a_data_url_is_not_fetched(app, cert_a, monkeypatch):
    import urllib.request
    monkeypatch.setattr(urllib.request, 'urlopen', lambda *a, **k: pytest.fail('fetched'))
    row_id, cert, key = cert_a
    with app.app_context():
        assert related_cert.references(
            _sign(row_id, _csr_b_located(cert, key, 'https://pki.example.com/a.crt')), cert)


# ---- EST and WSTEP record the pair --------------------------------------------------

def test_the_est_path_links_b_to_a(app, cert_a):
    from services.ca_service import CAService
    row_id, cert, key = cert_a
    csr = x509.load_pem_x509_csr(_csr_b(cert, key))
    with app.app_context():
        ca = _signing_ca(row_id)[0]
        pem, serial = CAService.sign_csr_from_crypto(ca, csr, validity_days=30, source='est')
        b_row = Certificate.query.filter_by(serial_number=str(int(serial, 16))).one()
        a_row = db.session.get(Certificate, row_id)
        assert (b_row.related_certificate_id, b_row.hybrid_role) == (row_id, 'pq')
        assert (a_row.related_certificate_id, a_row.hybrid_role) == (b_row.id, 'classical')

        # A re-enrolment of B (the old row superseded) moves A's link to the new B
        again, serial2 = CAService.sign_csr_from_crypto(ca, x509.load_pem_x509_csr(_csr_b(cert, key)),
                                                        validity_days=30, source='est', supersedes=b_row)
        b2 = Certificate.query.filter_by(serial_number=str(int(serial2, 16))).one()
        assert db.session.get(Certificate, row_id).related_certificate_id == b2.id


# ---- the CSR route takes related_to ------------------------------------------------

def test_the_csr_route_signs_the_attribute_with_a(app, auth_client, cert_a):
    row_id, cert, _key = cert_a
    cn = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
    r = auth_client.post('/api/v2/csrs', json={'cn': cn, 'key_type': PQ_LABEL, 'related_to': row_id})
    assert r.status_code == 201, r.data
    with app.app_context():
        csr_row = db.session.get(Certificate, json.loads(r.data)['data']['id'])
        csr = x509.load_pem_x509_csr(base64.b64decode(csr_row.csr))
        req = related_cert.request_from_csr_der(csr.public_bytes(serialization.Encoding.DER))
    assert related_cert.requested_serial(req) == cert.serial_number
    assert related_cert.request_signature_valid(req, cert.public_key())


@pytest.mark.parametrize('related_to,message', [('7', b'related_to must be'), (True, b'related_to must be'),
                                                (0, b'related_to must be'),
                                                (10 ** 9, b'Related certificate not found')])
def test_the_csr_route_refuses_a_bad_related_to(auth_client, related_to, message):
    r = auth_client.post('/api/v2/csrs', json={'cn': 'bad-related.example.com', 'key_type': 'EC P-256',
                                               'related_to': related_to})
    assert r.status_code == 400 and message in r.data, r.data
