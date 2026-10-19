"""ACME finalize reads a request with CA:FALSE and a path length (Windows-shaped).

The raw cryptography accessor refuses that BasicConstraints, so the identifiers
were never found and finalize failed.
"""
import base64

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from models import CA, Certificate, db
from services.acme.acme_service import AcmeService
import tests.test_acme_profile_template as profile_tests
from tests.test_csr_windows_basic_constraints import _windows_shaped_csr


def test_finalize_issues_for_a_windows_shaped_request(app, monkeypatch, create_ca):
    ca = create_ca(cn='ACME Windows CSR CA')
    with app.app_context():
        ca_refid = db.session.get(CA, ca['id']).refid
        order = profile_tests.TestFinalizeWithBoundTemplate._order(None)
        service = AcmeService(base_url='http://localhost')
        from utils import caa_checker
        monkeypatch.setattr(caa_checker, 'check_caa_for_domains', lambda *a, **k: (True, 'allowed'))
        monkeypatch.setattr(service, '_resolve_ca_for_domains', lambda _d: ca_refid)
        csr = _windows_shaped_csr(rsa.generate_private_key(public_exponent=65537, key_size=2048),
                                  'web.example.com')
        service.begin_order_processing(order)
        service._finalizing_order_id = order.order_id
        success, error = service.finalize_order(
            order.order_id, csr.public_bytes(serialization.Encoding.PEM).decode())
        service._finalizing_order_id = None
        assert success, error
        db.session.refresh(order)
        row = db.session.get(Certificate, order.certificate_id)
        cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
        names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        assert names.get_values_for_type(x509.DNSName) == ['web.example.com']
