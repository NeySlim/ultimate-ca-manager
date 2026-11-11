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
        with pytest.raises(RelatedCertificateRefused, match='signature does not verify'):
            _sign(row_id, _csr_b(cert, ec.generate_private_key(ec.SECP256R1())))


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


def test_a_newer_b_takes_a_from_the_previous_one(app, auth_client, cert_a):
    """A re-enrolment: B2 names A, so A pairs with B2 and B1 no longer revokes A."""
    from services.cert.related_pair import mutual_partner
    row_id = cert_a[0]
    b1, b2 = _sign_b(app, auth_client, row_id), _sign_b(app, auth_client, row_id)
    with app.app_context():
        assert mutual_partner(db.session.get(Certificate, row_id)).id == b2
        assert db.session.get(Certificate, b1).related_certificate_id == row_id
    r = auth_client.post(f'/api/v2/certificates/{b1}/revoke', json={'reason': 'superseded'})
    assert r.status_code == 200, r.data
    data = json.loads(r.data)['data']
    assert 'related_revoked' not in data and 'related_not_revoked' not in data, r.data
    with app.app_context():
        assert not db.session.get(Certificate, row_id).revoked
    r = auth_client.post(f'/api/v2/certificates/{row_id}/revoke', json={'reason': 'keyCompromise'})
    assert json.loads(r.data)['data']['related_revoked'] == b2, r.data
    with app.app_context():
        assert db.session.get(Certificate, b2).revoked


def test_revoking_a_takes_the_newest_b_and_leaves_the_previous_one(app, auth_client, cert_a):
    row_id = cert_a[0]
    b1, b2 = _sign_b(app, auth_client, row_id), _sign_b(app, auth_client, row_id)
    r = auth_client.post(f'/api/v2/certificates/{row_id}/revoke', json={'reason': 'superseded'})
    assert json.loads(r.data)['data']['related_revoked'] == b2, r.data
    with app.app_context():
        assert not db.session.get(Certificate, b1).revoked


def test_revoking_the_newest_b_alone_hands_the_link_to_the_previous_one(app, auth_client, cert_a):
    from services.cert.related_pair import mutual_partner
    row_id = cert_a[0]
    b1, b2 = _sign_b(app, auth_client, row_id), _sign_b(app, auth_client, row_id)
    r = auth_client.post(f'/api/v2/certificates/{b2}/revoke',
                         json={'reason': 'superseded', 'revoke_related': False})
    assert r.status_code == 200, r.data
    with app.app_context():
        assert mutual_partner(db.session.get(Certificate, row_id)).id == b1


@pytest.mark.parametrize('state', ['archived', 'expired'])
def test_a_never_returns_to_a_b_that_is_no_longer_current(app, auth_client, cert_a, state):
    row_id = cert_a[0]
    b1, b2 = _sign_b(app, auth_client, row_id), _sign_b(app, auth_client, row_id)
    with app.app_context():
        old = db.session.get(Certificate, b1)
        if state == 'archived':
            old.archived = True
        else:
            old.valid_to = utc_now() - timedelta(days=1)
        db.session.commit()
    r = auth_client.post(f'/api/v2/certificates/{b2}/revoke',
                         json={'reason': 'superseded', 'revoke_related': False})
    assert r.status_code == 200, r.data
    with app.app_context():
        assert db.session.get(Certificate, row_id).related_certificate_id == b2
    r = auth_client.delete(f'/api/v2/certificates/{b2}')
    assert r.status_code == 204, r.data
    with app.app_context():
        row = db.session.get(Certificate, row_id)
        assert (row.related_certificate_id, row.hybrid_role) == (None, None)


def test_revoking_a_alone_moves_no_link(app, auth_client, cert_a):
    row_id = cert_a[0]
    b1, b2 = _sign_b(app, auth_client, row_id), _sign_b(app, auth_client, row_id)
    r = auth_client.post(f'/api/v2/certificates/{row_id}/revoke',
                         json={'reason': 'superseded', 'revoke_related': False})
    assert r.status_code == 200, r.data
    with app.app_context():
        assert db.session.get(Certificate, row_id).related_certificate_id == b2
        assert db.session.get(Certificate, b1).related_certificate_id == row_id
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


def _csr_naming(cert_a, signer_key, key_b):
    """A CSR for *key_b* whose relatedCertRequest names *cert_a*, signed by *signer_key*."""
    digest = None if key_algorithms.is_post_quantum(
        key_algorithms.label_for_public_key(key_b.public_key())) else hashes.SHA256()
    csr = (x509.CertificateSigningRequestBuilder().subject_name(cert_a.subject)
           .add_extension(cert_a.extensions.get_extension_for_class(x509.SubjectAlternativeName).value,
                          critical=False)
           .sign(key_b, digest))
    request = related_cert.build_request(cert_a, signer_key, related_cert.data_url_for([cert_a]))
    return related_cert.csr_with_request(csr, key_b, request)


def _est_sign(ca, csr):
    from services.ca_service import CAService
    _pem, serial = CAService.sign_csr_from_crypto(ca, csr, validity_days=30, source='est')
    return Certificate.query.filter_by(serial_number=str(int(serial, 16))).one()


def test_an_a_that_is_itself_a_b_keeps_its_own_link(app, cert_a):
    """C <- A <- B: B names A, but A's single link stays on the C its certificate names."""
    c_id, cert_c, key_c = cert_a
    key_a = ec.generate_private_key(ec.SECP256R1())
    with app.app_context():
        ca = _signing_ca(c_id)[0]
        a_row = _est_sign(ca, _csr_naming(cert_c, key_c, key_a))
        a_id, cert_a2 = a_row.id, x509.load_pem_x509_certificate(base64.b64decode(a_row.crt))
        assert a_row.related_certificate_id == c_id
        b_row = _est_sign(ca, _csr_naming(cert_a2, key_a, key_algorithms.generate(PQ_LABEL)))
        assert b_row.related_certificate_id == a_id
        assert db.session.get(Certificate, a_id).related_certificate_id == c_id


# ---- a request honoured once binds to its key B -----------------------------------

P256_ORDER = 0xffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551


def _csr_with(cert_a, key_b, request, cn=None):
    """A CSR for *key_b* carrying the RequesterCertificate DER *request* as is."""
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]) if cn else cert_a.subject
    csr = (x509.CertificateSigningRequestBuilder().subject_name(subject)
           .add_extension(cert_a.extensions.get_extension_for_class(x509.SubjectAlternativeName).value,
                          critical=False)
           .sign(key_b, hashes.SHA256()))
    return related_cert.csr_with_request(csr, key_b, request)


def _request(cert_a, key_a):
    return related_cert.build_request(cert_a, key_a, related_cert.data_url_for([cert_a]))


def _bindings(request, cert_a):
    from models.related_cert_request import RelatedCertRequestUse
    from services.cert.related_pair import _request_digest
    digest = _request_digest(related_cert.parse_request(request), cert_a.public_key())
    return RelatedCertRequestUse.query.filter_by(request_sha256=digest).all()


def test_a_request_replayed_with_another_key_is_refused(app, cert_a):
    """RFC 9763's signature does not cover B's key: the CA binds the request to the first B."""
    row_id, cert, key = cert_a
    request = _request(cert, key)
    with app.app_context():
        ca = _signing_ca(row_id)[0]
        key_b = ec.generate_private_key(ec.SECP256R1())
        first = _csr_with(cert, key_b, request)
        b_id = _est_sign(ca, first).id
        # The same CSR, or another CSR for the same key B, is a retry: honoured again
        assert _est_sign(ca, first).id != b_id
        _est_sign(ca, _csr_with(cert, key_b, request, cn='retry.example.test'))
        before = Certificate.query.count()
        replayed = _csr_with(cert, ec.generate_private_key(ec.SECP256R1()), request)
        with pytest.raises(RelatedCertificateRefused, match='already used with another key'):
            _est_sign(ca, replayed)
        # Refused before anything is signed
        with pytest.raises(RelatedCertificateRefused, match='already used with another key'):
            _sign(row_id, replayed.public_bytes(serialization.Encoding.PEM))
        assert Certificate.query.count() == before
        assert len(_bindings(request, cert)) == 1


def _sign_route(auth_client, csr, ca_id):
    r = auth_client.post('/api/v2/csrs/upload', data=json.dumps(
        {'pem': csr.public_bytes(serialization.Encoding.PEM).decode(), 'name': 'related-b'}),
        content_type='application/json')
    assert r.status_code in (200, 201), r.data
    csr_id = json.loads(r.data)['data']['id']
    return auth_client.post(f'/api/v2/csrs/{csr_id}/sign', json={'ca_id': ca_id, 'validity_days': 30})


def test_the_sign_route_binds_the_request_too(app, auth_client, cert_a):
    row_id, cert, key = cert_a
    request = _request(cert, key)
    with app.app_context():
        ca_id = _signing_ca(row_id)[0].id
    r = _sign_route(auth_client, _csr_with(cert, ec.generate_private_key(ec.SECP256R1()), request), ca_id)
    assert r.status_code == 200, r.data
    with app.app_context():
        with pytest.raises(RelatedCertificateRefused, match='already used with another key'):
            _est_sign(db.session.get(CA, ca_id),
                      _csr_with(cert, ec.generate_private_key(ec.SECP256R1()), request))
    r = _sign_route(auth_client, _csr_with(cert, ec.generate_private_key(ec.SECP256R1()), request), ca_id)
    assert r.status_code == 400 and b'already used with another key' in r.data, r.data


def test_a_malleated_ecdsa_signature_names_the_same_request(app, cert_a):
    """(r, n - s) verifies as well as (r, s): the binding keys on what was signed, not on the signature."""
    from cryptography.hazmat.primitives.asymmetric.utils import (decode_dss_signature,
                                                                 encode_dss_signature)
    row_id, cert, key = cert_a
    request = _request(cert, key)
    req = related_cert.parse_request(request)
    r, s_value = decode_dss_signature(req['signature'].native)
    twin = related_cert.RequesterCertificate({
        'cert_id': req['cert_id'], 'request_time': req['request_time'].native,
        'location_info': req['location_info'],
        'signature': encode_dss_signature(r, P256_ORDER - s_value)}).dump()
    assert twin != request
    with app.app_context():
        verify_request(related_cert.parse_request(twin))
        ca = _signing_ca(row_id)[0]
        _est_sign(ca, _csr_with(cert, ec.generate_private_key(ec.SECP256R1()), request))
        with pytest.raises(RelatedCertificateRefused, match='already used with another key'):
            _est_sign(ca, _csr_with(cert, ec.generate_private_key(ec.SECP256R1()), twin))


def test_a_failed_signature_does_not_use_the_request(app, cert_a, monkeypatch):
    row_id, cert, key = cert_a
    request = _request(cert, key)
    with app.app_context():
        ca = _signing_ca(row_id)[0]

        def broken(*args, **kwargs):
            raise ValueError('signing failed')
        with monkeypatch.context() as m:
            m.setattr(x509.CertificateBuilder, 'sign', broken)
            with pytest.raises(ValueError, match='signing failed'):
                _est_sign(ca, _csr_with(cert, ec.generate_private_key(ec.SECP256R1()), request))
        db.session.commit()  # as an audit row written after the failure would
        assert _bindings(request, cert) == []
        _est_sign(ca, _csr_with(cert, ec.generate_private_key(ec.SECP256R1()), request))
        assert len(_bindings(request, cert)) == 1


def test_two_concurrent_keys_meet_the_unique_binding(app, cert_a, monkeypatch):
    """Both requests passed the check before either committed: the second insert loses."""
    from models.related_cert_request import RelatedCertRequestUse
    from services.cert import related_pair
    row_id, cert, key = cert_a
    request = _request(cert, key)
    req = related_cert.parse_request(request)
    with app.app_context():
        ca = _signing_ca(row_id)[0]
        link = db.session.get(Certificate, row_id).related_certificate_id
        db.session.add(RelatedCertRequestUse(request_sha256=related_pair._request_digest(req, cert.public_key()),
                                             spki_sha256='0' * 64,
                                             request_time=related_cert.request_time(req)))
        db.session.commit()
        real = related_pair._bound_key
        calls = []

        def unseen_once(digest):
            calls.append(digest)
            return None if len(calls) == 1 else real(digest)
        monkeypatch.setattr(related_pair, 'check_request_key', lambda *a: None)
        monkeypatch.setattr(related_pair, '_bound_key', unseen_once)
        before = Certificate.query.count()
        with pytest.raises(RelatedCertificateRefused, match='already used with another key'):
            _est_sign(ca, _csr_with(cert, ec.generate_private_key(ec.SECP256R1()), request))
        assert len(calls) == 2
        assert Certificate.query.count() == before
        assert db.session.get(Certificate, row_id).related_certificate_id == link
        assert [b.spki_sha256 for b in _bindings(request, cert)] == ['0' * 64]


def test_bindings_older_than_a_request_may_be_go(app, cert_a):
    from models.related_cert_request import RelatedCertRequestUse
    from services.cert.related_pair import REQUEST_MAX_AGE
    row_id, cert, key = cert_a
    stale = utc_now() - REQUEST_MAX_AGE - timedelta(minutes=1)
    with app.app_context():
        db.session.add(RelatedCertRequestUse(request_sha256='f' * 64, spki_sha256='0' * 64,
                                             request_time=stale))
        db.session.add(RelatedCertRequestUse(request_sha256='e' * 64, spki_sha256='0' * 64,
                                             request_time=stale + timedelta(minutes=2)))
        db.session.commit()
        _est_sign(_signing_ca(row_id)[0], _csr_with(cert, ec.generate_private_key(ec.SECP256R1()),
                                                    _request(cert, key)))
        left = {b.request_sha256 for b in RelatedCertRequestUse.query.all()}
        assert 'f' * 64 not in left and 'e' * 64 in left


# ---- a B enrolled by a device: A renews alone ---------------------------------------

def _renew(auth_client, row_id, how):
    if how == 'bulk':
        r = auth_client.post('/api/v2/certificates/bulk/renew', json={'ids': [row_id]})
        assert r.status_code == 200, r.data
        assert json.loads(r.data)['data']['failed'] == [], r.data
        return
    r = auth_client.post(f'/api/v2/certificates/{row_id}/renew', json={})
    assert r.status_code == 200, r.data
    assert 'related_renewed' not in json.loads(r.data)['data'], r.data


def _links(*ids):
    db.session.expire_all()
    return [(db.session.get(Certificate, i).related_certificate_id,
             db.session.get(Certificate, i).hybrid_role) for i in ids]


@pytest.mark.parametrize('how', ['single', 'bulk'])
def test_a_renews_alone_when_its_b_was_enrolled_by_a_device(app, auth_client, cert_a, how):
    row_id, cert, key = cert_a
    with app.app_context():
        b_row = _est_sign(_signing_ca(row_id)[0], _csr_naming(cert, key, key_algorithms.generate(PQ_LABEL)))
        b_id, b_serial = b_row.id, b_row.serial_number
        assert not b_row.prv and _links(row_id) == [(b_id, 'classical')]
    _renew(auth_client, row_id, how)
    with app.app_context():
        a_row, b_row = db.session.get(Certificate, row_id), db.session.get(Certificate, b_id)
        assert a_row.renewed_times == 1 and b_row.serial_number == b_serial and not b_row.revoked
        # B names the A that was replaced: neither row is left pointing at the other
        assert _links(row_id, b_id) == [(None, None), (None, None)]


def test_a_form_pair_renews_a_alone_once_a_device_enrols_a_newer_b(app, auth_client, create_ca):
    from utils.key_codec import load_pem_bytes
    ca = create_ca(cn='Device B CA')
    r = auth_client.post('/api/v2/certificates', json={
        'cn': 'device-b.example.com', 'ca_id': ca['id'], 'validity_days': 90,
        'hybrid': {'classical': next(l for l in key_algorithms.labels('EC') if l.endswith('P256')),
                   'pq': PQ_LABEL}})
    assert r.status_code == 201, r.data
    a_id, form_id = (json.loads(r.data)['data'][k]['id'] for k in ('certificate', 'related'))
    with app.app_context():
        a_row = db.session.get(Certificate, a_id)
        cert = x509.load_pem_x509_certificate(base64.b64decode(a_row.crt))
        key = serialization.load_pem_private_key(load_pem_bytes(a_row.prv, context='test'), None)
        b2_id = _est_sign(_signing_ca(a_id)[0],
                          _csr_naming(cert, key, key_algorithms.generate(PQ_LABEL))).id
        assert _links(a_id)[0][0] == b2_id
    _renew(auth_client, a_id, 'single')
    with app.app_context():
        assert [db.session.get(Certificate, i).renewed_times or 0 for i in (a_id, form_id, b2_id)] == [1, 0, 0]
        assert _links(a_id, form_id, b2_id) == [(None, None)] * 3


@pytest.mark.parametrize('archived', ['related', 'certificate'])
def test_an_archived_partner_is_not_renewed_with_the_live_member(app, auth_client, create_ca, archived):
    ca = create_ca(cn=f'Archived partner CA {archived}')
    r = auth_client.post('/api/v2/certificates', json={
        'cn': f'archived-{archived}.example.com', 'ca_id': ca['id'], 'validity_days': 90,
        'hybrid': {'classical': next(l for l in key_algorithms.labels('EC') if l.endswith('P256')),
                   'pq': PQ_LABEL}})
    assert r.status_code == 201, r.data
    a_id, b_id = (json.loads(r.data)['data'][k]['id'] for k in ('certificate', 'related'))
    gone, live = (b_id, a_id) if archived == 'related' else (a_id, b_id)
    with app.app_context():
        row = db.session.get(Certificate, gone)
        row.archived, gone_serial = True, row.serial_number
        db.session.commit()
    _renew(auth_client, live, 'single')
    with app.app_context():
        row = db.session.get(Certificate, gone)
        assert (db.session.get(Certificate, live).renewed_times, row.renewed_times or 0,
                row.serial_number) == (1, 0, gone_serial)


@pytest.mark.parametrize('path', ['est', 'sign_route'])
def test_b_is_stored_and_linked_when_a_changes_after_signing(app, auth_client, cert_a, monkeypatch, path):
    """A is found before signing: a lookup after it could lose a signed certificate."""
    row_id, cert, key = cert_a
    real_sign = TrustStoreService.sign_csr

    def sign_then_move_a(*args, **kwargs):
        pem = real_sign(*args, **kwargs)
        db.session.get(Certificate, row_id).serial_number = '0'  # A no longer found by serial
        return pem

    monkeypatch.setattr(TrustStoreService, 'sign_csr', staticmethod(sign_then_move_a))
    try:
        if path == 'est':
            with app.app_context():
                b_id = _est_sign(_signing_ca(row_id)[0], x509.load_pem_x509_csr(_csr_b(cert, key))).id
        else:
            b_id = _sign_b(app, auth_client, row_id)
        with app.app_context():
            assert db.session.get(Certificate, b_id).related_certificate_id == row_id
            assert db.session.get(Certificate, row_id).related_certificate_id == b_id
    finally:
        monkeypatch.undo()
        with app.app_context():
            db.session.get(Certificate, row_id).serial_number = str(cert.serial_number)
            db.session.commit()


@pytest.mark.parametrize('path', ['est', 'sign_route'])
def test_no_link_is_written_onto_an_a_renewed_after_signing(app, auth_client, cert_a, monkeypatch, path):
    """B's extension hashes the A it was signed against: an A renewed in place meanwhile
    holds another certificate, so the linked issuance is refused rather than linked wrong."""
    row_id, cert, key = cert_a
    real_sign = TrustStoreService.sign_csr
    other_key = ec.generate_private_key(ec.SECP256R1())
    other = _self_signed(other_key, hashes.SHA256(), serial=cert.serial_number + 1)
    csr_id = _generate_b(app, row_id) if path == 'sign_route' else None

    def sign_then_renew_a(*args, **kwargs):
        pem = real_sign(*args, **kwargs)
        a_row = db.session.get(Certificate, row_id)
        a_row.crt = base64.b64encode(other.public_bytes(serialization.Encoding.PEM)).decode()
        a_row.serial_number = str(other.serial_number)
        return pem

    monkeypatch.setattr(TrustStoreService, 'sign_csr', staticmethod(sign_then_renew_a))
    try:
        if path == 'est':
            with app.app_context():
                with pytest.raises(RelatedCertificateRefused, match='not held by this instance'):
                    _est_sign(_signing_ca(row_id)[0], x509.load_pem_x509_csr(_csr_b(cert, key)))
        else:
            with app.app_context():
                ca_id = _signing_ca(row_id)[0].id
            r = auth_client.post(f'/api/v2/csrs/{csr_id}/sign', json={'ca_id': ca_id, 'validity_days': 30})
            assert r.status_code == 400, r.data
            assert 'not held by this instance' in json.loads(r.data)['message']
        with app.app_context():
            a_row = db.session.get(Certificate, row_id)
            assert (a_row.serial_number, a_row.related_certificate_id) == (str(cert.serial_number), None)
            assert Certificate.query.filter_by(related_certificate_id=row_id).count() == 0
    finally:
        monkeypatch.undo()
        with app.app_context():
            a_row = db.session.get(Certificate, row_id)
            a_row.crt = base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode()
            a_row.serial_number, a_row.related_certificate_id = str(cert.serial_number), None
            db.session.commit()


def test_a_related_certificate_under_an_expired_ca_certificate_is_refused(app, create_ca, create_cert):
    """RFC 9763 §3.2 asks for RFC 5280 path validation of A: its CA must be valid now."""
    from services.hsm.ca_key_loader import get_ca_signing_key
    from utils.key_codec import load_pem_bytes
    ca_id = create_ca(cn='Related expired CA')['id']
    data = create_cert(ca_id=ca_id, key_type='ec', key_size='256', cert_type='server')
    with app.app_context():
        row = db.session.get(Certificate, data['id'])
        cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
        key = serialization.load_pem_private_key(load_pem_bytes(row.prv, context='test'), None)
        ca = db.session.get(CA, ca_id)
        ca_cert = x509.load_pem_x509_certificate(base64.b64decode(ca.crt))
        ca_key = get_ca_signing_key(ca)
        now = utc_now()
        expired = (x509.CertificateBuilder().subject_name(ca_cert.subject).issuer_name(ca_cert.subject)
                   .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now - timedelta(days=20)).not_valid_after(now - timedelta(days=10)))
        for ext in ca_cert.extensions:
            expired = expired.add_extension(ext.value, critical=ext.critical)
        expired = expired.sign(ca_key, hashes.SHA256())
        previous, ca.crt = ca.crt, base64.b64encode(expired.public_bytes(serialization.Encoding.PEM)).decode()
        db.session.commit()
        try:
            req = related_cert.parse_request(related_cert.build_request(cert, key, 'u:x'))
            with pytest.raises(RelatedCertificateRefused, match='CA certificate .* is not valid now'):
                verify_request(req)
            # Who does not hold A's key learns nothing of its CA
            forged = related_cert.parse_request(related_cert.build_request(
                cert, ec.generate_private_key(ec.SECP256R1()), 'u:x'))
            with pytest.raises(RelatedCertificateRefused, match='signature does not verify') as refused:
                verify_request(forged)
            assert 'Related expired CA' not in str(refused.value)
        finally:
            ca = db.session.get(CA, ca_id)
            ca.crt = previous
            db.session.commit()


def _resign(ca_id, signer_id, change):
    """Reissue CA *ca_id*'s certificate with the same key, names and serial, the
    extensions passed through *change*, signed by CA *signer_id*; returns the old crt."""
    from services.hsm.ca_key_loader import get_ca_signing_key
    ca = db.session.get(CA, ca_id)
    cert = x509.load_pem_x509_certificate(base64.b64decode(ca.crt))
    builder = (x509.CertificateBuilder().subject_name(cert.subject).issuer_name(cert.issuer)
               .public_key(cert.public_key()).serial_number(cert.serial_number)
               .not_valid_before(cert.not_valid_before_utc).not_valid_after(cert.not_valid_after_utc))
    for ext in change(list(cert.extensions)):
        builder = builder.add_extension(ext.value, critical=ext.critical)
    signed = builder.sign(get_ca_signing_key(db.session.get(CA, signer_id)), hashes.SHA256())
    previous, ca.crt = ca.crt, base64.b64encode(signed.public_bytes(serialization.Encoding.PEM)).decode()
    db.session.commit()
    return previous


def _replaced(extensions, kind, value):
    return [x509.Extension(e.oid, e.critical, value) if isinstance(e.value, kind) else e
            for e in extensions]


def _usage(key_cert_sign):
    return x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False,
                         data_encipherment=False, key_agreement=False, key_cert_sign=key_cert_sign,
                         crl_sign=True, encipher_only=False, decipher_only=False)


@pytest.fixture
def two_level_a(app, auth_client, create_ca, create_cert):
    """A under an intermediate under a root, both held here: ``(root id, inter id, request)``."""
    from utils.key_codec import load_pem_bytes
    root_id = create_ca(cn='Related path root')['id']
    r = auth_client.post('/api/v2/cas', data=json.dumps({
        'type': 'intermediate', 'parentCAId': root_id, 'commonName': 'Related path inter',
        'keyAlgo': 'EC', 'keySize': 'P-256', 'validityYears': 5}), content_type='application/json')
    assert r.status_code in (200, 201), r.data
    inter_id = json.loads(r.data)['data']['id']
    data = create_cert(ca_id=inter_id, key_type='ec', key_size='256', cert_type='server')
    with app.app_context():
        row = db.session.get(Certificate, data['id'])
        cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
        key = serialization.load_pem_private_key(load_pem_bytes(row.prv, context='test'), None)
    return root_id, inter_id, related_cert.parse_request(related_cert.build_request(cert, key, 'u:x'))


@pytest.mark.parametrize('target,change,message', [
    ('inter', lambda e: _replaced(e, x509.BasicConstraints, x509.BasicConstraints(False, None)),
     'is not a CA certificate'),
    ('inter', lambda e: [x for x in e if not isinstance(x.value, x509.BasicConstraints)],
     'is not a CA certificate'),
    ('inter', lambda e: _replaced(e, x509.KeyUsage, _usage(False)), r'may not sign certificates'),
    ('root', lambda e: _replaced(e, x509.BasicConstraints, x509.BasicConstraints(True, 0)),
     'path length constraint'),
    ('root', lambda e: _replaced(e, x509.BasicConstraints, x509.BasicConstraints(True, 1)), None),
    ('inter', lambda e: _replaced(e, x509.BasicConstraints, x509.BasicConstraints(True, 0)), None),
    ('inter', lambda e: _replaced(e, x509.KeyUsage, _usage(True)), None),
    # (k) skips the trust anchor: a self-signed root needs keyUsage keyCertSign, not BC
    ('root', lambda e: [x for x in e if not isinstance(x.value, x509.BasicConstraints)], None),
    ('root', lambda e: [x for x in e if not isinstance(x.value, (x509.BasicConstraints, x509.KeyUsage))],
     'is not a CA certificate'),
    ('root', lambda e: _replaced(e, x509.BasicConstraints, x509.BasicConstraints(False, None)),
     'is not a CA certificate'),
    ('root', lambda e: _replaced(e, x509.KeyUsage, _usage(False)), r'may not sign certificates'),
])
def test_the_path_of_a_is_validated_as_rfc_5280_says(app, two_level_a, target, change, message):
    """RFC 5280 §6.1.4 (k)-(n) on A's CA certificates: cA, pathLenConstraint, keyCertSign."""
    root_id, inter_id, req = two_level_a
    ca_id = inter_id if target == 'inter' else root_id
    with app.app_context():
        verify_request(req)
        previous = _resign(ca_id, root_id, change)
        try:
            if message is None:
                verify_request(req)
            else:
                with pytest.raises(RelatedCertificateRefused, match=message):
                    verify_request(req)
        finally:
            db.session.get(CA, ca_id).crt = previous
            db.session.commit()


def test_a_v1_root_anchors_the_path_of_a(app, two_level_a):
    """OpenSSL accepts a self-signed v1 root as trust anchor (X509_check_ca returns 3)."""
    from asn1crypto import x509 as asn1_x509
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    from services.hsm.ca_key_loader import get_ca_signing_key
    root_id, _inter_id, req = two_level_a
    with app.app_context():
        root = db.session.get(CA, root_id)
        der = x509.load_pem_x509_certificate(base64.b64decode(root.crt)).public_bytes(
            serialization.Encoding.DER)
        tbs = asn1_x509.Certificate.load(der)['tbs_certificate']
        tbs['version'] = 'v1'
        tbs['extensions'] = None
        key = get_ca_signing_key(root)
        signed = tbs.dump(force=True)
        signature = (key.sign(signed, padding.PKCS1v15(), hashes.SHA256())
                     if isinstance(key, rsa.RSAPrivateKey) else key.sign(signed, ec.ECDSA(hashes.SHA256())))
        cert = asn1_x509.Certificate({'tbs_certificate': tbs, 'signature_algorithm': tbs['signature'],
                                      'signature_value': signature})
        v1 = x509.load_der_x509_certificate(cert.dump())
        assert v1.version == x509.Version.v1 and not list(v1.extensions)
        previous, root.crt = root.crt, base64.b64encode(v1.public_bytes(serialization.Encoding.PEM)).decode()
        db.session.commit()
        try:
            verify_request(req)
        finally:
            db.session.get(CA, root_id).crt = previous
            db.session.commit()


@pytest.mark.parametrize('member', ['a', 'b'])
def test_acme_revocation_revokes_the_presented_member_only(app, client, create_cert, member):
    """RFC 8555 §7.6: revoking A or B through ACME leaves the other one valid."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from tests.test_acme_security_paths import _build_jws, _int_to_b64, _nonce, _post_jws
    from utils.key_codec import load_pem_bytes
    data = create_cert(cert_type='server', key_type='rsa', key_size='2048')
    key_b = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with app.app_context():
        a_row = db.session.get(Certificate, data['id'])
        a_id = a_row.id
        cert_a2 = x509.load_pem_x509_certificate(base64.b64decode(a_row.crt))
        key_a = serialization.load_pem_private_key(load_pem_bytes(a_row.prv, context='test'), None)
        b_row = _est_sign(_signing_ca(a_id)[0], _csr_naming(cert_a2, key_a, key_b))
        b_id, cert_b = b_row.id, x509.load_pem_x509_certificate(base64.b64decode(b_row.crt))
        assert db.session.get(Certificate, a_id).related_certificate_id == b_id
    presented, key = (cert_a2, key_a) if member == 'a' else (cert_b, key_b)
    pub = key.public_key().public_numbers()
    der = presented.public_bytes(serialization.Encoding.DER)
    jws = _build_jws('http://localhost/acme/revoke-cert',
                     {'certificate': base64.urlsafe_b64encode(der).rstrip(b'=').decode(), 'reason': 1},
                     key, jwk={'kty': 'RSA', 'n': _int_to_b64(pub.n), 'e': _int_to_b64(pub.e)},
                     nonce=_nonce(client))
    r = _post_jws(client, '/acme/revoke-cert', jws)
    assert r.status_code == 200, r.data
    with app.app_context():
        db.session.expire_all()
        revoked = [bool(db.session.get(Certificate, i).revoked) for i in (a_id, b_id)]
    assert revoked == ([True, False] if member == 'a' else [False, True])


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


def test_using_the_key_of_a_needs_the_private_key_permission(app, auth_client, cert_a, create_user):
    """An operator holds write:csrs, not read:private_keys: A's key signs nothing for it."""
    from models import AuditLog
    row_id, cert, _key = cert_a
    cn = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
    body = {'cn': cn, 'key_type': PQ_LABEL, 'related_to': row_id}
    user = create_user(role='operator')
    operator = app.test_client()
    r = operator.post('/api/v2/auth/login', json={'username': user['username'], 'password': 'TestPass123!'})
    assert r.status_code == 200, r.data

    def key_uses():
        with app.app_context():
            return [e.details for e in AuditLog.query.filter_by(
                action='certificate_key_used', resource_id=str(row_id)).all()]

    r = operator.post('/api/v2/csrs', json=body)
    assert r.status_code == 403 and b'read:private_keys' in r.data, r.data
    assert key_uses() == []
    r = auth_client.post('/api/v2/csrs', json=body)
    assert r.status_code == 201, r.data
    csr_id = json.loads(r.data)['data']['id']
    assert [f'#{csr_id}' in d for d in key_uses()] == [True]


@pytest.mark.parametrize('related_to,message', [('7', b'related_to must be'), (True, b'related_to must be'),
                                                (0, b'related_to must be'),
                                                (10 ** 9, b'Related certificate not found')])
def test_the_csr_route_refuses_a_bad_related_to(auth_client, related_to, message):
    r = auth_client.post('/api/v2/csrs', json={'cn': 'bad-related.example.com', 'key_type': 'EC P-256',
                                               'related_to': related_to})
    assert r.status_code == 400 and message in r.data, r.data
