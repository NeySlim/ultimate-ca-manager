"""SCEP checks the CA's name constraints once the EKUs are settled: an S/MIME
certificate's dotted CN (john.doe) names a person, not a host, while a server
CN or a SAN dNSName outside the constraints is still refused."""

import base64

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from models import CA, Certificate, SCEPRequest, db

NC = [{'type': 'dns', 'value': 'example.com'}, {'type': 'email', 'value': 'example.com'}]


def _csr(cn, ekus=(), dns=(), emails=()):
    builder = x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
    names = [x509.DNSName(d) for d in dns] + [x509.RFC822Name(e) for e in emails]
    if names:
        builder = builder.add_extension(x509.SubjectAlternativeName(names), critical=False)
    if ekus:
        builder = builder.add_extension(x509.ExtendedKeyUsage(list(ekus)), critical=False)
    return builder.sign(ec.generate_private_key(ec.SECP256R1()), hashes.SHA256())


def _issue(app, ca_id, csr, txn):
    """(stored cert_type, certificate) of a SCEP issuance; raises its refusal."""
    from services.scep.scep_service import SCEPService
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        svc = SCEPService(ca_refid=ca.refid, auto_approve=True)
        req = SCEPRequest(transaction_id=txn, ca_refid=ca.refid,
                          csr=base64.b64encode(csr.public_bytes(serialization.Encoding.DER)).decode(),
                          status='pending', subject=csr.subject.rfc4514_string())
        db.session.add(req)
        db.session.flush()
        try:
            refid = svc._auto_approve_request(req, csr)
            db.session.commit()
            row = Certificate.query.filter_by(refid=refid).one()
            found = row.cert_type, x509.load_pem_x509_certificate(base64.b64decode(row.crt))
            db.session.delete(row)
            db.session.delete(req)
            db.session.commit()
            return found
        finally:
            db.session.rollback()


@pytest.fixture
def constrained_ca(create_ca):
    return create_ca(cn='SCEP NC profile CA', nameConstraintsPermitted=NC)['id']


def test_smime_dotted_person_cn_is_issued(app, constrained_ca):
    csr = _csr('john.doe', ekus=[ExtendedKeyUsageOID.EMAIL_PROTECTION],
               emails=['john.doe@example.com'])
    cert_type, cert = _issue(app, constrained_ca, csr, 'scep-nc-smime')
    assert cert_type == 'email_cert'
    assert cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == 'john.doe'


@pytest.mark.parametrize('ekus', [
    [ExtendedKeyUsageOID.EMAIL_PROTECTION, ExtendedKeyUsageOID.SERVER_AUTH],
    [ExtendedKeyUsageOID.SERVER_AUTH],
    [ExtendedKeyUsageOID.CLIENT_AUTH],
    [],
])
def test_a_cn_that_may_name_a_host_outside_the_constraints_is_refused(app, constrained_ca, ekus):
    csr = _csr('www.outside.test', ekus=ekus)
    with pytest.raises(ValueError, match='www.outside.test'):
        _issue(app, constrained_ca, csr, f'scep-nc-host-{len(ekus)}')


def test_the_issued_ekus_decide_not_the_requested_ones(app, constrained_ca):
    """anyExtendedKeyUsage is not issuable over SCEP: the certificate is S/MIME only."""
    csr = _csr('john.doe', ekus=[ExtendedKeyUsageOID.EMAIL_PROTECTION,
                                 ExtendedKeyUsageOID.ANY_EXTENDED_KEY_USAGE])
    cert_type, cert = _issue(app, constrained_ca, csr, 'scep-nc-any')
    assert cert_type == 'email_cert'
    assert list(cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value) == [
        ExtendedKeyUsageOID.EMAIL_PROTECTION]


def test_a_dns_name_outside_the_constraints_is_refused(app, constrained_ca):
    csr = _csr('john.doe', ekus=[ExtendedKeyUsageOID.EMAIL_PROTECTION],
               dns=['mail.outside.test'], emails=['john.doe@example.com'])
    with pytest.raises(ValueError, match='mail.outside.test'):
        _issue(app, constrained_ca, csr, 'scep-nc-san')


@pytest.mark.parametrize('ekus,expected', [
    ([ExtendedKeyUsageOID.CLIENT_AUTH], 'client_cert'),
    ([ExtendedKeyUsageOID.CODE_SIGNING], 'code_signing'),
    ([ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH], 'server_cert'),
    ([], 'server_cert'),
])
def test_the_row_records_the_type_its_ekus_give(app, create_ca, ekus, expected):
    ca_id = create_ca(cn='SCEP recorded type CA')['id']
    cert_type, _cert = _issue(app, ca_id, _csr('device.example.com', ekus=ekus),
                              f'scep-type-{expected}-{len(ekus)}')
    assert cert_type == expected
