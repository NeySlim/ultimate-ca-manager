"""WSTEP issues for the matched template's validity.

XCEP advertises each template's validity to Windows, but WSTEP signed with
the global "Validity (days)" whatever template matched.
"""
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import ExtendedKeyUsageOID

from models import CA, db
from services.wstep import wstep_service
from tests.test_wstep_template_eku import _make_csr, smartcard_template_config  # noqa: F401


def _days(cert_pem):
    cert = x509.load_pem_x509_certificate(cert_pem.encode())
    return (cert.not_valid_after_utc - cert.not_valid_before_utc).days


def test_matched_template_sets_the_validity(app, smartcard_template_config):  # noqa: F811
    csr, _ = _make_csr('validity-user.example.test', ekus=[ExtendedKeyUsageOID.CLIENT_AUTH])
    with app.app_context():
        ca = db.session.get(CA, smartcard_template_config['id'])
        cert_pem, err = wstep_service.issue(ca, csr.public_bytes(Encoding.DER), validity_days=30)
    assert err is None, err
    assert _days(cert_pem) >= 364  # the template's 365, not the global 30


def test_no_template_keeps_the_global_validity():
    assert wstep_service._template_validity(None, 30) == 30
