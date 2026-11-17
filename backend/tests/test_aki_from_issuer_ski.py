"""Every issuance path derives the Authority Key Identifier from the issuing
CA certificate's own Subject Key Identifier (RFC 5280 §4.2.1.1).

The shared CSR trunk, the lifecycle service and the CRL already did; the
issue form, the approval workflow, SCEP, in-place renewal, the TSA signer
certificate and the OCSP responder renewal recomputed it from the CA's public
key instead. For a CA whose SKI is not the RFC 5280 method-1 hash of its key
(RFC 7093 truncated SHA-256, an HSM or AD CS-generated identifier, an
imported CA) the leaf's AKI then differed from the CA's SKI and strict
validators failed to build the chain (OpenSSL: akid/skid mismatch).
"""

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtensionOID, NameOID

from models import CA, Certificate, db
from utils.key_codec import store_pem_bytes

ODD_SKI = bytes(range(20))  # deliberately not SHA-1(subjectPublicKey)


def _ca_with_odd_ski(cn):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier(ODD_SKI), critical=False)
        .add_extension(
            x509.KeyUsage(digital_signature=True, key_encipherment=False, content_commitment=False,
                          data_encipherment=False, key_agreement=False, key_cert_sign=True,
                          crl_sign=True, encipher_only=False, decipher_only=False),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    return cert, key


@pytest.fixture
def odd_ca(app, create_ca):
    """A CA row whose certificate carries a non-method-1 SKI."""
    ca_data = create_ca(cn='Odd SKI CA')
    cert, key = _ca_with_odd_ski('Odd SKI CA')
    with app.app_context():
        ca = db.session.get(CA, ca_data['id'])
        ca.crt = base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode()
        ca.prv = store_pem_bytes(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        db.session.commit()
        return {'id': ca.id, 'refid': ca.refid}


def _aki(cert):
    return cert.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_KEY_IDENTIFIER).value.key_identifier


def _row_cert(app, cert_id):
    with app.app_context():
        row = db.session.get(Certificate, cert_id)
        return x509.load_pem_x509_certificate(base64.b64decode(row.crt), default_backend())


class TestAkiMatchesIssuerSki:

    def test_issue_form(self, app, auth_client, odd_ca):
        r = auth_client.post('/api/v2/certificates', data=json.dumps({
            'cn': 'aki-form.example.test', 'ca_id': odd_ca['id'], 'validity_days': 30,
        }), content_type='application/json')
        assert r.status_code == 201, r.get_json()
        assert _aki(_row_cert(app, r.get_json()['data']['id'])) == ODD_SKI

    def test_approval_workflow(self, app, odd_ca):
        from tests.test_approval_template_issuance import _mk_approval_id, _requester_id
        from models.policy import ApprovalRequest
        from api.v2.policies import _issue_approved_certificate
        with app.app_context():
            approval = db.session.get(ApprovalRequest, _mk_approval_id(
                app, _requester_id(app),
                {'cn': 'aki-approval.example.test', 'ca_id': odd_ca['id'],
                 'cert_type': 'server', 'validity_days': 30},
            ))
            result = _issue_approved_certificate(approval)
        assert _aki(_row_cert(app, result['id'])) == ODD_SKI

    def test_in_place_renewal(self, app, odd_ca):
        from services.cert_service import CertificateService
        from services.cert.renewal import renew_certificate_in_place
        with app.app_context():
            row = CertificateService.create_certificate(
                descr='aki-renew', caref=odd_ca['refid'], dn={'CN': 'aki-renew.example.test'},
                cert_type='server_cert', key_type='2048', validity_days=30, username='admin',
            )
            db.session.commit()
            renew_certificate_in_place(row, username='admin')
            db.session.commit()
            row_id = row.id
        assert _aki(_row_cert(app, row_id)) == ODD_SKI

    def test_tsa_signer_certificate(self, app, odd_ca):
        from services import tsa_signer_cert
        with app.app_context():
            ca = db.session.get(CA, odd_ca['id'])
            issued = tsa_signer_cert.issue_tsa_signer_certificate(ca=ca, cn='aki-tsa.example.test')
            leaf = x509.load_pem_x509_certificate(base64.b64decode(issued.crt), default_backend())
        assert _aki(leaf) == ODD_SKI
