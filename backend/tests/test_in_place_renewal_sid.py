"""Characterization: an in-place renewal (UI, REST, scheduler, bulk) copies the SID security
extension as it is, and does not ask the AD Connector whether the account still exists.
A maintainer decision may change the second half; this test then changes with it."""
import base64

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from models import CA, Certificate, db
from services.ad_connector import lookup as ad_lookup
from services.ca_service import CAService
from services.cert.renewal import renew_certificate_in_place
from services.trust_store.csr_operations_mixin import _SID_SECURITY_EXT_OID, _ad_security_extension
from tests.test_wstep_strong_cert_mapping import _clear_ad_connector, _configure_ad_connector

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')

SID = 'S-1-5-21-1608104657-630783805-1473387121-1105'


@pytest.fixture(autouse=True)
def _no_connector(app):
    _clear_ad_connector(app)
    yield
    _clear_ad_connector(app)


def _sid_ext(cert):
    return cert.extensions.get_extension_for_oid(_SID_SECURITY_EXT_OID)


def _issued_row(app, ca_id, cn):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
           .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
           .sign(key, hashes.SHA256()))
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        pem, _serial = CAService.sign_csr_from_crypto(ca=ca, csr=csr, validity_days=30, source='test',
                                                      requester_sid=SID)
        row = Certificate.query.filter_by(caref=ca.refid, subject_cn=cn).one()
        # The server holds the key, as for a certificate it generated: renewable in place
        from utils.key_codec import store_pem_bytes
        row.prv = store_pem_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                    serialization.NoEncryption()))
        db.session.commit()
        return row.id, x509.load_pem_x509_certificate(pem.encode())


def _stored(row_id):
    return x509.load_pem_x509_certificate(base64.b64decode(db.session.get(Certificate, row_id).crt))


@pytest.mark.parametrize('connector', [False, True], ids=['connector-off', 'connector-on'])
def test_in_place_renewal_copies_the_sid_extension_without_a_directory_check(
        app, create_ca, monkeypatch, connector):
    ca_data = create_ca(cn=f'In-place renewal SID CA {connector}')
    row_id, original = _issued_row(app, ca_data['id'], f'in-place-sid-{str(connector).lower()}.example.test')
    if connector:
        _configure_ad_connector(app)
    asked = []
    monkeypatch.setattr(ad_lookup, 'lookup_account_by_sid', lambda sid: asked.append(sid) or ad_lookup.NO_ACCOUNT)
    with app.app_context():
        renew_certificate_in_place(db.session.get(Certificate, row_id), username='admin')
        db.session.commit()
        renewed = _stored(row_id)
    assert renewed.serial_number != original.serial_number
    ext = _sid_ext(renewed)
    assert ext.critical is False
    assert ext.value.value == _sid_ext(original).value.value == _ad_security_extension(SID).value
    assert asked == []
